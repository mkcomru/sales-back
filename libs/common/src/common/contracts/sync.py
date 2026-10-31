"""Sync contracts for connector-to-backend communication.

These schemas define the contract between connector modules and backend
for history synchronization.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from common.models.inbound import MessageRole


class SyncStatus(StrEnum):
    """History synchronization status."""

    IDLE = "idle"
    INITIAL = "initial"
    BACKFILL = "backfill"
    CATCHUP = "catchup"
    COMPLETED = "completed"
    FAILED = "failed"


class SyncMessage(BaseModel):
    """Normalized message for batch ingestion.

    Connector transforms provider-specific format into this structure.
    """

    conversation_id: str = Field(description="Provider-determined conversation ID")
    user_id: str = Field(description="Message sender identifier")
    text: str = Field(description="Message text content")
    role: MessageRole = Field(description="Who sent the message")
    timestamp: datetime = Field(description="Message timestamp")
    provider_message_id: str = Field(description="Provider message ID for idempotency")
    sender_name: str | None = Field(default=None, description="Normalized sender display name")
    sender_username: str | None = Field(default=None, description="Normalized sender username/handle")
    sender_phone: str | None = Field(default=None, description="Normalized sender phone number")
    artifact_ids: list[str] = Field(
        default_factory=list,
        description="List of S3 artifact IDs for media attachments (voice, image, video, document)",
    )


class SyncProgress(BaseModel):
    """Progress details for synchronization."""

    total_chats: int = Field(description="Total number of chats to process")
    processed_chats: int = Field(description="Number of chats processed")
    total_messages: int = Field(description="Total number of messages to process")
    processed_messages: int = Field(description="Number of messages processed")


class SyncBatchRequest(BaseModel):
    """Request to ingest a batch of messages from connector."""

    connector_id: str = Field(description="Connector identifier")
    batch_id: str = Field(description="Unique batch identifier for idempotency")
    correlation_id: str = Field(description="Correlation ID for tracking sync job")
    messages: list[SyncMessage] = Field(description="List of messages in batch")


class SyncStatusUpdate(BaseModel):
    """Status update from connector during sync."""

    connector_id: str = Field(description="Connector identifier")
    correlation_id: str = Field(description="Correlation ID for tracking sync job")
    status: SyncStatus = Field(description="Current sync status")
    progress: SyncProgress | None = Field(default=None, description="Progress details")
    error: str | None = Field(default=None, description="Error message if status is FAILED")
    cursor: str | None = Field(default=None, description="Cursor for resume after interruption")


class SyncHeartbeatRequest(BaseModel):
    """Heartbeat signal from connector to indicate sync is alive."""

    connector_id: str = Field(description="Connector identifier")
    correlation_id: str = Field(description="Correlation ID for tracking sync job")


class SyncStartCommand(BaseModel):
    """Command to start sync in connector module."""

    connector_id: str = Field(description="Connector identifier")
    correlation_id: str = Field(description="Correlation ID for tracking sync job")
    sync_type: str = Field(description="Type of sync: initial, backfill, or catchup")
    cursor: str | None = Field(default=None, description="Cursor for resume after interruption")
    since: datetime | None = Field(default=None, description="Start date for catchup sync")


class SyncCancelCommand(BaseModel):
    """Command to cancel sync in connector module."""

    connector_id: str = Field(description="Connector identifier")
    correlation_id: str = Field(description="Correlation ID of the sync job to cancel")
