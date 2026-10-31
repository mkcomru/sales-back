from __future__ import annotations

import asyncio
import mimetypes
from collections.abc import Mapping
from typing import Any

import structlog
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import BufferedInputFile
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse

from common.models.transport import AttachmentDescriptor, TransportDeliveryPayload
from common.transport.base_backend_client import TransportBackendClientError
from common.transport.base_delivery import BaseTransportDeliveryService
from telegram_module.bots.manager import BotManager, BotRuntime
from telegram_module.config import Settings
from telegram_module.services.backend import TransportBackendClient

log = structlog.get_logger(__name__)


def _as_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


class TransportDeliveryError(RuntimeError):
    """Raised when telegram transport delivery fails after retries."""


class _IdempotencyStore:
    """In-memory tracker preventing duplicate correlation deliveries."""

    def __init__(self, ttl_seconds: float = 86_400.0) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def reserve(self, key: str) -> bool:
        """Store key if absent; return False when key still active."""

        async with self._lock:
            now = asyncio.get_running_loop().time()
            self._purge(now)
            expires_at = self._entries.get(key)
            if expires_at is not None and expires_at > now:
                return False
            self._entries[key] = now + self._ttl
            return True

    def _purge(self, now: float) -> None:
        expired = [key for key, expires in self._entries.items() if expires <= now]
        for key in expired:
            self._entries.pop(key, None)


