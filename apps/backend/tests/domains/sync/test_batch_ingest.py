"""Tests for sync batch ingestion."""

from datetime import UTC, datetime

import pytest

from common.contracts.sync import SyncBatchRequest, SyncMessage, SyncProgress, SyncStatus, SyncStatusUpdate
from common.models.inbound import MessageRole

from src.backend.modules.chat.repository import ChatMessagesRepository
from src.backend.modules.sync.service import SyncService
from src.backend.modules.transport.models import Connector, ConnectorType
from src.backend.modules.transport.models import SyncStatus as ConnectorSyncStatus


class TestSyncServiceBatchIngest:
    """Tests for batch ingestion."""

    async def test_process_batch_success(self, company_factory):
        """Test successful batch processing."""
        service = SyncService()
        company = await company_factory()

        await Connector.create(
            connector_id="test-connector",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="telegram",
            display_name="Test Connector",
            managed=True,
            config={},
            enabled=True,
        )

        messages = [
            SyncMessage(
                conversation_id="chat123",
                user_id="user1",
                text="Hello",
                role=MessageRole.USER,
                timestamp=datetime.now(UTC),
                provider_message_id="msg1",
                sender_name="User 1",
            ),
            SyncMessage(
                conversation_id="chat123",
                user_id="user1",
                text="World",
                role=MessageRole.USER,
                timestamp=datetime.now(UTC),
                provider_message_id="msg2",
            ),
        ]

        request = SyncBatchRequest(
            connector_id="test-connector",
            batch_id="batch1",
            correlation_id="corr1",
            messages=messages,
        )

        result = await service.process_batch(request)

        assert result["status"] == "processed"
        assert result["message_count"] == 2

        # Verify messages were created
        from src.backend.modules.chat.models import Thread

        threads = await Thread.filter(
            company_id=company.id,
            connector_id="test-connector",
            conversation_id="chat123",
        ).all()
        assert len(threads) > 0
        thread = threads[0]

        messages_repo = ChatMessagesRepository()
        db_messages, _ = await messages_repo.list_by_thread(thread)
        assert len(db_messages) == 2
        assert all(msg.provider_message_id in ("msg1", "msg2") for msg in db_messages)

    async def test_process_batch_idempotency(self, company_factory):
        """Test batch idempotency - duplicate batch should be skipped."""
        service = SyncService()
        company = await company_factory()

        await Connector.create(
            connector_id="test-connector",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="telegram",
            display_name="Test Connector",
            managed=True,
            config={},
            enabled=True,
            sync_progress={"processed_batches": ["batch1"]},
        )

        messages = [
            SyncMessage(
                conversation_id="chat123",
                user_id="user1",
                text="Hello",
                role=MessageRole.USER,
                timestamp=datetime.now(UTC),
                provider_message_id="msg1",
            ),
        ]

        request = SyncBatchRequest(
            connector_id="test-connector",
            batch_id="batch1",
            correlation_id="corr1",
            messages=messages,
        )

        result = await service.process_batch(request)

        assert result["status"] == "duplicate"
        assert result["message_count"] == 0

        # Verify no messages were created
        from src.backend.modules.chat.models import ChatMessage

        all_messages = await ChatMessage.all()
        assert len(all_messages) == 0

    async def test_process_batch_connector_not_found(self):
        """Test batch processing with non-existent connector."""
        service = SyncService()

        request = SyncBatchRequest(
            connector_id="non-existent",
            batch_id="batch1",
            correlation_id="corr1",
            messages=[],
        )

        with pytest.raises(ValueError, match="Connector non-existent not found"):
            await service.process_batch(request)

    async def test_process_batch_marks_batch_as_processed(self, company_factory):
        """Test that batch_id is stored in processed_batches."""
        service = SyncService()
        company = await company_factory()

        await Connector.create(
            connector_id="test-connector",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="telegram",
            display_name="Test Connector",
            managed=True,
            config={},
            enabled=True,
        )

        request = SyncBatchRequest(
            connector_id="test-connector",
            batch_id="batch1",
            correlation_id="corr1",
            messages=[],
        )

        await service.process_batch(request)

        # Reload connector
        connector = await Connector.get(connector_id="test-connector")
        processed_batches = connector.sync_progress.get("processed_batches", [])
        assert "batch1" in processed_batches

    async def test_process_batch_handles_message_errors_gracefully(self, company_factory):
        """Test that errors in individual messages don't stop batch processing."""
        service = SyncService()
        company = await company_factory()

        await Connector.create(
            connector_id="test-connector",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="telegram",
            display_name="Test Connector",
            managed=True,
            config={},
            enabled=True,
        )

        messages = [
            SyncMessage(
                conversation_id="chat123",
                user_id="user1",
                text="Valid message",
                role=MessageRole.USER,
                timestamp=datetime.now(UTC),
                provider_message_id="msg1",
            ),
            SyncMessage(
                conversation_id="",  # Invalid - empty conversation_id
                user_id="user1",
                text="Invalid message",
                role=MessageRole.USER,
                timestamp=datetime.now(UTC),
                provider_message_id="msg2",
            ),
        ]

        request = SyncBatchRequest(
            connector_id="test-connector",
            batch_id="batch1",
            correlation_id="corr1",
            messages=messages,
        )

        result = await service.process_batch(request)

        # Should process at least one message
        assert result["status"] == "processed"
        assert result["message_count"] >= 1


