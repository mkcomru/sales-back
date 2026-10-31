from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from common import SalesAgentSettings

from src.sales_agent.connectors.registry import ConnectorRegistry
from src.sales_agent.connectors.telegram.inbound import TelegramInboundConnector
from src.sales_agent.connectors.telegram.router import build_telegram_router
from src.sales_agent.connectors.wappi_hub.inbound import WappiHubInboundConnector
from src.sales_agent.connectors.wappi_hub.router import build_wappi_hub_router

log = structlog.get_logger(__name__)

if TYPE_CHECKING:
    from src.sales_agent.core.telemetry import Tracer


def build_connector_registry(settings: SalesAgentSettings, tracer: Tracer | None = None) -> ConnectorRegistry:
    """Instantiate available connector adapters and associated routers."""

    registry = ConnectorRegistry(tracer=tracer)
    for connector_key, connector_cfg in settings.connectors.items():
        connector_id = connector_cfg.connector_id or connector_key
        if not connector_cfg.enabled:
            log.info(
                "connector.registry.skipped",
                connector_id=connector_id,
                reason="disabled",
            )
            continue

        metadata = connector_cfg.metadata or {}
        provider = str(metadata.get("provider") or connector_id).lower()

        if provider == "telegram":
            inbound = TelegramInboundConnector(connector_cfg, default_window=settings.debounce.window_seconds)
            router = build_telegram_router(connector_id=inbound.connector_id)
            registry.register_inbound(inbound, router)
            log.info(
                "connector.registry.registered",
                connector_id=inbound.connector_id,
                connector_type=inbound.connector_type.value,
                channels=list(connector_cfg.channel_types or []),
                provider="telegram",
            )
        elif provider == "wappi-hub":
            inbound = WappiHubInboundConnector(connector_cfg, default_window=settings.debounce.window_seconds)
            router = build_wappi_hub_router(connector_id=inbound.connector_id)
            registry.register_inbound(inbound, router)
            log.info(
                "connector.registry.registered",
                connector_id=inbound.connector_id,
                connector_type=inbound.connector_type.value,
                channels=list(connector_cfg.channel_types or []),
                provider=provider,
            )
        else:
            log.warning(
                "connector.registry.unsupported_inbound",
                connector_id=connector_id,
                connector_type=connector_cfg.type,
                provider=provider,
            )

    return registry


def update_connector_registry(
    registry: ConnectorRegistry,
    settings: SalesAgentSettings,
    tracer: Tracer | None = None,
) -> None:
    """Update existing registry with new connectors from settings.

    Adds new connectors that are not yet registered, but does not remove
    existing ones to avoid breaking active connections.
    """
    for connector_key, connector_cfg in settings.connectors.items():
        connector_id = connector_cfg.connector_id or connector_key

        if registry.get_inbound(connector_id) is not None:
            continue

        if not connector_cfg.enabled:
            continue

        metadata = connector_cfg.metadata or {}
        provider = str(metadata.get("provider") or connector_id).lower()

        if provider == "telegram":
            inbound = TelegramInboundConnector(connector_cfg, default_window=settings.debounce.window_seconds)
            router = build_telegram_router(connector_id=inbound.connector_id)
            registry.register_inbound(inbound, router)
            log.info(
                "connector.registry.registered",
                connector_id=inbound.connector_id,
                connector_type=inbound.connector_type.value,
                channels=list(connector_cfg.channel_types or []),
                provider="telegram",
            )
        elif provider == "wappi-hub":
            inbound = WappiHubInboundConnector(connector_cfg, default_window=settings.debounce.window_seconds)
            router = build_wappi_hub_router(connector_id=inbound.connector_id)
            registry.register_inbound(inbound, router)
            log.info(
                "connector.registry.registered",
                connector_id=inbound.connector_id,
                connector_type=inbound.connector_type.value,
                channels=list(connector_cfg.channel_types or []),
                provider=provider,
            )