class TransportDeliveryService(BaseTransportDeliveryService):
    """Handle deliveries from Sales Agent to Telegram Bot API."""

    def __init__(self, settings: Settings, bots: BotManager, backend_client: TransportBackendClient) -> None:
        self._settings = settings
        self._bots = bots
        self._backend_client = backend_client
        self._idempotency = _IdempotencyStore()
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
        payload: TransportDeliveryPayload,
        headers: Mapping[str, str],
    ) -> JSONResponse:
        runtime = self._bots.get(payload.connector_id)
        if runtime is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unknown connector_id '{payload.connector_id}'",
            )

        normalized_headers = {key.lower(): value for key, value in headers.items()}
        connector_header = normalized_headers.get(self._connector_header)
        if connector_header is None:
            log.warning(
                "transport.delivery.missing_connector_header",
                connector_id=payload.connector_id,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing connector header",
            )
        if connector_header.strip() != payload.connector_id:
            log.warning(
                "transport.delivery.connector_mismatch",
                connector_id=payload.connector_id,
                header_value=connector_header,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Connector header mismatch",
            )

        provided_key = normalized_headers.get(self._service_header)
        if provided_key is None:
            log.warning(
                "transport.delivery.missing_service_key",
                connector_id=payload.connector_id,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing service credentials",
            )
        if provided_key != self._service_key:
            log.warning(
                "transport.delivery.invalid_service_key",
                connector_id=payload.connector_id,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid service credentials",
            )

        correlation_id = payload.correlation_id.strip()
        if not correlation_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Correlation id must be provided",
            )

        is_new = await self._idempotency.reserve(f"{payload.connector_id}:{correlation_id}")
        if not is_new:
            log.info(
                "transport.delivery.duplicate",
                connector_id=payload.connector_id,
                company_id=payload.company_id,
                correlation_id=payload.correlation_id,
            )
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "status": "duplicate",
                    "connector_id": payload.connector_id,
                    "correlation_id": payload.correlation_id,
                },
            )

        try:
            await self._deliver_replies(runtime, payload)
        except TransportDeliveryError as exc:
            log.error(
                "transport.delivery.failed",
                connector_id=payload.connector_id,
                company_id=payload.company_id,
                correlation_id=payload.correlation_id,
                error=str(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to deliver to Telegram",
            ) from exc

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "status": "accepted",
                "connector_id": payload.connector_id,
                "correlation_id": payload.correlation_id,
            },
        )

    async def _deliver_replies(self, runtime: BotRuntime, payload: TransportDeliveryPayload) -> None:
        metadata = payload.metadata or {}
        extra = metadata.get("extra")
        if isinstance(extra, Mapping):
            extra_meta = dict(extra)
        else:
            extra_meta = {}

        chat_id = metadata.get("chat_id") or extra_meta.get("chat_id")
        if not chat_id:
            raise TransportDeliveryError("Missing chat_id in metadata")

        message_thread_id = metadata.get("message_thread_id") or extra_meta.get("message_thread_id")
        reply_to_message_id = metadata.get("reply_to_message_id") or extra_meta.get("reply_to_message_id")
        allow_without_reply = _as_bool(
            metadata.get("allow_sending_without_reply") or extra_meta.get("allow_sending_without_reply")
        )
        disable_notification = _as_bool(metadata.get("disable_notification") or extra_meta.get("disable_notification"))
        disable_web_preview = _as_bool(
            metadata.get("disable_web_page_preview") or extra_meta.get("disable_web_page_preview")
        )
        attempts_limit = self._settings.max_delivery_attempts

        for index, reply in enumerate(payload.replies):
            text = reply.strip()
            if not text:
                continue
            params: dict[str, Any] = {"chat_id": chat_id, "text": text}
            if message_thread_id is not None:
                params["message_thread_id"] = message_thread_id
            if reply_to_message_id is not None:
                params["reply_to_message_id"] = reply_to_message_id
            if allow_without_reply is not None:
                params["allow_sending_without_reply"] = allow_without_reply
            if disable_notification is True:
                params["disable_notification"] = True
            if disable_web_preview is not None:
                params["disable_web_page_preview"] = disable_web_preview

            await self._send_with_retry(
                runtime,
                params,
                attempts_limit=attempts_limit,
                delivery_index=index,
                payload=payload,
            )

        for attachment in payload.attachments or []:
            await self._deliver_attachment(
                runtime=runtime,
                chat_id=chat_id,
                message_thread_id=message_thread_id,
                attachment=attachment,
                attempts_limit=attempts_limit,
                payload=payload,
            )

    async def _send_with_retry(
        self,
        runtime: BotRuntime,
        params: dict[str, Any],
        *,
        attempts_limit: int,
        delivery_index: int,
        payload: TransportDeliveryPayload,
    ) -> None:
        attempt = 0
        while True:
            attempt += 1
            try:
                await runtime.bot.send_message(**params)
                log.info(
                    "transport.delivery.delivered",
                    connector_id=payload.connector_id,
                    company_id=payload.company_id,
                    correlation_id=payload.correlation_id,
                    delivery_index=delivery_index,
                    attempt=attempt,
                )
                return
            except TelegramRetryAfter as exc:
                delay = max(1.0, float(exc.retry_after))
                log.warning(
                    "transport.delivery.retry_after",
                    connector_id=payload.connector_id,
                    delay=delay,
                    attempt=attempt,
                )
            except TelegramServerError as exc:
                delay = min(5.0 * attempt, 30.0)
                log.warning(
                    "transport.delivery.server_error",
                    connector_id=payload.connector_id,
                    attempt=attempt,
                    error=str(exc),
                )
            except TelegramBadRequest as exc:
                # AICODE-NOTE: Bad requests are permanent, retrying would spam the API.
                raise TransportDeliveryError(f"Telegram API rejected payload: {exc}") from exc
            except Exception as exc:
                raise TransportDeliveryError(f"Unexpected Telegram error: {exc}") from exc

            if attempt >= attempts_limit:
                raise TransportDeliveryError("Exceeded delivery retry limit")

            await asyncio.sleep(delay)

    async def _deliver_attachment(
        self,
        *,
        runtime: BotRuntime,
        chat_id: Any,
        message_thread_id: Any,
        attachment: AttachmentDescriptor,
        attempts_limit: int,
        payload: TransportDeliveryPayload,
    ) -> None:
        try:
            file_bytes = await self._backend_client.download_artifact(attachment.artifact_id)
        except TransportBackendClientError as exc:
            raise TransportDeliveryError(f"Failed to download artifact {attachment.artifact_id}: {exc}") from exc

        attempt = 0
        delay = 0.0
        while True:
            attempt += 1
            try:
                await self._send_attachment(
                    runtime=runtime,
                    chat_id=chat_id,
                    message_thread_id=message_thread_id,
                    attachment=attachment,
                    file_bytes=file_bytes,
                )
                log.info(
                    "transport.delivery.attachment_delivered",
                    connector_id=payload.connector_id,
                    artifact_id=attachment.artifact_id,
                    attachment_type=attachment.type,
                    attempt=attempt,
                )
                return
            except TelegramRetryAfter as exc:
                delay = max(1.0, float(exc.retry_after))
                log.warning(
                    "transport.delivery.attachment_retry_after",
                    connector_id=payload.connector_id,
                    artifact_id=attachment.artifact_id,
                    delay=delay,
                    attempt=attempt,
                )
            except TelegramServerError as exc:
                delay = min(5.0 * attempt, 30.0)
                log.warning(
                    "transport.delivery.attachment_server_error",
                    connector_id=payload.connector_id,
                    artifact_id=attachment.artifact_id,
                    attachment_type=attachment.type,
                    attempt=attempt,
                    error=str(exc),
                )
            except TelegramBadRequest as exc:
                raise TransportDeliveryError(f"Telegram API rejected attachment: {exc}") from exc
            except Exception as exc:
                raise TransportDeliveryError(f"Unexpected Telegram error sending attachment: {exc}") from exc

            if attempt >= attempts_limit:
                raise TransportDeliveryError("Exceeded attachment delivery retry limit")

            await asyncio.sleep(delay)

    async def _send_attachment(
        self,
        *,
        runtime: BotRuntime,
        chat_id: Any,
        message_thread_id: Any,
        attachment: AttachmentDescriptor,
        file_bytes: bytes,
    ) -> None:
        ext = mimetypes.guess_extension(attachment.mime_type, strict=False) or ""
        kwargs: dict[str, Any] = {"chat_id": chat_id}
        if message_thread_id is not None:
            kwargs["message_thread_id"] = message_thread_id
        if attachment.caption is not None:
            kwargs["caption"] = attachment.caption

        match attachment.type:
            case "image":
                await runtime.bot.send_photo(
                    **kwargs,
                    photo=BufferedInputFile(file_bytes, filename=f"photo{ext}"),
                )
            case "audio":
                await runtime.bot.send_audio(
                    **kwargs,
                    audio=BufferedInputFile(file_bytes, filename=f"audio{ext}"),
                )
            case "voice":
                await runtime.bot.send_voice(
                    **kwargs,
                    voice=BufferedInputFile(file_bytes, filename=f"voice{ext}"),
                )
            case "document":
                await runtime.bot.send_document(
                    **kwargs,
                    document=BufferedInputFile(file_bytes, filename=f"document{ext}"),
                )
            case _:
                raise TransportDeliveryError(f"Unsupported attachment type for Telegram: {attachment.type}")
