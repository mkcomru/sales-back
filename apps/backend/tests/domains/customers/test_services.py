"""Service tests for ChatService."""

from datetime import UTC, datetime

import pytest

from src.backend.modules.chat.models import (
    AssistantMode,
    ChatMessage,
    ChatMessageRole,
    ChatMessageStatus,
    Customer,
    Thread,
    ThreadState,
)
from src.backend.modules.chat.service import ChatService


@pytest.mark.asyncio
async def test_chat_service_get_or_create_customer_new(company_factory, chat_service: ChatService):
    """Test creating new customer via service."""
    company = await company_factory()
    service = chat_service

    customer, created = await service.get_or_create_customer(
        user_id="service_user_new",
        company_id=company.id,
        meta={"username": "serviceuser"},
    )

    assert created is True
    assert customer.user_id == "service_user_new"
    assert customer.meta == {"username": "serviceuser"}


@pytest.mark.asyncio
async def test_chat_service_get_or_create_customer_existing(company_factory, chat_service: ChatService):
    """Test getting existing customer via service."""
    company = await company_factory()
    existing = await Customer.create(user_id="service_user_existing", company=company, meta={"username": "old"})
    service = chat_service

    customer, created = await service.get_or_create_customer(
        user_id="service_user_existing",
        company_id=company.id,
        meta={"username": "new"},
    )

    assert created is False
    assert customer.id == existing.id
    assert customer.meta == {"username": "new"}


@pytest.mark.asyncio
async def test_chat_service_get_customer_profile(company_factory, chat_service):
    """Test getting customer profile."""
    company = await company_factory()
    _ = await Customer.create(
        user_id="profile_user",
        company=company,
        customer_fields={"field1": "value1", "field2": "value2"},
        rejected=False,
    )
    service = chat_service

    profile = await service.get_customer_profile("profile_user", company.id)

    assert profile.customer_fields == {"field1": "value1", "field2": "value2"}
    assert profile.rejected is False
    assert profile.rejection_reason is None


@pytest.mark.asyncio
async def test_chat_service_update_customer_fields(company_factory, chat_service):
    """Test updating customer fields."""
    company = await company_factory()
    customer = await Customer.create(user_id="update_user", company=company, customer_fields={"field1": "value1"})
    service = chat_service

    await service.update_customer_fields("update_user", company.id, {"field2": "value2", "field3": "value3"})

    updated = await Customer.get(id=customer.id)
    assert updated.customer_fields == {
        "field1": "value1",
        "field2": "value2",
        "field3": "value3",
    }


@pytest.mark.asyncio
async def test_chat_service_mark_customer_rejected(company_factory, chat_service):
    """Test marking customer as rejected."""
    company = await company_factory()
    customer = await Customer.create(user_id="reject_service_user", company=company)
    service = chat_service

    await service.mark_customer_rejected("reject_service_user", company.id, "Spam")

    updated = await Customer.get(id=customer.id)
    assert updated.rejected is True
    assert updated.rejection_reason == "Spam"


@pytest.mark.asyncio
async def test_chat_service_reset_customer_profile(company_factory, chat_service):
    """Test resetting customer profile."""
    company = await company_factory()
    customer = await Customer.create(
        user_id="reset_service_user",
        company=company,
        customer_fields={"field1": "value1"},
        rejected=True,
        rejection_reason="Test",
    )
    thread = await Thread.create(
        thread_id="thread_reset",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )
    await ChatMessage.create(
        message_id="msg_reset",
        thread=thread,
        role=ChatMessageRole.USER,
        content="Test message",
    )
    service = chat_service

    await service.reset_customer_profile("reset_service_user", company.id)

    updated = await Customer.get(id=customer.id)
    assert updated.customer_fields == {}
    assert updated.rejected is False
    assert updated.rejection_reason is None

    # Messages should be deleted
    messages = await ChatMessage.filter(thread=thread).all()
    assert len(messages) == 0


@pytest.mark.asyncio
async def test_chat_service_get_or_create_thread_new(company_factory, chat_service):
    """Test creating new thread via service."""
    company = await company_factory()
    customer = await Customer.create(user_id="thread_service_new", company=company)
    service = chat_service

    thread, created = await service.get_or_create_thread(
        user_id="thread_service_new",
        company_id=company.id,
        channel_type="telegram",
        connector_id="test-connector",
        conversation_id="conv_service_new",
        meta={"username": "threaduser"},
    )

    assert created is True
    assert thread.customer_id == customer.id
    assert thread.company_id == company.id
    assert thread.channel_type == "telegram"
    assert thread.connector_id == "test-connector"
    assert thread.conversation_id == "conv_service_new"
    assert thread.state == ThreadState.ACTIVE

    # Customer meta should be updated
    updated_customer = await Customer.get(id=customer.id)
    assert updated_customer.meta == {"username": "threaduser"}


