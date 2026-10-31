from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

import structlog

log = structlog.get_logger(__name__)


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class ProcessedMessage:
    """Result of channel-specific message processing."""

    def __init__(
        self,
        text: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
        channel_metadata: dict[str, Any] | None = None,
        conversation_id: str | None = None,
        user_id: str | None = None,
        provider_id: str | None = None,
        ts: float | None = None,
    ) -> None:
        self.text = text
        self.attachments = attachments or []
        self.channel_metadata = channel_metadata or {}
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.provider_id = provider_id
        self.ts = ts


class WappiChannelHandler(ABC):
    """Base protocol for channel-specific Wappi message handlers.

    AICODE-NOTE: Strategy pattern for different channels (Telegram, WhatsApp).
    Each handler normalizes channel-specific messages from Wappi webhook while
    main WappiHubInboundConnector handles auth and common orchestration.
    """

    @abstractmethod
    def process(self, message: Mapping[str, Any]) -> ProcessedMessage:
        """
        Extract normalized data from single Wappi message.

        Args:
            message: Single message dict from Wappi webhook

        Returns:
            ProcessedMessage with normalized fields
        """
        ...


class WappiTelegramHandler(WappiChannelHandler):
    """Handler for Telegram messages via Wappi hub.

    AICODE-NOTE: Processes text and voice (ptt) messages.
    Voice messages are converted to audio attachments for transcription.
    Other media types (photos, videos, stickers) are rejected.
    """

    def process(self, message: Mapping[str, Any]) -> ProcessedMessage:
        msg_type = _as_str(message.get("type"))

        if msg_type and msg_type not in ("text", "ptt"):
            msg_id = message.get("id")
            raise ValueError(
                f"Wappi Telegram handler accepts only text and voice messages. "
                f"Received message type: {msg_type} (id: {msg_id})"
            )

        text = _as_str(message.get("body")) if msg_type == "text" else None
        attachments_list: list[dict[str, Any]] = []

        if msg_type == "ptt":
            audio_base64 = message.get("body")
            if audio_base64:
                mime_type = _as_str(message.get("mimetype"))
                length_seconds = message.get("length_seconds")

                duration_s = None
                if length_seconds is not None:
                    try:
                        duration_s = float(length_seconds)
                    except (ValueError, TypeError):
                        pass

                attachment: dict[str, Any] = {
                    "type": "audio",
                    "bytes_base64": audio_base64,
                    "filename": f"voice_{message.get('id', 'unknown')}.ogg",
                }

                if mime_type:
                    attachment["mime"] = mime_type
                if duration_s is not None:
                    attachment["duration_s"] = duration_s

                attachments_list.append(attachment)

        msg_id = _as_str(message.get("id"))
        profile_id = _as_str(message.get("profile_id"))
        chat_id = _as_str(message.get("chatId"))
        username = _as_str(message.get("username"))
        sender_name = _as_str(message.get("senderName"))
        contact_name = _as_str(message.get("contact_name"))
        contact_username = _as_str(message.get("contact_username"))

        conversation_id = chat_id or profile_id
        # AICODE-NOTE: Use conversation_id (chat_id) as user_id, not username
        # Username can change, but chat_id is stable identifier
        user_id = conversation_id

        channel_metadata: dict[str, Any] = {}
        if msg_id:
            channel_metadata["message_id"] = msg_id
        if sender_name:
            channel_metadata["sender_name"] = sender_name
        if contact_name:
            channel_metadata["contact_name"] = contact_name
        if username:
            channel_metadata["username"] = username
        if contact_username:
            channel_metadata["contact_username"] = contact_username

        chat_type = _as_str(message.get("chat_type"))
        if chat_type:
            channel_metadata["chat_type"] = chat_type

        if message.get("is_forwarded"):
            channel_metadata["is_forwarded"] = True
        if message.get("isReply"):
            channel_metadata["is_reply"] = True
        if message.get("is_edited"):
            channel_metadata["is_edited"] = True

        ts_raw = message.get("time")
        ts_value = float(ts_raw) if isinstance(ts_raw, (int, float)) else None

        log.debug(
            "wappi.telegram.processed",
            message_id=msg_id,
            conversation_id=conversation_id,
            user_id=user_id,
            message_type=msg_type,
            text_length=len(text) if text else 0,
            has_audio=len(attachments_list) > 0,
        )

        return ProcessedMessage(
            text=text,
            attachments=attachments_list,
            channel_metadata=channel_metadata,
            conversation_id=conversation_id,
            user_id=user_id,
            provider_id=profile_id,
            ts=ts_value,
        )


