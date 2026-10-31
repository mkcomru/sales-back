from __future__ import annotations

import json
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, Request, status

from telegram_module.api.dependencies import (
    get_bot_manager,
    get_manual_broadcast_service,
    get_transport_service,
)
from telegram_module.bots.manager import BotManager
from telegram_module.bots.models import BotMode
from telegram_module.transport.manual_broadcast import (
    ManualBroadcastRequest,
    ManualBroadcastResponse,
    ManualBroadcastService,
)
from telegram_module.transport.models import TransportDeliveryPayload
from telegram_module.transport.service import TransportDeliveryService

transport_router = APIRouter(tags=["transport"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])
health_router = APIRouter(tags=["health"])
telegram_router = APIRouter(prefix="/telegram", tags=["telegram"])


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


@transport_router.post(
    "/transport/broadcasts/manual",
    status_code=status.HTTP_200_OK,
)
async def manual_broadcast(
    payload: ManualBroadcastRequest,
    request: Request,
    service: ManualBroadcastService = Depends(get_manual_broadcast_service),
) -> ManualBroadcastResponse:
    try:
        return await service.handle(request=payload, headers=dict(request.headers))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@admin_router.post("/reload", status_code=status.HTTP_202_ACCEPTED)
async def reload_bots(manager: BotManager = Depends(get_bot_manager)) -> dict[str, str]:
    await manager.reload()
    return {"status": "reloaded"}


@health_router.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@telegram_router.post("/{connector_id}/webhook", status_code=HTTPStatus.ACCEPTED)
async def telegram_webhook(
    connector_id: str,
    request: Request,
    manager: BotManager = Depends(get_bot_manager),
) -> dict[str, str]:
    runtime = manager.get(connector_id)
    if runtime is None:
        raise HTTPException(status_code=404, detail="Unknown connector")
    if runtime.mode != BotMode.WEBHOOK:
        raise HTTPException(status_code=409, detail="Connector not in webhook mode")
    if runtime.config.webhook_secret is None:
        raise HTTPException(status_code=403, detail="Webhook secret not configured")

    headers = {key.lower(): value for key, value in request.headers.items()}
    provided_secret = headers.get("x-telegram-bot-api-secret-token")
    expected_secret = runtime.config.webhook_secret.get_secret_value()
    if provided_secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    await runtime.handle_raw_update(payload)
    # Sales Agent forwarder is invoked via dispatcher handler
    return {"status": "forwarded"}