@pytest.mark.asyncio
async def test_chat_service_get_or_create_thread_existing(company_factory, chat_service):
    """Test getting existing thread via service."""
    company = await company_factory()
    customer = await Customer.create(user_id="thread_service_existing", company=company)
    existing = await Thread.create(
        thread_id="thread_service_existing_id",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
        conversation_id="conv_service_existing",
    )
    service = chat_service

    thread, created = await service.get_or_create_thread(
        user_id="thread_service_existing",
        company_id=company.id,
        channel_type="telegram",
        connector_id="test-connector",
        conversation_id="conv_service_existing",
    )

    assert created is False
    assert thread.id == existing.id


@pytest.mark.asyncio
async def test_chat_service_get_thread_by_id(company_factory, chat_service):
    """Test getting thread by ID."""
    company = await company_factory()
    customer = await Customer.create(user_id="get_thread_user", company=company)
    thread = await Thread.create(
        thread_id="thread_get",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )
    service = chat_service

    found = await service.get_thread_by_id("thread_get")
    assert found is not None
    assert found.id == thread.id

    not_found = await service.get_thread_by_id("nonexistent")
    assert not_found is None


@pytest.mark.asyncio
async def test_chat_service_list_threads(company_factory, chat_service):
    """Test listing threads with filters."""
    company = await company_factory()
    customer1 = await Customer.create(user_id="list_thread_user1", company=company)
    customer2 = await Customer.create(user_id="list_thread_user2", company=company)

    _ = await Thread.create(
        thread_id="thread_list_1",
        customer=customer1,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
        state=ThreadState.ACTIVE,
    )
    _ = await Thread.create(
        thread_id="thread_list_2",
        customer=customer2,
        company=company,
        channel_type="whatsapp",
        connector_id="test-connector",
        state=ThreadState.WAITING_MANAGER,
    )
    service = chat_service

    # List all
    threads, total = await service.list_threads(company.id)
    assert total >= 2

    # Filter by channel_type
    threads, total = await service.list_threads(company.id, channel_type="telegram")
    assert total >= 1
    assert any(t.thread_id == "thread_list_1" for t in threads)

    # Filter by state
    threads, total = await service.list_threads(company.id, state=ThreadState.ACTIVE)
    assert total >= 1
    assert any(t.thread_id == "thread_list_1" for t in threads)


@pytest.mark.asyncio
async def test_chat_service_update_thread_state(company_factory, chat_service):
    """Test updating thread state."""
    company = await company_factory()
    customer = await Customer.create(user_id="state_service_user", company=company)
    _ = await Thread.create(
        thread_id="thread_state_service",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
        state=ThreadState.ACTIVE,
    )
    service = chat_service

    updated = await service.update_thread_state(
        thread_id="thread_state_service",
        state=ThreadState.HANDOFF,
        reason="Manual handoff",
        metadata={"handoff_by": "manager_1"},
    )

    assert updated.state == ThreadState.HANDOFF
    assert "last_state_change" in updated.metadata


@pytest.mark.asyncio
async def test_chat_service_control_thread_assistant(company_factory, chat_service):
    """Test controlling assistant active state."""
    company = await company_factory()
    customer = await Customer.create(user_id="assistant_service_user", company=company)
    _ = await Thread.create(
        thread_id="thread_assistant_service",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )
    service = chat_service

    updated = await service.control_thread_mode(
        thread_id="thread_assistant_service",
        mode=AssistantMode.INACTIVE,
        reason="Manual stop",
    )

    assert updated.assistant_mode == AssistantMode.INACTIVE
    assert "last_assistant_control" in updated.metadata


@pytest.mark.asyncio
async def test_chat_service_create_message(company_factory, chat_service):
    """Test creating message via service."""
    company = await company_factory()
    customer = await Customer.create(user_id="create_msg_service_user", company=company)
    _ = await Thread.create(
        thread_id="thread_create_msg_service",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )
    service = chat_service

    message = await service.create_message(
        thread_id="thread_create_msg_service",
        role=ChatMessageRole.USER,
        content="Hello from service",
        message_id="msg_service",
        metadata={"source": "test"},
    )

    assert message.message_id == "msg_service"
    assert message.role == ChatMessageRole.USER
    assert message.content == "Hello from service"
    assert message.metadata == {"source": "test"}


@pytest.mark.asyncio
async def test_chat_service_create_messages_batch(company_factory, chat_service):
    """Test creating multiple messages via service."""
    company = await company_factory()
    customer = await Customer.create(user_id="batch_msg_service_user", company=company)
    _ = await Thread.create(
        thread_id="thread_batch_msg_service",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )
    service = chat_service

    messages_data = [
        {"role": ChatMessageRole.USER, "content": "Message 1"},
        {"role": ChatMessageRole.ASSISTANT, "content": "Message 2"},
        {
            "role": ChatMessageRole.USER,
            "content": "Message 3",
            "metadata": {"source": "test"},
        },
    ]

    messages = await service.create_messages_batch(thread_id="thread_batch_msg_service", messages=messages_data)

    assert len(messages) == 3
    assert messages[0].content == "Message 1"
    assert messages[1].content == "Message 2"
    assert messages[2].content == "Message 3"