class WappiWhatsAppHandler(WappiChannelHandler):
    """Handler for WhatsApp messages via Wappi hub.

    AICODE-NOTE: Processes text and voice (ptt) messages from WhatsApp.
    Voice messages are converted to audio attachments for transcription.
    WhatsApp uses 'chat' type for text and 'ptt' for voice messages.
    """

    def process(self, message: Mapping[str, Any]) -> ProcessedMessage:
        msg_type = _as_str(message.get("type"))

        if msg_type and msg_type not in ("chat", "ptt"):
            msg_id = message.get("id")
            raise ValueError(
                f"Wappi WhatsApp handler accepts only text and voice messages. "
                f"Received message type: {msg_type} (id: {msg_id})"
            )

        text = _as_str(message.get("body")) if msg_type == "chat" else None
        attachments_list: list[dict[str, Any]] = []

        if msg_type == "ptt":
            audio_base64 = message.get("body")
            if audio_base64:
                mime_type = _as_str(message.get("mimetype"))

                attachment: dict[str, Any] = {
                    "type": "audio",
                    "bytes_base64": audio_base64,
                    "filename": f"voice_{message.get('id', 'unknown')}.ogg",
                }

                if mime_type:
                    attachment["mime"] = mime_type

                attachments_list.append(attachment)

        msg_id = _as_str(message.get("id"))
        profile_id = _as_str(message.get("profile_id"))
        chat_id = _as_str(message.get("chatId"))
        from_field = _as_str(message.get("from"))
        sender_name = _as_str(message.get("senderName"))
        contact_name = _as_str(message.get("contact_name"))

        # WhatsApp uses phone@c.us format for IDs
        # AICODE-NOTE: Use chat_id/conversation_id
        # as user_id, not from_field/contact_name
        # from_field is phone number in
        # format phone@c.us (stable ID)
        # contact_name is display name (can change)
        conversation_id = chat_id or from_field or profile_id
        user_id = conversation_id

        channel_metadata: dict[str, Any] = {}
        if msg_id:
            channel_metadata["message_id"] = msg_id
        if sender_name:
            channel_metadata["sender_name"] = sender_name
        if contact_name:
            channel_metadata["contact_name"] = contact_name
        if from_field:
            channel_metadata["from"] = from_field

        chat_type = _as_str(message.get("chat_type"))
        if chat_type:
            channel_metadata["chat_type"] = chat_type

        if message.get("is_forwarded"):
            channel_metadata["is_forwarded"] = True
        if message.get("isReply"):
            channel_metadata["is_reply"] = True
            # Include reply message info if available
            reply_msg = message.get("reply_message")
            if isinstance(reply_msg, Mapping):
                channel_metadata["reply_to_message_id"] = reply_msg.get("id")
        if message.get("is_edited"):
            channel_metadata["is_edited"] = True

        ts_raw = message.get("time")
        ts_value = float(ts_raw) if isinstance(ts_raw, (int, float)) else None

        log.debug(
            "wappi.whatsapp.processed",
            message_id=msg_id,
            conversation_id=conversation_id,
            user_id=user_id,
            message_type=msg_type,
            text_length=len(text) if text else 0,
            has_audio=len(attachments_list) > 0,
        )

        return ProcessedMessage(
            text=text,
            attachments=attachments_list,
            channel_metadata=channel_metadata,
            conversation_id=conversation_id,
            user_id=user_id,
            provider_id=profile_id,
            ts=ts_value,
        )


def get_handler_for_channel(channel_type: str) -> WappiChannelHandler:
    """Factory function to get appropriate handler for the channel type.

    Args:
        channel_type: Channel identifier (e.g., 'telegram', 'whatsapp')

    Returns:
        Appropriate WappiChannelHandler instance
    """
    normalized = channel_type.lower().strip()

    if "telegram" in normalized:
        return WappiTelegramHandler()
    if "whatsapp" in normalized or "whats_app" in normalized:
        return WappiWhatsAppHandler()

    log.warning("wappi.handler.unknown", channel_type=channel_type)
    return WappiTelegramHandler()