class TestSyncServiceStatusUpdate:
    """Tests for status updates."""

    async def test_update_status_initial(self, company_factory):
        """Test updating status to INITIAL."""
        service = SyncService()
        company = await company_factory()

        connector = await Connector.create(
            connector_id="test-connector",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="telegram",
            display_name="Test Connector",
            managed=True,
            config={},
            enabled=True,
        )

        request = SyncStatusUpdate(
            connector_id="test-connector",
            correlation_id="corr1",
            status=SyncStatus.INITIAL,
        )

        await service.update_status(request)

        await connector.refresh_from_db()
        assert connector.sync_status == ConnectorSyncStatus.INITIAL
        assert connector.sync_started_at is not None

    async def test_update_status_with_progress(self, company_factory):
        """Test updating status with progress information."""
        service = SyncService()
        company = await company_factory()

        connector = await Connector.create(
            connector_id="test-connector",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="telegram",
            display_name="Test Connector",
            managed=True,
            config={},
            enabled=True,
        )

        progress = SyncProgress(
            total_chats=10,
            processed_chats=5,
            total_messages=100,
            processed_messages=50,
        )

        request = SyncStatusUpdate(
            connector_id="test-connector",
            correlation_id="corr1",
            status=SyncStatus.BACKFILL,
            progress=progress,
        )

        await service.update_status(request)

        await connector.refresh_from_db()
        assert connector.sync_status == ConnectorSyncStatus.BACKFILL
        assert connector.sync_progress["total_chats"] == 10
        assert connector.sync_progress["processed_chats"] == 5
        assert connector.sync_progress["total_messages"] == 100
        assert connector.sync_progress["processed_messages"] == 50

    async def test_update_status_completed(self, company_factory):
        """Test updating status to COMPLETED."""
        service = SyncService()
        company = await company_factory()

        connector = await Connector.create(
            connector_id="test-connector",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="telegram",
            display_name="Test Connector",
            managed=True,
            config={},
            enabled=True,
        )

        request = SyncStatusUpdate(
            connector_id="test-connector",
            correlation_id="corr1",
            status=SyncStatus.COMPLETED,
        )

        await service.update_status(request)

        await connector.refresh_from_db()
        assert connector.sync_status == ConnectorSyncStatus.COMPLETED
        assert connector.sync_completed_at is not None

    async def test_update_status_with_cursor(self, company_factory):
        """Test updating status with cursor for resume."""
        service = SyncService()
        company = await company_factory()

        connector = await Connector.create(
            connector_id="test-connector",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="telegram",
            display_name="Test Connector",
            managed=True,
            config={},
            enabled=True,
        )

        request = SyncStatusUpdate(
            connector_id="test-connector",
            correlation_id="corr1",
            status=SyncStatus.BACKFILL,
            cursor="offset_100",
        )

        await service.update_status(request)

        await connector.refresh_from_db()
        assert connector.sync_progress["cursor"] == "offset_100"

    async def test_update_status_connector_not_found(self):
        """Test status update with non-existent connector."""
        service = SyncService()

        request = SyncStatusUpdate(
            connector_id="non-existent",
            correlation_id="corr1",
            status=SyncStatus.INITIAL,
        )

        with pytest.raises(ValueError, match="Connector non-existent not found"):
            await service.update_status(request)


