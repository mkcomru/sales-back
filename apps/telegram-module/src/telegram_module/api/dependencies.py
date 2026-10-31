from __future__ import annotations

from fastapi import Depends, Request

from telegram_module.bots.manager import BotManager
from telegram_module.config import Settings
from telegram_module.services.sales_agent import BackendInboundClient
from telegram_module.transport.manual_broadcast import ManualBroadcastService
from telegram_module.transport.service import TransportDeliveryService


def get_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:  # pragma: no cover - startup guard
        raise RuntimeError("Settings not initialised")
    return settings


def get_bot_manager(request: Request) -> BotManager:
    manager = getattr(request.app.state, "bot_manager", None)
    if manager is None:  # pragma: no cover - startup guard
        raise RuntimeError("Bot manager not initialised")
    return manager


def get_sales_agent_client(request: Request) -> BackendInboundClient:
    client = getattr(request.app.state, "sales_agent_client", None)
    if client is None:  # pragma: no cover - startup guard
        raise RuntimeError("Sales Agent client not initialised")
    return client


def get_transport_service(
    request: Request,
    _: BotManager = Depends(get_bot_manager),
) -> TransportDeliveryService:
    service = getattr(request.app.state, "transport_service", None)
    if service is None:  # pragma: no cover - startup guard
        raise RuntimeError("Transport service not initialised")
    return service


def get_manual_broadcast_service(
    request: Request,
    _: BotManager = Depends(get_bot_manager),
) -> ManualBroadcastService:
    service = getattr(request.app.state, "manual_broadcast_service", None)
    if service is None:  # pragma: no cover - startup guard
        raise RuntimeError("Manual broadcast service not initialised")
    return service
