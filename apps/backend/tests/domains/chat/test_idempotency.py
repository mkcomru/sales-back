"""Tests for message idempotency via provider_message_id."""

from datetime import UTC, datetime

import pytest

from src.backend.modules.chat.models import ChatMessage, ChatMessageRole, ChatMessageStatus, Thread


@pytest.mark.asyncio
async def test_create_message_with_provider_message_id_idempotent(thread: Thread, chat_service):
    """Test that creating message with same provider_message_id twice returns existing message."""
    service = chat_service

    provider_message_id = "wappi-msg-12345"

    # Create first message
    message1 = await service.create_message(
        thread_id=thread.thread_id,
        role=ChatMessageRole.USER,
        content="First message",
        status=ChatMessageStatus.SENT,
        provider_message_id=provider_message_id,
        delivered_at=datetime.now(UTC),
    )

    assert message1.provider_message_id == provider_message_id

    # Try to create second message with same provider_message_id
    message2 = await service.create_message(
        thread_id=thread.thread_id,
        role=ChatMessageRole.USER,
        content="Second message (should be ignored)",
        status=ChatMessageStatus.SENT,
        provider_message_id=provider_message_id,
        delivered_at=datetime.now(UTC),
    )

    # Should return the same message
    assert message2.id == message1.id
    assert message2.message_id == message1.message_id
    assert message2.content == "First message"  # Original content preserved

    # Verify only one message in database
    messages = await ChatMessage.filter(thread=thread, provider_message_id=provider_message_id).all()
    assert len(messages) == 1


@pytest.mark.asyncio
async def test_create_message_different_provider_message_id_creates_new(thread: Thread, chat_service):
    """Test that different provider_message_id creates new messages."""
    service = chat_service

    message1 = await service.create_message(
        thread_id=thread.thread_id,
        role=ChatMessageRole.USER,
        content="Message 1",
        status=ChatMessageStatus.SENT,
        provider_message_id="wappi-msg-111",
        delivered_at=datetime.now(UTC),
    )

    message2 = await service.create_message(
        thread_id=thread.thread_id,
        role=ChatMessageRole.USER,
        content="Message 2",
        status=ChatMessageStatus.SENT,
        provider_message_id="wappi-msg-222",
        delivered_at=datetime.now(UTC),
    )

    assert message1.id != message2.id
    assert message1.provider_message_id != message2.provider_message_id

    # Both messages should exist
    messages = await ChatMessage.filter(thread=thread).all()
    assert len(messages) == 2


@pytest.mark.asyncio
async def test_create_message_same_provider_message_id_different_threads(company_factory, chat_service):
    """Test that same provider_message_id can exist in different threads."""
    from src.backend.modules.chat.models import Customer, Thread, ThreadState

    service = chat_service

    company = await company_factory()
    customer1 = await Customer.create(
        user_id="user1",
        company=company,
        quiz_answers={},
    )
    customer2 = await Customer.create(
        user_id="user2",
        company=company,
        quiz_answers={},
    )

    thread1 = await Thread.create(
        thread_id="thread1_test",
        customer=customer1,
        company=company,
        channel_type="telegram",
        state=ThreadState.ACTIVE,
    )
    thread2 = await Thread.create(
        thread_id="thread2_test",
        customer=customer2,
        company=company,
        channel_type="telegram",
        state=ThreadState.ACTIVE,
    )

    provider_message_id = "wappi-msg-shared"

    message1 = await service.create_message(
        thread_id=thread1.thread_id,
        role=ChatMessageRole.USER,
        content="Message in thread 1",
        status=ChatMessageStatus.SENT,
        provider_message_id=provider_message_id,
        delivered_at=datetime.now(UTC),
    )

    message2 = await service.create_message(
        thread_id=thread2.thread_id,
        role=ChatMessageRole.USER,
        content="Message in thread 2",
        status=ChatMessageStatus.SENT,
        provider_message_id=provider_message_id,
        delivered_at=datetime.now(UTC),
    )

    # Should create separate messages in different threads
    assert message1.id != message2.id
    assert message1.provider_message_id == message2.provider_message_id

    # Both messages should exist
    messages1 = await ChatMessage.filter(thread=thread1, provider_message_id=provider_message_id).all()
    messages2 = await ChatMessage.filter(thread=thread2, provider_message_id=provider_message_id).all()

    assert len(messages1) == 1
    assert len(messages2) == 1


@pytest.mark.asyncio
async def test_create_message_without_provider_message_id(thread: Thread, chat_service):
    """Test that messages without provider_message_id are created normally."""
    service = chat_service

    message1 = await service.create_message(
        thread_id=thread.thread_id,
        role=ChatMessageRole.USER,
        content="Message without provider ID",
        status=ChatMessageStatus.SENT,
        provider_message_id=None,
        delivered_at=datetime.now(UTC),
    )

    message2 = await service.create_message(
        thread_id=thread.thread_id,
        role=ChatMessageRole.USER,
        content="Another message without provider ID",
        status=ChatMessageStatus.SENT,
        provider_message_id=None,
        delivered_at=datetime.now(UTC),
    )

    # Both should be created (no idempotency check for None)
    assert message1.id != message2.id
    assert message1.provider_message_id is None
    assert message2.provider_message_id is None


@pytest.mark.asyncio
async def test_create_message_batch_with_duplicates(thread: Thread, chat_service):
    """Test creating batch of messages with duplicate provider_message_id."""
    service = chat_service

    messages_data = [
        {
            "role": ChatMessageRole.USER,
            "content": "Message 1",
            "status": ChatMessageStatus.SENT,
            "provider_message_id": "batch-msg-1",
            "delivered_at": datetime.now(UTC),
        },
        {
            "role": ChatMessageRole.USER,
            "content": "Message 2",
            "status": ChatMessageStatus.SENT,
            "provider_message_id": "batch-msg-2",
            "delivered_at": datetime.now(UTC),
        },
        {
            "role": ChatMessageRole.USER,
            "content": "Message 1 duplicate",
            "status": ChatMessageStatus.SENT,
            "provider_message_id": "batch-msg-1",  # Duplicate
            "delivered_at": datetime.now(UTC),
        },
    ]

    created = await service.create_messages_batch(thread.thread_id, messages_data)

    # Should create 3 message objects (duplicate returns existing)
    assert len(created) == 3

    # But only 2 unique provider_message_ids
    unique_provider_ids = {m.provider_message_id for m in created if m.provider_message_id}
    assert len(unique_provider_ids) == 2

    # Verify content of first message (original, not duplicate)
    message1 = next(m for m in created if m.provider_message_id == "batch-msg-1")
    assert message1.content == "Message 1"

    # Verify duplicate returns the same message object
    duplicate_message = created[2]
    assert duplicate_message.provider_message_id == "batch-msg-1"
    assert duplicate_message.id == message1.id
