from __future__ import annotations

import time
from http import HTTPStatus
from typing import Any

import httpx
import structlog

from common import InboundEnvelope, MessageRole
from telegram_module.bots.models import BotConfig
from telegram_module.config import Settings

log = structlog.get_logger(__name__)


class BackendInboundClientError(RuntimeError):
    """Raised when Backend inbound delivery fails."""


class BackendInboundClient:
    """Forward Telegram updates to Backend inbound endpoint.

    Uses unified InboundEnvelope format with service key auth (Plan 010).
    """

    def __init__(self, settings: Settings) -> None:
        backend_url = settings.backend.url
        if not backend_url:
            raise ValueError("Backend URL must be configured for telegram-module")
        self._base_url = str(backend_url).rstrip("/")
        self._timeout = settings.request_timeout_s
        self._service_key = settings.service.api_key
        self._service_header = settings.service.resolved_header()

    async def forward_update(self, connector_id: str, bot: BotConfig, update: dict[str, Any]) -> None:
        """Forward Telegram update to Backend using unified inbound endpoint.

        Normalizes Telegram update to InboundEnvelope format.
        """
        envelope = self._normalize_update(update)
        if envelope is None:
            log.debug(
                "sales_agent.forward.skipped",
                connector_id=connector_id,
                reason="unsupported_update",
            )
            return

        url = f"{self._base_url}/messages/inbound"
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "X-Connector-Id": connector_id,
        }
        if self._service_key:
            headers[self._service_header] = self._service_key.get_secret_value()

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=envelope.model_dump(mode="json"), headers=headers)
        except httpx.HTTPError as exc:
            raise BackendInboundClientError(f"Failed to forward update for connector '{connector_id}': {exc}") from exc

        if response.status_code not in (HTTPStatus.OK, HTTPStatus.ACCEPTED):
            raise BackendInboundClientError(f"Backend responded with status {response.status_code}: {response.text}")

        log.debug(
            "sales_agent.forward.accepted",
            connector_id=connector_id,
            company_id=bot.company_id,
            conversation_id=envelope.conversation_id,
            status_code=response.status_code,
            message="Backend accepted message (may be blocked by routing rules)",
        )

    def _normalize_update(self, update: dict[str, Any]) -> InboundEnvelope | None:
        """Normalize Telegram update to InboundEnvelope format."""
        message = self._extract_message(update)
        if message is None:
            return None

        chat = message.get("chat")
        if not isinstance(chat, dict):
            return None

        chat_id = chat.get("id")
        if chat_id is None:
            return None

        user = message.get("from")
        user_id = str(user.get("id")) if isinstance(user, dict) else str(chat_id)

        text = message.get("text") or message.get("caption")

        artifact_ids = message.get("artifact_ids", [])

        ts_raw = message.get("date")
        ts = float(ts_raw) if isinstance(ts_raw, (int, float)) else time.time()

        # Extract sender info: prefer `from` (user), fall back to `chat` (private chats always have first_name)
        sender_name: str | None = None
        sender_username: str | None = None
        sender_phone: str | None = None
        if isinstance(user, dict):
            sender_name = user.get("first_name") or None
            sender_username = user.get("username")
            sender_phone = user.get("phone_number")
        elif isinstance(chat, dict):
            sender_name = chat.get("first_name") or None
            sender_username = chat.get("username")

        return InboundEnvelope(
            conversation_id=str(chat_id),
            user_id=user_id,
            text=text,
            ts=ts,
            artifact_ids=artifact_ids if isinstance(artifact_ids, list) else [],
            role=MessageRole.USER,  # Telegram bots only receive user messages
            is_historical=False,
            sender_name=sender_name,
            sender_username=sender_username,
            sender_phone=sender_phone,
        )

    def _extract_message(self, update: dict[str, Any]) -> dict[str, Any] | None:
        """Extract message payload from Telegram update."""
        for key in ("message", "edited_message", "channel_post", "edited_channel_post"):
            candidate = update.get(key)
            if isinstance(candidate, dict):
                return candidate

        callback = update.get("callback_query")
        if isinstance(callback, dict):
            msg = callback.get("message")
            if isinstance(msg, dict):
                return msg

        return None
