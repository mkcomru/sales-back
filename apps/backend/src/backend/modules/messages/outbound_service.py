"""Outbound delivery service — single choke point for transport-bound messages.

Enriches transport addressing from Thread and delivers via TransportClient.
All outbound paths (agent replies, static pings, manager messages) should
route through this service to get consistent chat_id / conversation_id
enrichment from the authoritative Thread record.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from src.backend.modules.messages.transport_client import TransportClient

if TYPE_CHECKING:
    from src.backend.modules.chat.models import Thread
    from src.backend.modules.transport.models import Connector

log = structlog.get_logger(__name__)


class OutboundService:
    def __init__(self, transport_client: TransportClient) -> None:
        self._transport_client = transport_client

    async def deliver_to_thread(
        self,
        *,
        connector: Connector,
        thread: Thread,
        replies: list[str],
        correlation_id: str,
        metadata: dict[str, Any] | None = None,
        stage_id: str | None = None,
        handoff: dict[str, Any] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> None:
        """Enrich addressing from Thread and deliver to transport."""
        ext_conv = (thread.conversation_id or "").strip()
        enriched_meta = dict(metadata) if metadata else {}
        if ext_conv:
            enriched_meta["chat_id"] = ext_conv
            enriched_meta["user_id"] = ext_conv
            enriched_meta["conversation_id"] = ext_conv

        company_id: int | None = getattr(connector, "company_id", None)

        payload: dict[str, Any] = {
            "connector_id": connector.connector_id,
            "conversation_id": ext_conv,
            "correlation_id": correlation_id,
            "replies": replies,
            "metadata": enriched_meta,
            "channel_type": connector.channel_type,
            "company_id": str(company_id) if company_id is not None else "unknown",
            "user_id": ext_conv or "unknown",
        }
        if stage_id:
            payload["stage_id"] = stage_id
        if handoff:
            payload["handoff"] = handoff
        if attachments:
            payload["attachments"] = attachments

        await self._transport_client.deliver(connector=connector, payload=payload)
