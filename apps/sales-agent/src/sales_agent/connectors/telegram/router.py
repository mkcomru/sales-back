from __future__ import annotations

from fastapi import APIRouter

from src.sales_agent.connectors.http import GenericWebhookRouter


def build_telegram_router(connector_id: str) -> APIRouter:
    """Create a simple webhook endpoint backed by Telegram inbound connector."""
    builder = GenericWebhookRouter(
        connector_id=connector_id,
        prefix=f"/{connector_id}",
        tags=("telegram", connector_id),
    )
    return builder.build()
