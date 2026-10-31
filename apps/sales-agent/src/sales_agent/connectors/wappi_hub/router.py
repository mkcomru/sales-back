from __future__ import annotations

from fastapi import APIRouter

from src.sales_agent.connectors.http import GenericWebhookRouter


def build_wappi_hub_router(connector_id: str) -> APIRouter:
    """Create webhook endpoint backed by Wappi hub inbound connector."""
    builder = GenericWebhookRouter(
        connector_id=connector_id,
        prefix=f"/{connector_id}",
        tags=("wappi-hub", connector_id),
    )
    return builder.build()
