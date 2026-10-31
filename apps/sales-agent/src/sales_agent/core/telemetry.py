from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

import structlog
from langfuse import get_client as _get_client

from common import SalesAgentSettings as Settings

log = structlog.get_logger()


class Tracer:
    @contextlib.contextmanager
    def start_trace(
        self,
        name: str,
        *,
        input: Any | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> Iterator[None]:
        yield

    @contextlib.contextmanager
    def start_span(
        self,
        name: str,
        *,
        input: Any | None = None,
        metadata: dict | None = None,
    ) -> Iterator[None]:
        yield

    @contextlib.contextmanager
    def start_generation(
        self,
        name: str,
        *,
        model: str | None = None,
        model_parameters: dict | None = None,
        input: Any | None = None,
        metadata: dict | None = None,
    ) -> Iterator[None]:
        yield

    def update_current_trace(self, **kwargs: Any) -> None:  # pragma: no cover
        return None

    def update_current_span(self, **kwargs: Any) -> None:  # pragma: no cover
        return None

    def update_current_generation(self, **kwargs: Any) -> None:  # pragma: no cover
        return None

    def score_current_trace(self, name: str, value: float, **kwargs: Any) -> None:  # pragma: no cover
        return None

    def flush(self) -> None:  # pragma: no cover
        return None

    def record_event(
        self,
        name: str,
        *,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        return None

    def connector_tags(
        self,
        *,
        connector_id: str | None = None,
        connector_type: str | None = None,
        channel_type: str | None = None,
        extra: list[str] | None = None,
    ) -> list[str]:
        tags: list[str] = list(extra or [])
        if connector_id:
            tags.append(f"connector:{connector_id}")
        if connector_type:
            tags.append(f"connector_type:{connector_type}")
        if channel_type:
            tags.append(f"channel:{channel_type}")
        return tags

    def transport_delivery_event(
        self,
        phase: Literal["attempt", "retry", "sent", "failed"],
        *,
        metadata: dict[str, Any],
        tags: list[str] | None = None,
    ) -> None:
        event_name = f"transport.delivery.{phase}"
        self.record_event(event_name, metadata=metadata, tags=tags)


class NoopTracer(Tracer):
    pass


@dataclass
class LangfuseTracer(Tracer):
    settings: Settings

    def __post_init__(self):
        self._client = None
        self._lc_handler = None
        lf_cfg = self.settings.langfuse
        if lf_cfg.enabled:
            pk = lf_cfg.public_key.get_secret_value() if lf_cfg.public_key is not None else None
            sk = lf_cfg.secret_key.get_secret_value() if lf_cfg.secret_key is not None else None
            host = lf_cfg.host

            log.info("telemetry.langfuse.init", enabled=True, host=host)
            if not pk or not sk:
                log.warning("telemetry.langfuse.keys_missing_fallback_noop")
                return

            os.environ["LANGFUSE_PUBLIC_KEY"] = pk
            os.environ["LANGFUSE_SECRET_KEY"] = sk
            if host:
                os.environ["LANGFUSE_HOST"] = host

            try:
                self._client = _get_client()
                try:
                    if getattr(self._client, "auth_check", None):  # type: ignore[attr-defined]
                        self._client.auth_check()
                except Exception:
                    pass
                log.info("telemetry.langfuse.client_created", host=host)

            except Exception as exc:  # pragma: no cover
                raise RuntimeError("Langfuse initialization failed") from exc

    @contextlib.contextmanager
    def start_trace(
        self,
        name: str,
        *,
        input: Any | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> Iterator[None]:
        if not self._client:
            log.debug("telemetry.langfuse.no_client_skip", span=name)
            yield
            return
        # Use provided name as the top-level span name (e.g., "chat.process").
        with self._client.start_as_current_span(name=name):
            try:
                # Keep trace-level attributes updated
                self._client.update_current_trace(name=name)
                if tags:
                    self._client.update_current_trace(tags=list(tags))
                if input is not None:
                    self._client.update_current_trace(input=input)
                if metadata:
                    self._client.update_current_trace(metadata=metadata)
                if user_id is not None:
                    self._client.update_current_trace(user_id=user_id)
                if session_id is not None:
                    self._client.update_current_trace(session_id=session_id)
            except Exception:
                pass
            yield

    @contextlib.contextmanager
    def start_span(
        self,
        name: str,
        *,
        input: Any | None = None,
        metadata: dict | None = None,
    ) -> Iterator[None]:
        if not self._client:
            log.debug("telemetry.langfuse.no_client_skip", span=name)
            yield
            return
        t0 = time.perf_counter()
        with self._client.start_as_current_span(name=name) as span:
            if input is not None:
                span.update(input=input)
            if metadata:
                span.update(metadata=metadata)
            try:
                yield
            finally:
                try:
                    latency_ms = int((time.perf_counter() - t0) * 1000)
                    span.update(metadata={"latency_ms": latency_ms})
                except Exception:
                    pass

    @contextlib.contextmanager
    def start_generation(
        self,
        name: str,
        *,
        model: str | None = None,
        model_parameters: dict | None = None,
        input: Any | None = None,
        metadata: dict | None = None,
    ) -> Iterator[None]:
        if not self._client:
            log.debug("telemetry.langfuse.no_client_skip", generation=name)
            yield
            return

        t0 = time.perf_counter()
        with self._client.start_as_current_generation(name=name) as generation:
            if model:
                generation.update(model=model)
            if model_parameters:
                generation.update(model_parameters=model_parameters)
            if input is not None:
                generation.update(input=input)
            if metadata:
                generation.update(metadata=metadata)

            try:
                yield
            finally:
                try:
                    latency_ms = int((time.perf_counter() - t0) * 1000)
                    generation.update(metadata={"latency_ms": latency_ms})
                except Exception:
                    pass

    def update_current_trace(self, **kwargs: Any) -> None:
        if not self._client:
            return
        try:
            self._client.update_current_trace(**kwargs)
        except Exception as exc:  # pragma: no cover
            log.warning("telemetry.langfuse.update_trace_error", error=str(exc))

    def update_current_span(self, **kwargs: Any) -> None:
        if not self._client:
            return
        try:
            self._client.update_current_span(**kwargs)
        except Exception as exc:  # pragma: no cover
            log.warning("telemetry.langfuse.update_span_error", error=str(exc))

    def update_current_generation(self, **kwargs: Any) -> None:
        if not self._client:
            return
        try:
            self._client.update_current_generation(**kwargs)
        except Exception as exc:  # pragma: no cover
            log.warning("telemetry.langfuse.update_generation_error", error=str(exc))

    def score_current_trace(self, name: str, value: float, **kwargs: Any) -> None:
        if not self._client:
            return
        try:
            self._client.score_current_trace(name=name, value=value, **kwargs)
        except Exception as exc:  # pragma: no cover
            log.warning("telemetry.langfuse.score_error", error=str(exc))

    def flush(self) -> None:
        if not self._client:
            return
        try:
            self._client.flush()
        except Exception as exc:  # pragma: no cover
            log.warning("telemetry.langfuse.flush_error", error=str(exc))

    def record_event(
        self,
        name: str,
        *,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> None:
        if not self._client:
            return
        event_tags = list(tags or [])
        event_name = name if name.startswith("event.") else f"event.{name}"
        try:
            with self.start_trace(
                name=event_name,
                tags=event_tags,
                metadata=metadata,
            ):
                if metadata:
                    self.update_current_trace(metadata=metadata)
        except Exception as exc:  # pragma: no cover
            log.warning("telemetry.langfuse.event_error", name=name, error=str(exc))


def get_tracer(settings: Settings) -> Tracer:
    """Factory: create tracer instance from settings.

    AICODE-NOTE: No global singleton - caller manages lifecycle.
    Typically initialized once in app lifespan and stored in app.state.
    Creates LangfuseTracer if enabled, otherwise NoopTracer.

    Args:
        settings: Application settings with Langfuse config

    Returns:
        Configured tracer instance
    """
    lf_cfg = settings.langfuse
    if lf_cfg.enabled:
        return LangfuseTracer(settings)

    return NoopTracer()