@pytest.mark.asyncio
async def test_chat_service_get_thread_messages(company_factory, chat_service):
    """Test getting thread messages with pagination."""
    company = await company_factory()
    customer = await Customer.create(user_id="get_msg_service_user", company=company)
    thread = await Thread.create(
        thread_id="thread_get_msg_service",
        customer=customer,
        company=company,
        channel_type="telegram",
    )

    # Create messages
    for i in range(10):
        await ChatMessage.create(
            message_id=f"msg_get_{i}",
            thread=thread,
            role=ChatMessageRole.USER,
            content=f"Message {i}",
        )

    service = chat_service

    messages, total = await service.get_thread_messages(thread_id="thread_get_msg_service", limit=5, offset=0)

    assert total == 10
    assert len(messages) == 5


@pytest.mark.asyncio
async def test_chat_service_get_recent_history(company_factory, chat_service):
    """Test getting recent message history."""
    company = await company_factory()
    customer = await Customer.create(user_id="history_service_user", company=company)
    thread = await Thread.create(
        thread_id="thread_history_service",
        customer=customer,
        company=company,
        channel_type="telegram",
    )

    # Create messages
    for i in range(10):
        await ChatMessage.create(
            message_id=f"msg_history_{i}",
            thread=thread,
            role=ChatMessageRole.USER if i % 2 == 0 else ChatMessageRole.ASSISTANT,
            content=f"Message {i}",
        )

    service = chat_service

    # Get all history
    history = await service.get_recent_history("thread_history_service")
    assert len(history) == 10

    # Get limited history
    history = await service.get_recent_history("thread_history_service", limit=5)
    assert len(history) == 5


@pytest.mark.asyncio
async def test_chat_service_get_recent_history_thread_not_found(chat_service):
    """Test getting history for non-existent thread returns empty list."""
    service = chat_service

    history = await service.get_recent_history("nonexistent_thread")
    assert history == []


@pytest.mark.asyncio
async def test_chat_service_update_message_status(company_factory, chat_service):
    """Test updating message status."""
    company = await company_factory()
    customer = await Customer.create(user_id="status_msg_service_user", company=company)
    thread = await Thread.create(
        thread_id="thread_status_msg_service",
        customer=customer,
        company=company,
        channel_type="telegram",
    )
    message = await ChatMessage.create(
        message_id="msg_status_service",
        thread=thread,
        role=ChatMessageRole.USER,
        content="Test",
        status=ChatMessageStatus.PENDING,
    )
    _ = message  # Created for test data
    service = chat_service

    delivered_at = datetime.now(tz=UTC)
    updated = await service.update_message_status(
        message_id="msg_status_service",
        status=ChatMessageStatus.SENT,
        delivered_at=delivered_at,
        metadata={"delivery_method": "push"},
    )

    assert updated.status == ChatMessageStatus.SENT
    assert updated.delivered_at == delivered_at
    assert updated.metadata == {"delivery_method": "push"}


@pytest.mark.asyncio
async def test_chat_service_get_langfuse_session_id(company_factory, chat_service):
    """Test getting Langfuse session ID."""
    company = await company_factory()
    _ = await Customer.create(
        user_id="langfuse_service_user",
        company=company,
        langfuse_sessions={"conv_1": "session_123"},
    )
    service = chat_service

    session_response = await service.get_langfuse_session_id("langfuse_service_user", company.id, "conv_1")
    assert session_response.session_id == "session_123"

    # Non-existent conversation
    session_response = await service.get_langfuse_session_id("langfuse_service_user", company.id, "conv_nonexistent")
    assert session_response.session_id is None

    # None conversation_id
    session_response = await service.get_langfuse_session_id("langfuse_service_user", company.id, None)
    assert session_response.session_id is None


@pytest.mark.asyncio
async def test_chat_service_create_langfuse_session(company_factory, chat_service):
    """Test creating Langfuse session."""
    company = await company_factory()
    customer = await Customer.create(user_id="create_langfuse_service_user", company=company)
    service = chat_service

    session_id = await service.create_langfuse_session("create_langfuse_service_user", company.id, "conv_new")

    assert session_id is not None
    assert len(session_id) > 0

    # Verify session was saved
    updated = await Customer.get(id=customer.id)
    assert updated.langfuse_sessions == {"conv_new": session_id}


@pytest.mark.asyncio
async def test_chat_service_create_langfuse_session_requires_conversation_id(company_factory, chat_service):
    """Test that creating Langfuse session requires conversation_id."""
    company = await company_factory()
    service = chat_service

    with pytest.raises(ValueError, match="conversation_id is required"):
        await service.create_langfuse_session(
            "user",
            company.id,
            "",  # Empty string should raise error
        )
    with pytest.raises(ValueError, match="conversation_id is required"):
        await service.create_langfuse_session(
            "user",
            company.id,
            "",  # Empty string should raise error
        )
