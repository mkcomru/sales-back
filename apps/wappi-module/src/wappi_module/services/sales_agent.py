from __future__ import annotations

import base64
import time
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

import httpx
import structlog

from common import AudioConversionService, AudioData, FileType, InboundEnvelope, MessageRole
from wappi_module.config import Settings
from wappi_module.connectors.models import WappiConnectorConfig
from wappi_module.services.backend import WappiBackendClient, WappiBackendClientError

log = structlog.get_logger(__name__)


class BackendInboundClientError(RuntimeError):
    """Raised when Backend inbound delivery fails."""


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class BackendInboundClient:
    """Forward Wappi updates to Backend inbound endpoint.

    Uses unified InboundEnvelope format with service key auth (Plan 010).
    Normalizes wappi webhook messages before forwarding.
    """

    def __init__(self, settings: Settings, backend_client: WappiBackendClient | None = None) -> None:
        backend_url = settings.backend.url
        if not backend_url:
            raise ValueError("Backend URL must be configured for wappi-module")
        self._base_url = str(backend_url).rstrip("/")
        self._timeout = settings.request_timeout_s
        self._service_key = settings.service.api_key
        self._service_header = settings.service.resolved_header()
        self._backend_client = backend_client
        self._audio_converter = AudioConversionService()

    async def forward_update(
        self,
        connector_id: str,
        connector: WappiConnectorConfig,
        update: dict[str, Any],
    ) -> None:
        """Forward Wappi webhook to Backend using unified inbound endpoint.

        Normalizes each message in the payload to InboundEnvelope format.
        """
        messages = update.get("messages", [])
        if not isinstance(messages, list):
            log.warning(
                "sales_agent.forward.no_messages",
                connector_id=connector_id,
            )
            return

        company_id = int(connector.company_id)

        for msg in messages:
            if not isinstance(msg, Mapping):
                continue

            envelope = await self._normalize_message(msg, connector.channel_type, company_id, connector_id)
            if envelope is None:
                continue

            await self._send_envelope(connector_id, envelope)

        log.debug(
            "sales_agent.forward.success",
            connector_id=connector_id,
            company_id=connector.company_id,
            messages_count=len(messages),
        )

    async def _send_envelope(
        self,
        connector_id: str,
        envelope: InboundEnvelope,
    ) -> None:
        """Send single InboundEnvelope to Sales Agent."""
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

    @staticmethod
    def _pre_normalize_message(message: Mapping[str, Any], channel_type: str) -> dict[str, Any]:
        """Translate platform-specific message quirks into canonical form.

        VK delivers audio as type="document" with attachments[].type="audio_message".
        We remap it to type="ptt" + file_link so the standard voice pipeline handles it.
        """
        normalized = dict(message)
        if "vk" not in channel_type.lower() or normalized.get("type") != "document":
            return normalized
        attachments = normalized.get("attachments") or []
        vk_audio = next((a for a in attachments if a.get("type") == "audio_message"), None)
        if not vk_audio:
            return normalized
        audio_url = _as_str(vk_audio.get("url"))
        if not audio_url:
            return normalized
        ext = (_as_str(vk_audio.get("ext")) or "mp3").lower()
        normalized["type"] = "ptt"
        normalized["file_link"] = audio_url
        normalized["mimetype"] = f"audio/{ext}"
        return normalized

    async def _normalize_message(
        self,
        message: Mapping[str, Any],
        channel_type: str,
        company_id: int,
        connector_id: str,
    ) -> InboundEnvelope | None:
        """Normalize wappi message to InboundEnvelope format."""
        message = self._pre_normalize_message(message, channel_type)
        msg_type = _as_str(message.get("type"))

        from_me = message.get("fromMe", False)
        is_me = message.get("is_me", False)
        is_manager_outgoing = message.get("_manager_outgoing", False)
        is_sync_mode = message.get("_sync_mode", False)

        # Skip outgoing messages UNLESS they have _manager_outgoing flag
        if (from_me or is_me) and not is_manager_outgoing:
            log.debug(
                "sales_agent.normalize.skip_outgoing",
                message_type=msg_type,
            )
            return None

        # Determine text/audio based on channel and message type
        text: str | None = None
        artifact_ids: list[str] = []
        audio_data: AudioData | None = None

        is_telegram = "telegram" in channel_type.lower()
        is_whatsapp = "whatsapp" in channel_type.lower() or "whats_app" in channel_type.lower()
        is_vk = "vk" in channel_type.lower()

        # Text messages
        if is_telegram and msg_type == "text":
            text = _as_str(message.get("body"))
        elif is_whatsapp and msg_type == "chat":
            text = _as_str(message.get("body"))
        elif is_vk and msg_type in ("chat", "text"):
            text = _as_str(message.get("body"))

        # Voice messages (ptt = push-to-talk)
        if msg_type == "ptt":
            audio_bytes: bytes | None = None
            mime_type: str | None = None
            audio_base64_raw: str | None = None

            # Try to get audio from file_link (URL) first
            file_link = _as_str(message.get("file_link"))
            if file_link:
                try:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.get(file_link)
                        response.raise_for_status()
                        audio_bytes = response.content
                        mime_type = (
                            _as_str(message.get("mimetype")) or response.headers.get("content-type") or "audio/ogg"
                        )
                        log.debug(
                            "wappi.voice.downloaded",
                            message_id=message.get("id"),
                            url=file_link,
                            size_bytes=len(audio_bytes),
                        )
                except (httpx.HTTPError, Exception) as e:
                    log.warning(
                        "wappi.voice.download_failed",
                        message_id=message.get("id"),
                        url=file_link,
                        error=str(e),
                    )

            # Fallback to base64 in body if file_link failed or not present
            if not audio_bytes:
                audio_base64_raw = message.get("body")
                if audio_base64_raw:
                    try:
                        audio_bytes = base64.b64decode(audio_base64_raw)
                        mime_type = _as_str(message.get("mimetype")) or "audio/ogg"
                    except Exception as e:
                        log.warning(
                            "wappi.voice.base64_decode_failed",
                            message_id=message.get("id"),
                            error=str(e),
                        )

            # Process audio if we have it
            if audio_bytes:
                try:
                    if mime_type and "mp3" in mime_type.lower():
                        mp3_bytes = audio_bytes
                    else:
                        input_format = "ogg" if mime_type and "ogg" in mime_type.lower() else "mpeg"
                        mp3_bytes = await self._audio_converter.convert_to_mp3(
                            audio_bytes=audio_bytes,
                            input_format=input_format,
                            timeout_s=60.0,
                        )

                    # Upload to Backend S3
                    if not self._backend_client:
                        raise ValueError("Backend client is required for artifact upload")
                    artifact_id = await self._backend_client.upload_artifact(
                        file_bytes=mp3_bytes,
                        file_type=FileType.VOICE,
                        company_id=company_id,
                        connector_id=connector_id,
                    )
                    artifact_ids.append(artifact_id)

                    log.info(
                        "wappi.voice.processed",
                        message_id=message.get("id"),
                        artifact_id=artifact_id,
                        original_size_bytes=len(audio_bytes),
                        mp3_size_bytes=len(mp3_bytes),
                    )
                except (WappiBackendClientError, Exception) as e:
                    log.warning(
                        "wappi.voice.processing_failed",
                        message_id=message.get("id"),
                        error=str(e),
                    )
                    # Fallback to raw audio data when conversion/upload fails
                    if audio_base64_raw:
                        audio_data = AudioData(
                            bytes_base64=audio_base64_raw,
                            mime=mime_type or "audio/ogg",
                        )
                    elif audio_bytes:
                        # Re-encode if we only have bytes (from file_link)
                        audio_data = AudioData(
                            bytes_base64=base64.b64encode(audio_bytes).decode("utf-8"),
                            mime=mime_type or "audio/ogg",
                        )

        # Skip if no text, no artifacts, and no audio
        if not text and not artifact_ids and not audio_data:
            unsupported = msg_type not in (None, "text", "chat", "ptt")
            if unsupported:
                log.debug(
                    "sales_agent.normalize.unsupported_type",
                    message_type=msg_type,
                )
            return None

        # Extract conversation/user IDs
        from_field = _as_str(message.get("from"))
        chat_id = _as_str(message.get("chatId"))
        profile_id = _as_str(message.get("profile_id"))

        if is_telegram:
            conversation_id = chat_id or from_field or profile_id
        else:
            conversation_id = chat_id or from_field or profile_id

        if not conversation_id:
            log.warning("sales_agent.normalize.no_conversation_id")
            return None

        user_id = conversation_id

        ts_raw = message.get("time")
        ts = float(ts_raw) if isinstance(ts_raw, (int, float)) else time.time()

        # Determine role from flags
        role = MessageRole.MANAGER if is_manager_outgoing else MessageRole.USER

        # Extract sender info
        contact_name = _as_str(message.get("contact_name"))
        contact_username = _as_str(message.get("contact_username"))
        contact_phone = _as_str(message.get("contact_phone"))

        # Preserve extra dict for backward compatibility during transition
        extra: dict[str, Any] = {}
        if "_manager_outgoing" in message:
            extra["_manager_outgoing"] = message["_manager_outgoing"]
        if "_sync_mode" in message:
            extra["_sync_mode"] = message["_sync_mode"]
        if "fromMe" in message:
            extra["fromMe"] = message["fromMe"]
        if contact_name:
            extra["contact_name"] = contact_name

        return InboundEnvelope(
            conversation_id=conversation_id,
            user_id=user_id,
            text=text,
            ts=ts,
            artifact_ids=artifact_ids,
            audio=audio_data,
            message_id=_as_str(message.get("id")),
            role=role,
            is_historical=bool(is_sync_mode),
            sender_name=contact_name,
            sender_username=contact_username,
            sender_phone=contact_phone,
            extra=extra,
        )
