"""Integration tests for sync flow from connector to database."""

from datetime import UTC, datetime

from common.contracts.sync import SyncBatchRequest, SyncMessage, SyncStatus, SyncStatusUpdate
from common.models.inbound import MessageRole

from src.backend.modules.chat.models import AssistantMode
from src.backend.modules.chat.repository import ChatMessagesRepository
from src.backend.modules.sync.service import SyncService
from src.backend.modules.transport.models import Connector, ConnectorType


class TestSyncIntegration:
    """Integration tests for full sync flow."""

    async def test_full_sync_flow(self, company_factory):
        """Test complete sync flow: batch ingest → thread creation → message storage."""
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

        # Step 1: Update status to INITIAL
        status_update = SyncStatusUpdate(
            connector_id="test-connector",
            correlation_id="corr1",
            status=SyncStatus.INITIAL,
        )
        await service.update_status(status_update)

        await connector.refresh_from_db()
        assert connector.sync_status.value == "initial"

        # Step 2: Send batch of messages
        messages = [
            SyncMessage(
                conversation_id="chat123",
                user_id="user1",
                text="Hello",
                role=MessageRole.USER,
                timestamp=datetime.now(UTC),
                provider_message_id="msg1",
                sender_name="User 1",
                sender_username="user1",
            ),
            SyncMessage(
                conversation_id="chat123",
                user_id="user1",
                text="How are you?",
                role=MessageRole.USER,
                timestamp=datetime.now(UTC),
                provider_message_id="msg2",
            ),
            SyncMessage(
                conversation_id="chat123",
                user_id="profile-123",
                text="I'm fine, thanks!",
                role=MessageRole.MANAGER,
                timestamp=datetime.now(UTC),
                provider_message_id="msg3",
            ),
        ]

        batch_request = SyncBatchRequest(
            connector_id="test-connector",
            batch_id="batch1",
            correlation_id="corr1",
            messages=messages,
        )

        result = await service.process_batch(batch_request)
        assert result["status"] == "processed"
        assert result["message_count"] == 3

        # Step 3: Verify threads were created
        from src.backend.modules.chat.models import Thread

        threads = await Thread.filter(
            company_id=company.id,
            connector_id="test-connector",
            conversation_id="chat123",
        ).all()
        # For same conversation_id but different user_id, separate threads are created
        assert len(threads) >= 1
        # Historical-message threads start with assistant inactive
        for thread in threads:
            assert thread.assistant_mode == AssistantMode.INACTIVE
            assert thread.metadata.get("has_history") is True

        # Step 4: Verify messages were stored across all threads
        messages_repo = ChatMessagesRepository()
        all_messages = []
        for thread in threads:
            db_messages, _ = await messages_repo.list_by_thread(thread)
            all_messages.extend(db_messages)
        assert len(all_messages) == 3

        # Verify message order and content
        msg1 = next((m for m in all_messages if m.provider_message_id == "msg1"), None)
        assert msg1 is not None
        assert msg1.content == "Hello"
        assert msg1.role.value == "user"

        msg3 = next((m for m in all_messages if m.provider_message_id == "msg3"), None)
        assert msg3 is not None
        assert msg3.content == "I'm fine, thanks!"
        assert msg3.role.value == "manager"

        # Step 5: Update status to COMPLETED
        status_update = SyncStatusUpdate(
            connector_id="test-connector",
            correlation_id="corr1",
            status=SyncStatus.COMPLETED,
        )
        await service.update_status(status_update)

        await connector.refresh_from_db()
        assert connector.sync_status.value == "completed"
        assert connector.sync_completed_at is not None

    async def test_idempotency_across_multiple_batches(self, company_factory):
        """Test that duplicate batches are handled correctly."""
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
            ),
        ]

        # Send batch first time
        batch1 = SyncBatchRequest(
            connector_id="test-connector",
            batch_id="batch1",
            correlation_id="corr1",
            messages=messages,
        )
        result1 = await service.process_batch(batch1)
        assert result1["status"] == "processed"

        # Send same batch again (duplicate)
        batch2 = SyncBatchRequest(
            connector_id="test-connector",
            batch_id="batch1",
            correlation_id="corr1",
            messages=messages,
        )
        result2 = await service.process_batch(batch2)
        assert result2["status"] == "duplicate"
        assert result2["message_count"] == 0

        # Verify only one message was created
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
        assert len(db_messages) == 1

    async def test_multiple_conversations_in_batch(self, company_factory):
        """Test batch with messages from multiple conversations."""
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
                conversation_id="chat1",
                user_id="user1",
                text="Hello from chat1",
                role=MessageRole.USER,
                timestamp=datetime.now(UTC),
                provider_message_id="msg1",
            ),
            SyncMessage(
                conversation_id="chat2",
                user_id="user2",
                text="Hello from chat2",
                role=MessageRole.USER,
                timestamp=datetime.now(UTC),
                provider_message_id="msg2",
            ),
        ]

        batch = SyncBatchRequest(
            connector_id="test-connector",
            batch_id="batch1",
            correlation_id="corr1",
            messages=messages,
        )

        result = await service.process_batch(batch)
        assert result["status"] == "processed"
        assert result["message_count"] == 2

        # Verify both threads were created
        from src.backend.modules.chat.models import Thread

        threads1 = await Thread.filter(
            company_id=company.id,
            connector_id="test-connector",
            conversation_id="chat1",
        ).all()
        threads2 = await Thread.filter(
            company_id=company.id,
            connector_id="test-connector",
            conversation_id="chat2",
        ).all()
        assert len(threads1) > 0
        assert len(threads2) > 0
        thread1 = threads1[0]
        thread2 = threads2[0]
        assert thread1.thread_id != thread2.thread_id

        # Verify messages in correct threads
        messages_repo = ChatMessagesRepository()
        messages1, _ = await messages_repo.list_by_thread(thread1)
        messages2, _ = await messages_repo.list_by_thread(thread2)

        assert len(messages1) == 1
        assert len(messages2) == 1
        assert messages1[0].content == "Hello from chat1"
        assert messages2[0].content == "Hello from chat2"
