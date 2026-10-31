from __future__ import annotations

import asyncio
from typing import Any

import structlog
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramRetryAfter,
    TelegramServerError,
)
from pydantic import BaseModel, Field

from telegram_module.bots.manager import BotManager, BotRuntime
from telegram_module.config import Settings

log = structlog.get_logger(__name__)


class BroadcastMessage(BaseModel):
    text: str
    disable_notification: bool = False
    disable_web_page_preview: bool = False


class BroadcastRecipient(BaseModel):
    recipient_id: str
    chat_id: str | int


class ManualBroadcastRequest(BaseModel):
    connector_id: str
    message: BroadcastMessage
    recipients: list[BroadcastRecipient] = Field(min_length=1)


class RecipientResult(BaseModel):
    recipient_id: str
    chat_id: str | int
    status: str
    error: str | None = None
    telegram_message_id: int | None = None
    conversation_id: str | None = None


class ManualBroadcastResponse(BaseModel):
    total_sent: int
    total_failed: int
    recipients: list[RecipientResult]


class ManualBroadcastService:
    """Handle manual broadcast deliveries to Telegram Bot API."""

    def __init__(self, settings: Settings, bots: BotManager) -> None:
        self._settings = settings
        self._bots = bots
        header = settings.service.resolved_header()
        self._service_header = header.lower()
        api_key = settings.service.api_key
        if api_key is None:
            raise RuntimeError("SERVICE__API_KEY must be configured for transport")
        self._service_key = api_key.get_secret_value()
        self._connector_header = "x-connector-id"

    async def handle(
        self,
        *,
        request: ManualBroadcastRequest,
        headers: dict[str, str],
    ) -> ManualBroadcastResponse:
        runtime = self._bots.get(request.connector_id)
        if runtime is None:
            raise ValueError(f"Unknown connector_id '{request.connector_id}'")

        normalized_headers = {key.lower(): value for key, value in headers.items()}
        connector_header = normalized_headers.get(self._connector_header)
        if connector_header is None:
            log.warning(
                "manual_broadcast.missing_connector_header",
                connector_id=request.connector_id,
            )
            raise ValueError("Missing connector header")
        if connector_header.strip() != request.connector_id:
            log.warning(
                "manual_broadcast.connector_mismatch",
                connector_id=request.connector_id,
                header_value=connector_header,
            )
            raise ValueError("Connector header mismatch")

        provided_key = normalized_headers.get(self._service_header)
        if provided_key is None:
            log.warning(
                "manual_broadcast.missing_service_key",
                connector_id=request.connector_id,
            )
            raise ValueError("Missing service credentials")
        if provided_key != self._service_key:
            log.warning(
                "manual_broadcast.invalid_service_key",
                connector_id=request.connector_id,
            )
            raise ValueError("Invalid service credentials")

        results: list[RecipientResult] = []
        total_sent = 0
        total_failed = 0

        for recipient in request.recipients:
            result = await self._send_to_recipient(runtime, request.message, recipient)
            results.append(result)
            if result.status == "delivered":
                total_sent += 1
            else:
                total_failed += 1

        return ManualBroadcastResponse(
            total_sent=total_sent,
            total_failed=total_failed,
            recipients=results,
        )

    async def _send_to_recipient(
        self,
        runtime: BotRuntime,
        message: BroadcastMessage,
        recipient: BroadcastRecipient,
    ) -> RecipientResult:
        params: dict[str, Any] = {
            "chat_id": recipient.chat_id,
            "text": message.text,
        }
        if message.disable_notification:
            params["disable_notification"] = True
        if message.disable_web_page_preview:
            params["disable_web_page_preview"] = True

        attempts_limit = self._settings.max_delivery_attempts
        attempt = 0

        while True:
            attempt += 1
            try:
                sent_message = await runtime.bot.send_message(**params)
                telegram_message_id = sent_message.message_id
                conversation_id = f"{recipient.chat_id}:{telegram_message_id}"

                log.info(
                    "manual_broadcast.delivered",
                    connector_id=runtime.config.connector_id,
                    recipient_id=recipient.recipient_id,
                    chat_id=recipient.chat_id,
                    telegram_message_id=telegram_message_id,
                    attempt=attempt,
                )

                return RecipientResult(
                    recipient_id=recipient.recipient_id,
                    chat_id=recipient.chat_id,
                    status="delivered",
                    telegram_message_id=telegram_message_id,
                    conversation_id=conversation_id,
                )
            except TelegramRetryAfter as exc:
                delay = max(1.0, float(exc.retry_after))
                log.warning(
                    "manual_broadcast.retry_after",
                    connector_id=runtime.config.connector_id,
                    recipient_id=recipient.recipient_id,
                    delay=delay,
                    attempt=attempt,
                )
            except TelegramServerError as exc:
                delay = min(5.0 * attempt, 30.0)
                log.warning(
                    "manual_broadcast.server_error",
                    connector_id=runtime.config.connector_id,
                    recipient_id=recipient.recipient_id,
                    attempt=attempt,
                    error=str(exc),
                )
            except TelegramBadRequest as exc:
                error_msg = str(exc)
                log.error(
                    "manual_broadcast.bad_request",
                    connector_id=runtime.config.connector_id,
                    recipient_id=recipient.recipient_id,
                    error=error_msg,
                )
                return RecipientResult(
                    recipient_id=recipient.recipient_id,
                    chat_id=recipient.chat_id,
                    status="failed",
                    error=error_msg,
                )
            except Exception as exc:
                error_msg = str(exc)
                log.error(
                    "manual_broadcast.unexpected_error",
                    connector_id=runtime.config.connector_id,
                    recipient_id=recipient.recipient_id,
                    error=error_msg,
                )
                return RecipientResult(
                    recipient_id=recipient.recipient_id,
                    chat_id=recipient.chat_id,
                    status="failed",
                    error=error_msg,
                )

            if attempt >= attempts_limit:
                return RecipientResult(
                    recipient_id=recipient.recipient_id,
                    chat_id=recipient.chat_id,
                    status="failed",
                    error="Exceeded delivery retry limit",
                )

            await asyncio.sleep(delay)
