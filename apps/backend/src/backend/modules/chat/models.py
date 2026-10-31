from __future__ import annotations

from enum import Enum, StrEnum

import structlog
from tortoise import fields

from src.backend.modules.core.base_model import BaseModel
from src.backend.modules.s3_storage.exceptions import S3FileNotFoundError, S3StorageError
from src.backend.modules.s3_storage.s3_client import S3Client

log = structlog.get_logger(__name__)


class ThreadState(str, Enum):
    """Thread lifecycle states."""

    ACTIVE = "active"
    WAITING_MANAGER = "waiting_manager"
    HANDOFF = "handoff"
    CLOSED = "closed"


class AssistantMode(StrEnum):
    ACTIVE = "active"
    SHADOWING = "shadowing"
    INACTIVE = "inactive"


class ChatMessageRole(str, Enum):
    """Message author roles."""

    USER = "user"
    ASSISTANT = "assistant"
    MANAGER = "manager"
    SYSTEM = "system"


class ChatMessageStatus(str, Enum):
    """Message delivery status."""

    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChatMessageType(str, Enum):
    """Message types."""

    TEXT = "text"
    INTERNAL_NOTE = "internal_note"
    SYSTEM_EVENT = "system_event"


class Customer(BaseModel):
    """Customer profile with quiz answers and conversation metadata."""

    id = fields.IntField(primary_key=True)
    user_id = fields.CharField(max_length=64, db_index=True)
    name = fields.CharField(max_length=255, null=True)
    company: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.Company",
        related_name="customers",
        on_delete=fields.CASCADE,
    )
    rejected = fields.BooleanField(default=False)
    rejection_reason = fields.CharField(max_length=255, null=True)
    customer_fields = fields.JSONField(default=dict)
    langfuse_sessions = fields.JSONField(default=dict)
    meta = fields.JSONField(default=dict)
    notes = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    threads: fields.ReverseRelation

    class Meta(BaseModel.Meta):
        table = "customers"
        schema = "backend"
        unique_together = (("user_id", "company"),)


class Thread(BaseModel):
    """Conversation thread grouping messages from a specific channel."""

    # AICODE-NOTE: Thread unifies conversation history across channels.
    # A customer may have multiple threads (e.g., different Telegram chats,
    # CRM/messaging contacts), each identified by channel_type + conversation_id.
    id = fields.IntField(primary_key=True)
    thread_id = fields.CharField(max_length=128, unique=True, db_index=True)
    customer: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.Customer",
        related_name="threads",
        on_delete=fields.CASCADE,
    )
    company: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.Company",
        related_name="threads",
        on_delete=fields.CASCADE,
    )
    active_order: fields.ForeignKeyNullableRelation = fields.ForeignKeyField(
        "models.Order",
        related_name="threads",
        on_delete=fields.SET_NULL,
        null=True,
    )
    connector_id = fields.CharField(max_length=128, null=True)
    channel_type = fields.CharField(max_length=50)
    conversation_id = fields.CharField(max_length=255, null=True)
    state = fields.CharEnumField(ThreadState, max_length=30, default=ThreadState.ACTIVE)
    assistant_mode = fields.CharEnumField(AssistantMode, max_length=16, default=AssistantMode.ACTIVE)
    history_synced = fields.BooleanField(default=False)
    unread_count = fields.IntField(default=0)
    last_customer_message_at = fields.DatetimeField(null=True)
    metadata = fields.JSONField(default=dict)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    messages: fields.ReverseRelation

    class Meta(BaseModel.Meta):
        table = "threads"
        schema = "backend"
        indexes = (
            ("customer_id", "channel_type"),
            ("active_order_id",),
            ("company_id", "updated_at"),
        )


class ChatMessage(BaseModel):
    """Individual message within a thread."""

    id = fields.IntField(primary_key=True)
    message_id = fields.CharField(max_length=128, unique=True, db_index=True)
    provider_message_id = fields.CharField(max_length=255, null=True, db_index=True)
    thread: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.Thread",
        related_name="messages",
        on_delete=fields.CASCADE,
    )
    author: fields.ForeignKeyNullableRelation = fields.ForeignKeyField(
        "models.CompanyUser",
        related_name="messages",
        on_delete=fields.CASCADE,
        null=True,
    )
    role = fields.CharEnumField(ChatMessageRole, max_length=16)
    type = fields.CharEnumField(ChatMessageType, max_length=16, default=ChatMessageType.TEXT)
    content = fields.TextField()
    transcription = fields.TextField(null=True)
    status = fields.CharEnumField(ChatMessageStatus, max_length=20, default=ChatMessageStatus.PENDING)
    metadata = fields.JSONField(default=dict)
    attachments = fields.JSONField(default=list)
    artifact_ids = fields.JSONField(default=list)
    reply_to = fields.CharField(max_length=128, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True, null=True)
    delivered_at = fields.DatetimeField(null=True)

    async def download_artifacts(self, s3_client: S3Client) -> list[bytes]:
        """Download all artifact files from S3 storage.

        Args:
            s3_client: S3 client instance for downloading

        Returns:
            List of file contents as bytes, in the same order as artifact_ids

        Raises:
            S3FileNotFoundError: If any artifact not found
            S3StorageError: If any download fails
        """
        artifact_ids = self.artifact_ids or []
        if not artifact_ids:
            return []

        results: list[bytes] = []
        for artifact_id in artifact_ids:
            try:
                file_bytes = await s3_client.download_file(artifact_id)
                log.debug(
                    "chat_message.artifact.downloaded",
                    message_id=self.message_id,
                    artifact_id=artifact_id,
                    size_bytes=len(file_bytes),
                )
                results.append(file_bytes)
            except S3FileNotFoundError:
                log.warning(
                    "chat_message.artifact.not_found",
                    message_id=self.message_id,
                    artifact_id=artifact_id,
                )
                raise
            except S3StorageError:
                log.error(
                    "chat_message.artifact.download_failed",
                    message_id=self.message_id,
                    artifact_id=artifact_id,
                )
                raise

        return results

    class Meta(BaseModel.Meta):
        table = "chat_messages"
        schema = "backend"
        # AICODE-NOTE: Composite index for history retrieval
        # Query: WHERE thread_id=X ORDER BY created_at
        # AICODE-NOTE: Unique index for idempotency - prevents duplicate messages from provider
        # Note: Unique constraint on (thread_id, provider_message_id) is enforced via partial index in migration
        # since provider_message_id can be NULL
        indexes = (
            ("thread_id", "created_at"),
            ("thread_id", "provider_message_id"),
        )