class TestSyncServiceHeartbeat:
    """Tests for heartbeat processing."""

    async def test_process_heartbeat_success(self, company_factory):
        """Test successful heartbeat processing."""
        service = SyncService()
        company = await company_factory()

        connector = await Connector.create(
            connector_id="test-connector",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="telegram",
            display_name="Test Connector",
            managed=True,
            config={},
            enabled=True,
        )

        from common.contracts.sync import SyncHeartbeatRequest

        request = SyncHeartbeatRequest(
            connector_id="test-connector",
            correlation_id="corr1",
        )

        await service.process_heartbeat(request)

        await connector.refresh_from_db()
        assert "last_heartbeat_at" in connector.sync_progress
        assert connector.sync_progress["last_heartbeat_at"] is not None

    async def test_check_heartbeat_timeout_not_timed_out(self, company_factory):
        """Test heartbeat timeout check when not timed out."""
        service = SyncService()
        company = await company_factory()

        from datetime import timedelta

        await Connector.create(
            connector_id="test-connector",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="telegram",
            display_name="Test Connector",
            managed=True,
            config={},
            enabled=True,
            sync_status=ConnectorSyncStatus.INITIAL,
            sync_progress={
                "last_heartbeat_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            },
        )

        is_timed_out = await service.check_heartbeat_timeout("test-connector")
        assert is_timed_out is False

    async def test_check_heartbeat_timeout_timed_out(self, company_factory):
        """Test heartbeat timeout check when timed out."""
        service = SyncService()
        company = await company_factory()

        from datetime import timedelta

        await Connector.create(
            connector_id="test-connector",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="telegram",
            display_name="Test Connector",
            managed=True,
            config={},
            enabled=True,
            sync_status=ConnectorSyncStatus.INITIAL,
            sync_progress={
                "last_heartbeat_at": (datetime.now(UTC) - timedelta(minutes=3)).isoformat(),
            },
        )

        is_timed_out = await service.check_heartbeat_timeout("test-connector")
        assert is_timed_out is True


class TestSyncServiceCursor:
    """Tests for cursor management."""

    async def test_get_cursor_success(self, company_factory):
        """Test getting cursor for connector."""
        service = SyncService()
        company = await company_factory()

        await Connector.create(
            connector_id="test-connector",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="telegram",
            display_name="Test Connector",
            managed=True,
            config={},
            enabled=True,
            sync_progress={"cursor": "offset_50"},
        )

        cursor = await service.get_cursor("test-connector")
        assert cursor == "offset_50"

    async def test_get_cursor_not_found(self, company_factory):
        """Test getting cursor when not set."""
        service = SyncService()
        company = await company_factory()

        await Connector.create(
            connector_id="test-connector",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="telegram",
            display_name="Test Connector",
            managed=True,
            config={},
            enabled=True,
        )

        cursor = await service.get_cursor("test-connector")
        assert cursor is None

    async def test_get_cursor_connector_not_found(self):
        """Test getting cursor for non-existent connector."""
        service = SyncService()

        cursor = await service.get_cursor("non-existent")
        assert cursor is None
