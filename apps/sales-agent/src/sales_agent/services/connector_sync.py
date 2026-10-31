from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

import structlog

from common import SalesAgentSettings
from common.config import ConnectorSettings

from src.sales_agent.connectors.bootstrap import update_connector_registry
from src.sales_agent.connectors.registry import ConnectorRegistry
from src.sales_agent.services.backend_client import (
    BackendClient,
    BackendConnectorPayload,
)

log = structlog.get_logger(__name__)


class ConnectorSync:
    """Load connector configuration from backend with fallback to local settings."""

    def __init__(
        self,
        settings: SalesAgentSettings,
        backend_client: BackendClient,
        registry: ConnectorRegistry | None = None,
        tracer: Any | None = None,
    ) -> None:
        self._settings = settings
        self._backend = backend_client
        self._registry = registry
        self._tracer = tracer
        self._base_interval = max(0.0, float(settings.connectors_refresh_interval_s))
        self._dynamic_interval: float | None = None
        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._fallback = {key: cfg.model_copy(deep=True) for key, cfg in (settings.connectors or {}).items()}
        self._last_connectors = {key: cfg.model_copy(deep=True) for key, cfg in (settings.connectors or {}).items()}

    async def bootstrap(self) -> None:
        """Perform initial refresh; keep fallback if backend unavailable."""
        success = await self.refresh(reason="bootstrap")
        if not success and not self._last_connectors:
            await self._apply_map(self._fallback)

    async def refresh(self, *, reason: str = "manual") -> bool:
        """Refresh connector configuration from backend.

        Returns:
            bool: True when backend delivered a valid payload.
        """
        response = await self._backend.list_connectors()
        if response is None:
            log.info(
                "connector_sync.refresh.skipped",
                reason=reason,
                fallback="existing_connectors",
            )
            return False

        connectors = self._parse_connectors(response.connectors)
        if connectors:
            merged = self._merge_with_fallback(connectors)
            await self._apply_map(merged)
            self._last_connectors = {key: cfg.model_copy(deep=True) for key, cfg in merged.items()}

            if self._registry is not None:
                from common import SalesAgentSettings

                current_settings = SalesAgentSettings()
                current_settings.connectors = merged
                update_connector_registry(self._registry, current_settings, tracer=self._tracer)

            if response.ttl_seconds and response.ttl_seconds > 0:
                self._dynamic_interval = float(response.ttl_seconds)
            log.info(
                "connector_sync.refresh.completed",
                reason=reason,
                connector_ids=sorted(merged.keys()),
                ttl_seconds=response.ttl_seconds,
                interval=self._effective_interval(),
            )
            return True

        log.warning(
            "connector_sync.refresh.empty",
            reason=reason,
            action="retain_previous",
        )
        return False

    async def start(self) -> None:
        """Start periodic refresh if interval configured."""
        interval = self._effective_interval()
        if interval <= 0:
            log.info(
                "connector_sync.background.disabled",
                interval=interval,
            )
            return
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._worker(), name="connector-sync")

    async def stop(self) -> None:
        """Stop background refresh task."""
        self._stop_event.set()
        task = self._task
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def _worker(self) -> None:
        try:
            while True:
                interval = self._effective_interval()
                if interval <= 0:
                    break
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                except TimeoutError:
                    pass
                if self._stop_event.is_set():
                    break
                await self.refresh(reason="periodic")
        except asyncio.CancelledError:
            raise

    def _effective_interval(self) -> float:
        return float(self._dynamic_interval or self._base_interval or 0.0)

    async def _apply_map(self, new_map: dict[str, ConnectorSettings]) -> None:
        async with self._lock:
            self._settings.connectors = {key: cfg.model_copy(deep=True) for key, cfg in new_map.items()}

    def _merge_with_fallback(self, connectors: Iterable[ConnectorSettings]) -> dict[str, ConnectorSettings]:
        merged: dict[str, ConnectorSettings] = {key: cfg.model_copy(deep=True) for key, cfg in self._fallback.items()}
        for cfg in connectors:
            connector_id = cfg.connector_id or ""
            if not connector_id:
                log.warning("connector_sync.merge.missing_id")
                continue
            merged[connector_id] = cfg
        return merged

    def _parse_connectors(self, payloads: Iterable[BackendConnectorPayload]) -> list[ConnectorSettings]:
        configs: list[ConnectorSettings] = []
        for payload in payloads:
            cfg = self._build_connector_config(payload)
            if cfg is None:
                continue
            configs.append(cfg)
        return configs

    def _build_connector_config(self, payload: BackendConnectorPayload) -> ConnectorSettings | None:
        channel_types = payload.channel_types or []
        if payload.channel_type and payload.channel_type not in channel_types:
            channel_types = [payload.channel_type, *channel_types]

        data: dict[str, Any] = {
            "connector_id": payload.connector_id,
            "type": payload.type,
            "channel_type": payload.channel_type,
            "channel_types": channel_types,
            "metadata": dict(payload.metadata or {}),
            "enabled": True if payload.enabled is None else payload.enabled,
        }
        log.debug(
            "connector_sync.build.data",
            connector_id=payload.connector_id,
            payload_type=payload.type,
            channel_type=payload.channel_type,
        )

        debounce: dict[str, Any] = {}
        # Support both nested (legacy) and flat (new unified API) debounce fields
        if payload.debounce is not None:
            if payload.debounce.window_seconds is not None:
                debounce["window_seconds"] = payload.debounce.window_seconds
            if payload.debounce.max_batch_messages is not None:
                debounce["max_batch_messages"] = payload.debounce.max_batch_messages
            if payload.debounce.storage_key_template is not None:
                debounce["storage_key_template"] = payload.debounce.storage_key_template
        # Flat fields take precedence (new unified connector API)
        if payload.debounce_window_seconds is not None:
            debounce["window_seconds"] = payload.debounce_window_seconds
        if payload.debounce_storage_key_template is not None:
            debounce["storage_key_template"] = payload.debounce_storage_key_template
        if debounce:
            data["debounce"] = debounce

        if payload.secrets is not None:
            secrets: dict[str, Any] = {}
            if payload.secrets.token is not None:
                secrets["token"] = payload.secrets.token
            if payload.secrets.extra:
                secrets["extra"] = dict(payload.secrets.extra)
            if secrets:
                data["secrets"] = secrets

        if payload.callbacks is not None:
            callbacks: dict[str, Any] = {}
            if payload.callbacks.delivery_url is not None:
                callbacks["delivery_url"] = payload.callbacks.delivery_url
            if payload.callbacks.poll_url is not None:
                callbacks["poll_url"] = payload.callbacks.poll_url
            if payload.callbacks.proxy_url is not None:
                callbacks["proxy_url"] = payload.callbacks.proxy_url
            if payload.callbacks.handoff_url is not None:
                callbacks["handoff_url"] = payload.callbacks.handoff_url
            if callbacks:
                data["callbacks"] = callbacks

        if payload.transport is not None:
            transport: dict[str, Any] = {}
            if payload.transport.enabled is not None:
                transport["enabled"] = payload.transport.enabled
            if payload.transport.endpoint is not None:
                transport["endpoint"] = payload.transport.endpoint
            if payload.transport.retries is not None:
                retries: dict[str, Any] = {}
                if payload.transport.retries.max_attempts is not None:
                    retries["max_attempts"] = payload.transport.retries.max_attempts
                if payload.transport.retries.backoff_schedule_ms is not None:
                    retries["backoff_schedule_ms"] = list(payload.transport.retries.backoff_schedule_ms)
                if payload.transport.retries.connect_timeout_s is not None:
                    retries["connect_timeout_s"] = payload.transport.retries.connect_timeout_s
                if payload.transport.retries.read_timeout_s is not None:
                    retries["read_timeout_s"] = payload.transport.retries.read_timeout_s
                if payload.transport.retries.total_timeout_s is not None:
                    retries["total_timeout_s"] = payload.transport.retries.total_timeout_s
                if retries:
                    transport["retries"] = retries
            if transport:
                data["transport"] = transport
        elif payload.type in ("telegram", "wappi"):
            # Enable transport for managed connectors (telegram-module, wappi-module)
            # Actual endpoint is resolved from settings in message_processor
            data["transport"] = {"enabled": True}

        try:
            cfg = ConnectorSettings.model_validate(data)
        except Exception as exc:
            log.warning(
                "connector_sync.parse.invalid_connector",
                connector_id=payload.connector_id,
                error=str(exc),
            )
            return None

        cfg.assign_defaults(payload.connector_id)
        return cfg
