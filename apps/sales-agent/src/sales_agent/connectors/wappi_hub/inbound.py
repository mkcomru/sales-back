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
from src.sales_agent.connectors.wappi_hub.handlers import get_handler_for_channel
from src.sales_agent.services.debounce import IncomingMessage

log = structlog.get_logger(__name__)


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class WappiHubInboundConnector(InboundConnector):
    """Normalizes Wappi hub webhook payloads into IncomingMessage objects.

    Delegates channel-specific processing (Telegram, WhatsApp, etc.) to specialized
    handlers while maintaining common authentication and normalization logic.
    """

    def __init__(self, settings: ConnectorSettings, *, default_window: int) -> None:
        self._settings = settings
        self._default_window = default_window
        self._connector_id = settings.connector_id or "wappi-hub"
        try:
            self._connector_type = ConnectorType(settings.type)
        except ValueError:
            self._connector_type = ConnectorType.MESSAGING

        if settings.channel_types:
            self._channel_type = settings.channel_types[0]
        elif settings.channel_type:
            self._channel_type = settings.channel_type
        else:
            self._channel_type = "wappi"

        self._metadata_defaults = dict(settings.metadata or {})
        extra: Mapping[str, SecretStr] = settings.secrets.extra or {}
        self._webhook_secret: SecretStr | None = extra.get("webhook_secret")

    @property
    def connector_id(self) -> str:
        return self._connector_id

    @property
    def connector_type(self) -> ConnectorType:
        return self._connector_type

    def _authenticate(self, headers: Mapping[str, str]) -> None:
        """Verify Wappi webhook signature if configured."""
        if self._webhook_secret is None:
            return

        provided_sig = headers.get("x-wappi-signature")
        expected_sig = self._webhook_secret.get_secret_value()
        if not provided_sig or provided_sig != expected_sig:
            raise ConnectorAuthError("Wappi hub signature mismatch")

    def _build_metadata(
        self,
        headers: Mapping[str, str],
        provider_id: str | None,
        chat_id: str | None,
        channel_type: str,
        channel_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Build complete metadata dict from all sources."""
        company_id = headers.get("x-company-id")

        metadata: dict[str, Any] = {
            **self._metadata_defaults,
            **channel_metadata,
            "connector_id": self.connector_id,
            "connector_type": self.connector_type.value,
            "channel_type": channel_type,
            "provider": self._metadata_defaults.get("provider") or "wappi-hub",
        }

        if provider_id:
            metadata["provider_id"] = provider_id
        if chat_id:
            metadata["chat_id"] = chat_id
        if company_id:
            metadata.setdefault("company_id", company_id)

        return metadata

    async def normalize(
        self,
        payload: InboundPayload,
    ) -> Sequence[IncomingMessage]:
        headers = {k.lower(): v for k, v in (payload.headers or {}).items()}

        self._authenticate(headers)

        body = dict(payload.body or {})
        if not body:
            raise ConnectorPayloadError("Wappi hub payload body is empty")

        messages_raw = body.get("messages")
        if not isinstance(messages_raw, list):
            raise ConnectorPayloadError("Wappi hub 'messages' field is missing or not a list")

        if not messages_raw:
            log.warning("connector.wappi_hub.empty_messages", connector_id=self.connector_id)
            return ()

        incoming_messages: list[IncomingMessage] = []

        for message in messages_raw:
            if not isinstance(message, Mapping):
                log.warning("connector.wappi_hub.invalid_message_format", message=message)
                continue

            # AICODE-NOTE: Handler created per message to support mixed-channel batches.
            # Wappi may send telegram + whatsapp messages in same webhook payload.
            handler = get_handler_for_channel(self._channel_type)

            try:
                processed = handler.process(message)
            except ValueError as exc:
                log.warning(
                    "connector.wappi_hub.handler_rejected",
                    message_id=message.get("id"),
                    channel_type=self._channel_type,
                    error=str(exc),
                )
                continue

            if not processed.conversation_id:
                log.warning(
                    "connector.wappi_hub.missing_conversation_id",
                    message_id=message.get("id"),
                )
                continue

            conversation_id = processed.conversation_id
            user_id = processed.user_id or conversation_id
            provider_id = processed.provider_id

            # AICODE-NOTE: Copy sync/message-specific fields from original message
            # These fields are needed in on_batch_callback to determine message role
            extra_metadata = {}
            if "fromMe" in message:
                extra_metadata["fromMe"] = message["fromMe"]
            if "_sync_mode" in message:
                extra_metadata["_sync_mode"] = message["_sync_mode"]
            if "_manager_outgoing" in message:
                extra_metadata["_manager_outgoing"] = message["_manager_outgoing"]

            metadata = self._build_metadata(
                headers=headers,
                provider_id=provider_id,
                chat_id=conversation_id,
                channel_type=self._channel_type,
                channel_metadata={**processed.channel_metadata, **extra_metadata},
            )

            debounce_cfg = self._settings.debounce
            debounce_window = debounce_cfg.resolve_window(self._default_window)
            storage_key = debounce_cfg.render_storage_key(
                connector_id=self.connector_id,
                conversation_id=conversation_id,
                user_id=user_id,
                channel_type=self._channel_type,
                metadata=metadata,
            )

            ts_value = processed.ts or time.time()

            incoming = IncomingMessage(
                connector_id=self.connector_id,
                conversation_id=conversation_id,
                user_id=user_id,
                text=processed.text,
                attachments=processed.attachments,
                ts=ts_value,
                metadata=metadata,
                debounce_seconds=debounce_window,
                storage_key=storage_key,
            )

            incoming_messages.append(incoming)

            log.debug(
                "connector.wappi_hub.normalized_message",
                connector_id=self.connector_id,
                conversation_id=conversation_id,
                user_id=user_id,
                provider_id=provider_id,
                channel_type=self._channel_type,
                attachments=len(processed.attachments),
            )

        log.info(
            "connector.wappi_hub.normalized",
            connector_id=self.connector_id,
            messages_count=len(incoming_messages),
        )

        return incoming_messages
