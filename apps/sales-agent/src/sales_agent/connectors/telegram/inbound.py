from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any

import structlog
from pydantic import SecretStr

from common.config import ConnectorSettings

from src.sales_agent.connectors.base import (
    ConnectorAuthError,
    ConnectorPayloadError,
    ConnectorType,
    InboundConnector,
    InboundPayload,
)
from src.sales_agent.services.debounce import IncomingMessage

log = structlog.get_logger(__name__)


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _pick_best_photo(items: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    if not items:
        return {}
    return max(
        items,
        key=lambda item: item.get("file_size") or item.get("width", 0) * item.get("height", 0),
    )


def _extract_message(
    update: Mapping[str, Any],
) -> tuple[Mapping[str, Any] | None, str | None]:
    for key in (
        "message",
        "edited_message",
        "channel_post",
        "edited_channel_post",
        "callback_query",
    ):
        candidate = update.get(key)
        if isinstance(candidate, Mapping):
            if key == "callback_query":
                message = candidate.get("message")
                if isinstance(message, Mapping):
                    return message, key
                continue
            return candidate, key
    return None, None


class TelegramInboundConnector(InboundConnector):
    """Normalizes Telegram webhook updates into internal IncomingMessage objects."""

    def __init__(self, settings: ConnectorSettings, *, default_window: int) -> None:
        self._settings = settings
        self._default_window = default_window
        self._connector_id = settings.connector_id or "telegram"
        try:
            self._connector_type = ConnectorType(settings.type)
        except ValueError:
            self._connector_type = ConnectorType.MESSAGING

        if settings.channel_types:
            self._channel_type = settings.channel_types[0]
        elif settings.channel_type:
            self._channel_type = settings.channel_type
        else:
            self._channel_type = "telegram"

        self._metadata_defaults = dict(settings.metadata or {})
        self._secret_token: SecretStr | None = settings.secrets.extra.get("webhook_secret")

    @property
    def connector_id(self) -> str:
        return self._connector_id

    @property
    def connector_type(self) -> ConnectorType:
        return self._connector_type

    async def normalize(
        self,
        payload: InboundPayload,
    ) -> Sequence[IncomingMessage]:
        headers = {k.lower(): v for k, v in (payload.headers or {}).items()}
        if self._secret_token is not None:
            provided = headers.get("x-telegram-bot-api-secret-token")
            if provided != self._secret_token.get_secret_value():
                raise ConnectorAuthError("Telegram secret token mismatch")

        update = dict(payload.body or {})
        if not update:
            raise ConnectorPayloadError("Telegram update body is empty")

        message, update_type = _extract_message(update)
        if message is None:
            raise ConnectorPayloadError("Unsupported Telegram update structure")

        chat = message.get("chat")
        if not isinstance(chat, Mapping):
            raise ConnectorPayloadError("Telegram message missing chat payload")
        chat_id = _as_str(chat.get("id"))
        if not chat_id:
            raise ConnectorPayloadError("Telegram chat id is missing")

        user_payload = message.get("from") if isinstance(message.get("from"), Mapping) else None
        if user_payload is None and isinstance(chat, Mapping):
            user_payload = chat
        user_id = _as_str((user_payload or {}).get("id")) or chat_id

        text = _as_str(message.get("text")) or _as_str(message.get("caption"))

        attachments: list[dict[str, Any]] = []

        photos = message.get("photo")
        if isinstance(photos, list) and photos:
            best_photo = _pick_best_photo([item for item in photos if isinstance(item, Mapping)])
            if best_photo:
                attachments.append(
                    {
                        "type": "photo",
                        "file_id": best_photo.get("file_id"),
                        "file_unique_id": best_photo.get("file_unique_id"),
                        "width": best_photo.get("width"),
                        "height": best_photo.get("height"),
                        "file_size": best_photo.get("file_size"),
                    }
                )

        for key, att_type in (
            ("document", "document"),
            ("video", "video"),
            ("video_note", "video_note"),
            ("animation", "animation"),
            ("sticker", "sticker"),
        ):
            payload_map = message.get(key)
            if isinstance(payload_map, Mapping):
                attachments.append(
                    {
                        "type": att_type,
                        "file_id": payload_map.get("file_id"),
                        "file_unique_id": payload_map.get("file_unique_id"),
                        "file_name": payload_map.get("file_name"),
                        "mime_type": payload_map.get("mime_type"),
                        "file_size": payload_map.get("file_size"),
                    }
                )

        # AICODE-NOTE: Voice and audio messages are processed specially:
        # If bytes_base64 is present (downloaded by telegram-module), create audio attachment
        # for transcription. Otherwise, pass file_id for backward compatibility.
        for key in ("voice", "audio"):
            payload_map = message.get(key)
            if isinstance(payload_map, Mapping):
                bytes_base64 = payload_map.get("bytes_base64")
                if bytes_base64:
                    # Create audio attachment with bytes for transcription
                    attachment: dict[str, Any] = {
                        "type": "audio",  # transcribe_if_audio expects type="audio"
                        "bytes_base64": bytes_base64,
                        "filename": f"{key}_{payload_map.get('file_id', 'unknown')}.ogg",
                    }

                    # Add MIME type
                    mime = payload_map.get("mime_type")
                    if mime:
                        attachment["mime"] = mime
                    elif key == "voice":
                        # Default for voice messages
                        attachment["mime"] = "audio/ogg"

                    # Add duration if available
                    duration = payload_map.get("duration")
                    if duration is not None:
                        try:
                            attachment["duration_s"] = float(duration)
                        except (ValueError, TypeError):
                            pass

                    attachments.append(attachment)
                    log.debug(
                        "telegram.audio.attachment_with_bytes",
                        connector_id=self.connector_id,
                        key=key,
                        has_bytes=True,
                        mime=attachment.get("mime"),
                    )
                else:
                    # Fallback: pass file_id for backward compatibility
                    attachments.append(
                        {
                            "type": "audio" if key == "audio" else "voice",
                            "file_id": payload_map.get("file_id"),
                            "file_unique_id": payload_map.get("file_unique_id"),
                            "file_name": payload_map.get("file_name"),
                            "mime_type": payload_map.get("mime_type"),
                            "file_size": payload_map.get("file_size"),
                        }
                    )
                    log.debug(
                        "telegram.audio.attachment_file_id_only",
                        connector_id=self.connector_id,
                        key=key,
                    )

        # AICODE-NOTE: For voice/audio with bytes_base64, telegram-module downloads files.
        # For other media types, Telegram returns only file identifiers.

        company_id = headers.get("x-company-id")

        metadata: dict[str, Any] = {
            **self._metadata_defaults,
            "connector_id": self.connector_id,
            "connector_type": self.connector_type.value,
            "channel_type": self._channel_type,
            "provider": "telegram",
            "update_id": update.get("update_id"),
            "update_type": update_type,
            "chat_id": chat_id,
            "chat_type": chat.get("type"),
            "chat_title": chat.get("title"),
            "chat_username": chat.get("username"),
            "message_id": message.get("message_id"),
            "message_thread_id": message.get("message_thread_id"),
            "reply_to_message_id": message.get("reply_to_message_id"),
            "from_id": (user_payload or {}).get("id"),
            "from_username": (user_payload or {}).get("username"),
            "from_first_name": (user_payload or {}).get("first_name"),
            "from_last_name": (user_payload or {}).get("last_name"),
            "from_language_code": (user_payload or {}).get("language_code"),
            "from_is_bot": (user_payload or {}).get("is_bot"),
        }

        if company_id:
            metadata["company_id"] = company_id

        debounce_cfg = self._settings.debounce
        debounce_window = debounce_cfg.resolve_window(self._default_window)
        storage_key = debounce_cfg.render_storage_key(
            connector_id=self.connector_id,
            conversation_id=chat_id,
            user_id=user_id,
            channel_type=self._channel_type,
            metadata=metadata,
        )

        ts_raw = message.get("date")
        ts_value = float(ts_raw) if isinstance(ts_raw, (int, float)) else time.time()

        incoming = IncomingMessage(
            connector_id=self.connector_id,
            conversation_id=chat_id,
            user_id=user_id,
            text=text,
            attachments=attachments,
            ts=ts_value,
            metadata=metadata,
            debounce_seconds=debounce_window,
            storage_key=storage_key,
        )

        log.debug(
            "connector.telegram.normalized",
            connector_id=self.connector_id,
            chat_id=chat_id,
            user_id=user_id,
            has_text=bool(text),
            attachments=len(attachments),
        )

        return (incoming,)
