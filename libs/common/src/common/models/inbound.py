"""Inbound message envelope schemas for Sales Agent unified ingestion.

These schemas define the contract between connectors and Sales Agent.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class MessageRole(StrEnum):
    """Role of the message sender in the conversation."""

    USER = "user"
    MANAGER = "manager"


class AudioData(BaseModel):
    """Audio attachment data for voice messages."""

    bytes_base64: str = Field(description="Base64-encoded audio bytes")
    mime: str = Field(default="audio/ogg", description="Audio MIME type")


class InboundEnvelope(BaseModel):
    """Normalized inbound message envelope.

    All connectors (managed and custom) send this structure to Sales Agent.
    The `conversation_id` is provider-determined and opaque to Sales.
    """

    conversation_id: str = Field(description="Provider-determined conversation ID (e.g., chat.id in Telegram)")
    user_id: str = Field(description="Message sender identifier")
    text: str | None = Field(default=None, description="Message text content (None if audio-only)")
    ts: float = Field(description="Unix timestamp of the message")
    artifact_ids: list[str] = Field(
        default_factory=list,
        description="List of S3 artifact IDs for media attachments (voice, image, video, etc.)",
    )
    audio: AudioData | None = Field(
        default=None,
        description="Raw audio data (fallback when conversion/upload fails, deprecated in favor of artifact_ids)",
    )
    message_id: str | None = Field(default=None, description="Provider message ID for idempotency")

    role: MessageRole = Field(default=MessageRole.USER, description="Who sent the message")
    is_historical: bool = Field(default=False, description="Is this a sync/backfill message?")
    sender_name: str | None = Field(default=None, description="Normalized sender display name")
    sender_username: str | None = Field(default=None, description="Normalized sender username/handle")
    sender_phone: str | None = Field(default=None, description="Normalized sender phone number")

    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra metadata for connector-specific features (DEPRECATED - use standardized fields)",
    )


class DebounceConfig(BaseModel):
    """Debounce configuration returned in ConnectorContext."""

    window_seconds: int = Field(default=45, ge=1, le=300)
    storage_key_template: str = Field(default="{connector_id}:{conversation_id}")


class ConnectorContext(BaseModel):
    """Resolved connector context for message processing.

    Returned by backend validation endpoints.
    """

    connector_id: str
    company_id: int
    type: str
    channel_type: str
    debounce: DebounceConfig
