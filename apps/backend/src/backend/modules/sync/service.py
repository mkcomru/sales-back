"""Service for processing sync batches and status updates from connectors."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from common.contracts.sync import SyncBatchRequest, SyncHeartbeatRequest, SyncStatus, SyncStatusUpdate

from src.backend.modules.chat.models import ChatMessageRole, ChatMessageStatus, Thread
from src.backend.modules.chat.service import ChatService
from src.backend.modules.orders.service import OrderService
from src.backend.modules.transport.models import SyncStatus as ConnectorSyncStatus
from src.backend.modules.transport.repository import ConnectorsRepository

log = structlog.get_logger(__name__)

HEARTBEAT_TIMEOUT_MINUTES = 2


class SyncService:
    """Service for processing sync batches and managing sync state."""

    def __init__(
        self,
        connectors_repo: ConnectorsRepository | None = None,
        chat_service: ChatService | None = None,
    ):
        self.connectors_repo = connectors_repo or ConnectorsRepository()
        self.chat_service = chat_service or ChatService(order_service=OrderService())

    async def process_batch(self, request: SyncBatchRequest) -> dict[str, Any]:
        """Process a batch of messages from connector.

        Args:
            request: Batch request with messages

        Returns:
            Dict with status and message count

        Raises:
            ValueError: If connector not found or batch already processed
        """
        connector = await self.connectors_repo.get_by_connector_id(request.connector_id)
        if not connector:
            raise ValueError(f"Connector {request.connector_id} not found")

        # AICODE-NOTE: Check batch_id idempotency using sync_progress
        processed_batches = connector.sync_progress.get("processed_batches", [])
        if request.batch_id in processed_batches:
            log.debug(
                "sync.batch.duplicate_skipped",
                connector_id=request.connector_id,
                batch_id=request.batch_id,
                correlation_id=request.correlation_id,
            )
            return {"status": "duplicate", "message_count": 0}

        # AICODE-NOTE: Group messages by conversation_id to process per-thread
        conversations: dict[str, list] = defaultdict(list)
        for msg in request.messages:
            conversations[msg.conversation_id].append(msg)

        # Process messages per conversation
        created_count = 0
        for conversation_id, messages in conversations.items():
            try:
                # AICODE-NOTE: Get existing thread by conversation_id first
                thread = await Thread.filter(
                    connector_id=connector.connector_id,
                    conversation_id=conversation_id,
                ).first()

                # If no thread exists, create one using first user message
                if not thread:
                    first_user_msg = next((m for m in messages if m.role.value == "user"), messages[0])
                    meta = {
                        "name": first_user_msg.sender_name,
                        "username": first_user_msg.sender_username,
                        "phone": first_user_msg.sender_phone,
                    }
                    thread, _ = await self.chat_service.get_or_create_thread(
                        user_id=first_user_msg.user_id,
                        company_id=connector.company_id,
                        channel_type=connector.channel_type,
                        connector_id=connector.connector_id,
                        conversation_id=conversation_id,
                        meta={k: v for k, v in meta.items() if v},
                        is_historical=True,
                    )

                # Create all messages in this thread
                max_timestamp: datetime | None = None
                for sync_msg in messages:
                    try:
                        db_role = ChatMessageRole.USER if sync_msg.role.value == "user" else ChatMessageRole.MANAGER

                        # Outgoing messages may already exist as ASSISTANT rows (saved via
                        # outbound without provider_message_id). Dedup by content + timestamp
                        # to prevent a second MANAGER row for the same logical message.
                        if db_role != ChatMessageRole.USER:
                            existing = await self.chat_service.find_outgoing_duplicate(
                                thread_id=thread.thread_id,
                                content=sync_msg.text,
                                timestamp=sync_msg.timestamp,
                            )
                            if existing:
                                if sync_msg.provider_message_id and not existing.provider_message_id:
                                    existing.provider_message_id = sync_msg.provider_message_id
                                    await existing.save(update_fields=["provider_message_id"])
                                if max_timestamp is None or sync_msg.timestamp > max_timestamp:
                                    max_timestamp = sync_msg.timestamp
                                continue

                        await self.chat_service.create_message(
                            thread_id=thread.thread_id,
                            role=db_role,
                            content=sync_msg.text,
                            status=ChatMessageStatus.SENT,
                            delivered_at=sync_msg.timestamp,
                            provider_message_id=sync_msg.provider_message_id,
                            is_historical=True,
                            artifact_ids=sync_msg.artifact_ids,
                            created_at=sync_msg.timestamp,
                        )
                        created_count += 1
                        if max_timestamp is None or sync_msg.timestamp > max_timestamp:
                            max_timestamp = sync_msg.timestamp
                    except Exception as exc:
                        log.exception(
                            "sync.message.create_failed",
                            connector_id=request.connector_id,
                            batch_id=request.batch_id,
                            message_id=sync_msg.provider_message_id,
                            error=str(exc),
                        )

                if max_timestamp is not None:
                    await Thread.filter(id=thread.id).update(updated_at=max_timestamp)

            except Exception as exc:
                log.exception(
                    "sync.conversation.process_failed",
                    connector_id=request.connector_id,
                    batch_id=request.batch_id,
                    conversation_id=conversation_id,
                    error=str(exc),
                )
                # Continue processing other conversations

        # Mark batch as processed
        processed_batches.append(request.batch_id)
        progress = dict(connector.sync_progress or {})
        progress["processed_batches"] = processed_batches
        await self.connectors_repo.update_connector(connector.id, {"sync_progress": progress})

        log.info(
            "sync.batch.processed",
            connector_id=request.connector_id,
            batch_id=request.batch_id,
            correlation_id=request.correlation_id,
            message_count=created_count,
        )

        return {"status": "processed", "message_count": created_count}

    async def update_status(self, request: SyncStatusUpdate) -> None:
        """Update sync status and progress for connector.

        Args:
            request: Status update request

        Raises:
            ValueError: If connector not found
        """
        connector = await self.connectors_repo.get_by_connector_id(request.connector_id)
        if not connector:
            raise ValueError(f"Connector {request.connector_id} not found")

        updates: dict[str, Any] = {}

        # Map SyncStatus to ConnectorSyncStatus
        status_map = {
            SyncStatus.IDLE: ConnectorSyncStatus.IDLE,
            SyncStatus.INITIAL: ConnectorSyncStatus.INITIAL,
            SyncStatus.BACKFILL: ConnectorSyncStatus.BACKFILL,
            SyncStatus.CATCHUP: ConnectorSyncStatus.CATCHUP,
            SyncStatus.COMPLETED: ConnectorSyncStatus.COMPLETED,
            SyncStatus.FAILED: ConnectorSyncStatus.FAILED,
        }
        updates["sync_status"] = status_map[request.status]

        # Update progress
        if request.progress:
            progress = dict(connector.sync_progress or {})
            progress.update(
                {
                    "total_chats": request.progress.total_chats,
                    "processed_chats": request.progress.processed_chats,
                    "total_messages": request.progress.total_messages,
                    "processed_messages": request.progress.processed_messages,
                }
            )
            updates["sync_progress"] = progress

        # Save cursor for resume
        if request.cursor:
            progress = dict(connector.sync_progress or {})
            progress["cursor"] = request.cursor
            updates["sync_progress"] = progress

        # Update timestamps
        if request.status == SyncStatus.INITIAL and connector.sync_started_at is None:
            updates["sync_started_at"] = datetime.now(UTC)
        if request.status in (SyncStatus.COMPLETED, SyncStatus.FAILED):
            updates["sync_completed_at"] = datetime.now(UTC)

        await self.connectors_repo.update_connector(connector.id, updates)

        log.info(
            "sync.status.updated",
            connector_id=request.connector_id,
            correlation_id=request.correlation_id,
            status=request.status.value,
            error=request.error,
        )

    async def process_heartbeat(self, request: SyncHeartbeatRequest) -> None:
        """Process heartbeat signal from connector.

        Args:
            request: Heartbeat request

        Raises:
            ValueError: If connector not found
        """
        connector = await self.connectors_repo.get_by_connector_id(request.connector_id)
        if not connector:
            raise ValueError(f"Connector {request.connector_id} not found")

        # AICODE-NOTE: Store heartbeat timestamp in sync_progress
        # (last_heartbeat_at field will be added in migration if needed)
        progress = dict(connector.sync_progress or {})
        progress["last_heartbeat_at"] = datetime.now(UTC).isoformat()
        await self.connectors_repo.update_connector(connector.id, {"sync_progress": progress})

        log.debug(
            "sync.heartbeat.received",
            connector_id=request.connector_id,
            correlation_id=request.correlation_id,
        )

    async def get_cursor(self, connector_id: str) -> str | None:
        """Get last cursor for connector to resume sync.

        Args:
            connector_id: Connector identifier

        Returns:
            Cursor string or None if not found
        """
        connector = await self.connectors_repo.get_by_connector_id(connector_id)
        if not connector:
            return None

        return connector.sync_progress.get("cursor") if connector.sync_progress else None

    async def check_heartbeat_timeout(self, connector_id: str) -> bool:
        """Check if connector heartbeat has timed out.

        Args:
            connector_id: Connector identifier

        Returns:
            True if timed out, False otherwise
        """
        connector = await self.connectors_repo.get_by_connector_id(connector_id)
        if not connector:
            return False

        if connector.sync_status not in (
            ConnectorSyncStatus.INITIAL,
            ConnectorSyncStatus.BACKFILL,
            ConnectorSyncStatus.CATCHUP,
        ):
            return False

        heartbeat_str = connector.sync_progress.get("last_heartbeat_at") if connector.sync_progress else None
        if not heartbeat_str:
            return False

        try:
            heartbeat_at = datetime.fromisoformat(heartbeat_str.replace("Z", "+00:00"))
            timeout_threshold = datetime.now(UTC) - timedelta(minutes=HEARTBEAT_TIMEOUT_MINUTES)
            return heartbeat_at < timeout_threshold
        except (ValueError, AttributeError):
            return False
