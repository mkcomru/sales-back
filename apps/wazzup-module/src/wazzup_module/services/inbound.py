from __future__ import annotations

import time
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any

import httpx
import structlog

from common import AudioConversionService, FileType, InboundEnvelope, MessageRole
from wazzup_module.config import Settings
from wazzup_module.connectors.models import WazzupConnectorConfig
from wazzup_module.services.backend import WazzupBackendClient

log = structlog.get_logger(__name__)


class BackendInboundClientError(RuntimeError):
    """Raised when Backend inbound delivery fails."""


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_ts(value: Any) -> float:
    if not value:
        return time.time()
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=UTC).timestamp()
    except (ValueError, TypeError):
        return time.time()


def _input_format_from_content_type(content_type: str) -> str | None:
    if "ogg" in content_type:
        return "ogg"
    if "mpeg" in content_type or "mp3" in content_type:
        return "mp3"
    if "mp4" in content_type or "m4a" in content_type:
        return "mp4"
    if "webm" in content_type:
        return "webm"
    return None


class BackendInboundClient:
    """Forward Wazzup webhook updates to Backend inbound endpoint."""

    def __init__(
        self,
        settings: Settings,
        backend_client: WazzupBackendClient,
        audio_converter: AudioConversionService | None = None,
    ) -> None:
        backend_url = settings.backend.url
        if not backend_url:
            raise ValueError("Backend URL must be configured for wazzup-module")
        self._base_url = str(backend_url).rstrip("/")
        self._timeout = settings.request_timeout_s
        self._service_key = settings.service.api_key
        self._service_header = settings.service.resolved_header()
        self._backend_client = backend_client
        self._audio_converter = audio_converter

    async def forward_message(
        self,
        connector_id: str,
        connector: WazzupConnectorConfig,
        message: dict[str, Any],
    ) -> None:
        envelope = await self._normalize_message(message, connector)
        if envelope is None:
            return
        await self._send_envelope(connector_id, envelope)

    async def _send_envelope(
        self,
        connector_id: str,
        envelope: InboundEnvelope,
    ) -> None:
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
            raise BackendInboundClientError(f"Failed to forward message for connector '{connector_id}': {exc}") from exc

        if response.status_code not in (HTTPStatus.OK, HTTPStatus.ACCEPTED):
            raise BackendInboundClientError(f"Backend responded with status {response.status_code}: {response.text}")

    async def _normalize_message(
        self,
        message: dict[str, Any],
        connector: WazzupConnectorConfig,
    ) -> InboundEnvelope | None:
        if message.get("isDeleted") or message.get("isEdited"):
            return None

        is_echo: bool = message.get("isEcho", False)
        sent_from_app: bool = message.get("sentFromApp", False)

        if is_echo and not sent_from_app:
            return None

        role = MessageRole.MANAGER if (is_echo and sent_from_app) else MessageRole.USER

        chat_id = _as_str(message.get("chatId"))
        if not chat_id:
            log.warning("wazzup.normalize.no_chat_id")
            return None

        contact: dict[str, Any] = message.get("contact") or {}
        common_fields: dict[str, Any] = dict(
            conversation_id=chat_id,
            user_id=chat_id,
            ts=_parse_ts(message.get("dateTime")),
            role=role,
            is_historical=False,
            sender_name=_as_str(contact.get("name")),
            sender_username=_as_str(contact.get("username")),
            sender_phone=_as_str(contact.get("phone")),
            message_id=_as_str(message.get("messageId")),
            extra={"_manager_outgoing": True} if role == MessageRole.MANAGER else {},
        )

        if message.get("type") == "audio":
            content_uri = _as_str(message.get("contentUri"))
            if not content_uri:
                log.debug("wazzup.normalize.audio_no_uri")
                return None
            artifact_ids = await self._process_audio(content_uri, connector)
            return InboundEnvelope(**common_fields, text=None, artifact_ids=artifact_ids, audio=None)

        text = _as_str(message.get("text"))
        if not text:
            log.debug("wazzup.normalize.no_text", message_type=message.get("type"))
            return None

        return InboundEnvelope(**common_fields, text=text, artifact_ids=[], audio=None)

    async def _process_audio(
        self,
        content_uri: str,
        connector: WazzupConnectorConfig,
    ) -> list[str]:
        if self._audio_converter is None:
            log.warning("wazzup.audio.converter_not_configured", url=content_uri)
            return []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(content_uri)
                response.raise_for_status()
                file_bytes = response.content
                content_type = response.headers.get("content-type", "")
        except Exception as exc:
            log.warning("wazzup.audio.download_failed", url=content_uri, error=str(exc))
            return []

        input_format = _input_format_from_content_type(content_type)

        try:
            mp3_bytes = await self._audio_converter.convert_to_mp3(
                audio_bytes=file_bytes,
                input_format=input_format,
            )
        except Exception as exc:
            log.warning("wazzup.audio.conversion_failed", error=str(exc))
            return []

        try:
            artifact_id = await self._backend_client.upload_artifact(
                file_bytes=mp3_bytes,
                file_type=FileType.AUDIO,
                company_id=int(connector.company_id),
                connector_id=connector.connector_id,
            )
            return [artifact_id]
        except Exception as exc:
            log.warning("wazzup.audio.upload_failed", error=str(exc))
            return []
