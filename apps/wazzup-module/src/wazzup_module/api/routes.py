from __future__ import annotations

import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from wazzup_module.api.dependencies import (
    get_connector_manager,
    get_inbound_client,
    get_transport_service,
)
from wazzup_module.connectors.manager import ConnectorManager
from wazzup_module.services.inbound import BackendInboundClient
from wazzup_module.transport.models import TransportDeliveryPayload
from wazzup_module.transport.service import TransportDeliveryService

log = structlog.get_logger(__name__)

transport_router = APIRouter(tags=["transport"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])
health_router = APIRouter(tags=["health"])
wazzup_router = APIRouter(prefix="/wazzup", tags=["wazzup"])


@transport_router.post(
    "/transport/delivery",
    status_code=status.HTTP_202_ACCEPTED,
)
async def transport_delivery(
    request: Request,
    service: TransportDeliveryService = Depends(get_transport_service),
) -> dict[str, str]:
    raw_body = await request.body()
    try:
        data = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    try:
        payload = TransportDeliveryPayload.model_validate(data)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return await service.handle(payload=payload, headers=dict(request.headers))


@admin_router.post("/reload", status_code=status.HTTP_202_ACCEPTED)
async def reload_connectors(
    manager: ConnectorManager = Depends(get_connector_manager),
) -> dict[str, str]:
    await manager.reload()
    return {"status": "reloaded"}


@health_router.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@wazzup_router.get("/webhook", status_code=status.HTTP_200_OK)
async def wazzup_webhook_validate() -> dict[str, str]:
    return {"status": "ok"}


@wazzup_router.post("/webhook", status_code=status.HTTP_200_OK)
async def wazzup_webhook(
    request: Request,
    manager: ConnectorManager = Depends(get_connector_manager),
    inbound_client: BackendInboundClient = Depends(get_inbound_client),
) -> dict[str, str]:
    try:
        payload = await request.json()
    except Exception as exc:
        log.warning("wazzup.webhook.invalid_json", error=str(exc))
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    if payload.get("test"):
        log.info("wazzup.webhook.test_ping")
        return {"status": "ok"}

    log.info(
        "wazzup.webhook.received",
        payload_keys=list(payload.keys()) if isinstance(payload, dict) else [],
    )

    messages = payload.get("messages", [])
    if not isinstance(messages, list):
        return {"status": "no_messages"}

    for msg in messages:
        if not isinstance(msg, dict):
            continue

        channel_id = msg.get("channelId")
        if not channel_id:
            log.debug("wazzup.webhook.no_channel_id", msg_keys=list(msg.keys()))
            continue

        connector = manager.get_by_channel_id(channel_id)
        if connector is None:
            log.warning("wazzup.webhook.connector_not_found", channel_id=channel_id)
            continue

        try:
            await inbound_client.forward_message(connector.connector_id, connector, msg)
        except Exception as exc:
            log.error(
                "wazzup.webhook.forward_failed",
                connector_id=connector.connector_id,
                error=str(exc),
            )

    return {"status": "forwarded"}
