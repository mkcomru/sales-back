from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ValidationError

from src.sales_agent.connectors.base import (
    ConnectorAuthError,
    ConnectorPayloadError,
    InboundPayload,
)
from src.sales_agent.connectors.registry import ConnectorRegistry
from src.sales_agent.handlers.dependencies import get_connector_registry, get_debouncer
from src.sales_agent.services.debounce import DebounceManager

log = structlog.get_logger(__name__)


class Ack(BaseModel):
    ok: bool
    window_seconds: int


def build_universal_webhook_router() -> APIRouter:
    """Create a universal router that handles all connectors dynamically.

    This router handles paths like /{connector_id}/webhook for connectors
    that are dynamically added after application startup.
    """
    router = APIRouter(tags=["universal"])

    @router.post("/{connector_id}/webhook", response_model=Ack)
    async def handle_universal_webhook(
        connector_id: str,
        payload: dict[str, Any],
        request: Request,
        debouncer: DebounceManager = Depends(get_debouncer),
        registry: ConnectorRegistry = Depends(get_connector_registry),
    ) -> Ack:
        connector = registry.get_inbound(connector_id)
        if connector is None:
            log.warning(
                "connector.webhook.not_found",
                connector_id=connector_id,
            )
            raise HTTPException(status_code=404, detail=f"Connector '{connector_id}' not found")

        try:
            normalized = await connector.normalize(
                InboundPayload(
                    body=payload or {},
                    headers=dict(request.headers),
                    query_params=dict(request.query_params),
                )
            )
        except ConnectorAuthError as exc:
            log.warning(
                "connector.webhook.auth_failed",
                connector_id=connector_id,
                error=str(exc),
            )
            raise HTTPException(status_code=403, detail="Forbidden") from exc
        except ConnectorPayloadError as exc:
            log.warning(
                "connector.webhook.payload_invalid",
                connector_id=connector_id,
                error=str(exc),
            )
            raise HTTPException(status_code=422, detail="Invalid payload") from exc

        window_seconds = debouncer.debounce_seconds
        for message in normalized:
            window_seconds = await debouncer.add_message(message)

        return Ack(ok=True, window_seconds=window_seconds)

    return router


class GenericWebhookRouter:
    """Factory for simple webhook routers backed by an inbound connector."""

    def __init__(
        self,
        connector_id: str,
        *,
        payload_model: type[BaseModel] | None = None,
        prefix: str | None = None,
        tags: Sequence[str] | None = None,
    ) -> None:
        self._connector_id = connector_id
        self._payload_model = payload_model
        self._prefix = prefix or f"/{connector_id}"
        self._tags = tuple(tags) if tags is not None else (connector_id,)

    def build(self) -> APIRouter:
        payload_model = self._payload_model
        router = APIRouter(prefix=self._prefix, tags=list(self._tags))

        @router.post("/webhook", response_model=Ack)
        async def handle_webhook(
            payload: dict[str, Any],
            request: Request,
            debouncer: DebounceManager = Depends(get_debouncer),
            registry: ConnectorRegistry = Depends(get_connector_registry),
        ) -> Ack:
            connector = registry.require_inbound(self._connector_id)

            raw_body = payload
            if payload_model is not None:
                try:
                    validated = payload_model.model_validate(payload)
                except ValidationError as exc:
                    log.warning(
                        "connector.webhook.payload_invalid",
                        connector_id=self._connector_id,
                        error=str(exc),
                    )
                    raise HTTPException(status_code=422, detail="Invalid payload") from exc
                raw_body = validated.model_dump()

            try:
                normalized = await connector.normalize(
                    InboundPayload(
                        body=raw_body or {},
                        headers=dict(request.headers),
                        query_params=dict(request.query_params),
                    )
                )
            except ConnectorAuthError as exc:
                log.warning(
                    "connector.webhook.auth_failed",
                    connector_id=self._connector_id,
                    error=str(exc),
                )
                raise HTTPException(status_code=403, detail="Forbidden") from exc
            except ConnectorPayloadError as exc:
                log.warning(
                    "connector.webhook.payload_invalid",
                    connector_id=self._connector_id,
                    error=str(exc),
                )
                raise HTTPException(status_code=422, detail="Invalid payload") from exc

            window_seconds = debouncer.debounce_seconds
            for message in normalized:
                window_seconds = await debouncer.add_message(message)

            return Ack(ok=True, window_seconds=window_seconds)

        return router
