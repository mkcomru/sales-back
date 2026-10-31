"""Repository tests for customers, threads, and chat messages."""

from datetime import UTC, datetime

import pytest

from src.backend.modules.chat.models import (
    AssistantMode,
    ChatMessage,
    ChatMessageRole,
    ChatMessageStatus,
    ChatMessageType,
    Customer,
    Thread,
    ThreadState,
)
from src.backend.modules.chat.repository import (
    ChatMessagesRepository,
    CustomersRepository,
    ThreadsRepository,
)


@pytest.mark.asyncio
async def test_customers_repo_get_or_create_new(company_factory):
    """Test creating new customer via repository."""
    company = await company_factory()
    repo = CustomersRepository()

    customer, created = await repo.get_or_create(
        user_id="new_user", company_id=company.id, meta={"username": "testuser"}
    )

    assert created is True
    assert customer.user_id == "new_user"
    assert customer.company_id == company.id
    assert customer.meta == {"username": "testuser"}


@pytest.mark.asyncio
async def test_customers_repo_get_or_create_existing(company_factory):
    """Test getting existing customer via repository."""
    company = await company_factory()
    existing = await Customer.create(user_id="existing_user", company=company, meta={"username": "olduser"})
    repo = CustomersRepository()

    customer, created = await repo.get_or_create(
        user_id="existing_user", company_id=company.id, meta={"username": "newuser"}
    )

    assert created is False
    assert customer.id == existing.id
    assert customer.meta == {"username": "newuser"}  # Should be updated


@pytest.mark.asyncio
async def test_customers_repo_get_by_user_id(company_factory):
    """Test getting customer by user_id."""
    company = await company_factory()
    customer = await Customer.create(user_id="find_user", company=company)
    repo = CustomersRepository()

    found = await repo.get_by_user_id("find_user", company.id)
    assert found is not None
    assert found.id == customer.id

    not_found = await repo.get_by_user_id("nonexistent", company.id)
    assert not_found is None


@pytest.mark.asyncio
async def test_customers_repo_update_customer_fields(company_factory):
    """Test updating customer quiz answers."""
    company = await company_factory()
    customer = await Customer.create(user_id="quiz_user", company=company, customer_fields={"field1": "value1"})
    repo = CustomersRepository()

    updated, changed_fields = await repo.update_customer_fields(customer, {"field2": "value2"})

    assert updated.customer_fields == {"field1": "value1", "field2": "value2"}
    assert "field2" in changed_fields
    assert changed_fields["field2"]["old"] is None
    assert changed_fields["field2"]["new"] == "value2"


@pytest.mark.asyncio
async def test_customers_repo_mark_rejected(company_factory):
    """Test marking customer as rejected."""
    company = await company_factory()
    customer = await Customer.create(user_id="reject_user", company=company)
    repo = CustomersRepository()

    updated = await repo.mark_rejected(customer, "Spam")

    assert updated.rejected is True
    assert updated.rejection_reason == "Spam"


@pytest.mark.asyncio
async def test_customers_repo_reset_profile(company_factory):
    """Test resetting customer profile."""
    company = await company_factory()
    customer = await Customer.create(
        user_id="reset_user",
        company=company,
        customer_fields={"field1": "value1"},
        rejected=True,
        rejection_reason="Test",
    )
    repo = CustomersRepository()

    updated = await repo.reset_profile(customer)

    assert updated.customer_fields == {}
    assert updated.rejected is False
    assert updated.rejection_reason is None


@pytest.mark.asyncio
async def test_customers_repo_langfuse_sessions(company_factory):
    """Test Langfuse session management."""
    company = await company_factory()
    customer = await Customer.create(user_id="langfuse_user", company=company)
    repo = CustomersRepository()

    # Get non-existent session
    session = await repo.get_langfuse_session(customer, "conv_1")
    assert session is None

    # Create session
    updated = await repo.create_langfuse_session(customer, "conv_1", "session_123")
    assert updated.langfuse_sessions == {"conv_1": "session_123"}

    # Get existing session
    session = await repo.get_langfuse_session(customer, "conv_1")
    assert session == "session_123"


@pytest.mark.asyncio
async def test_threads_repo_get_by_thread_id(company_factory):
    """Test getting thread by thread_id."""
    company = await company_factory()
    customer = await Customer.create(user_id="thread_user", company=company)
    thread = await Thread.create(
        thread_id="thread_find",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )
    repo = ThreadsRepository()

    found = await repo.get_by_thread_id("thread_find")
    assert found is not None
    assert found.id == thread.id

    not_found = await repo.get_by_thread_id("nonexistent")
    assert not_found is None


@pytest.mark.asyncio
async def test_threads_repo_get_or_create_new(company_factory):
    """Test creating new thread via repository."""
    company = await company_factory()
    customer = await Customer.create(user_id="thread_new", company=company)
    repo = ThreadsRepository()

    thread, created = await repo.get_or_create(
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
        conversation_id="conv_new",
    )

    assert created is True
    assert thread.customer_id == customer.id
    assert thread.company_id == company.id
    assert thread.channel_type == "telegram"
    assert thread.connector_id == "test-connector"
    assert thread.conversation_id == "conv_new"
    assert thread.state == ThreadState.ACTIVE


@pytest.mark.asyncio
async def test_threads_repo_get_or_create_existing(company_factory):
    """Test getting existing thread via repository."""
    company = await company_factory()
    customer = await Customer.create(user_id="thread_existing", company=company)
    existing = await Thread.create(
        thread_id="thread_existing_id",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
        conversation_id="conv_existing",
    )
    repo = ThreadsRepository()

    thread, created = await repo.get_or_create(
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
        conversation_id="conv_existing",
    )

    assert created is False
    assert thread.id == existing.id


@pytest.mark.asyncio
async def test_threads_repo_list_by_company(company_factory):
    """Test listing threads by company with filters."""
    company = await company_factory()
    customer1 = await Customer.create(user_id="list_user1", company=company)
    customer2 = await Customer.create(user_id="list_user2", company=company)

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
    _ = await Thread.create(
        thread_id="thread_list_3",
        customer=customer1,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
        state=ThreadState.ACTIVE,
    )

    repo = ThreadsRepository()

    # List all threads
    threads, total = await repo.list_by_company(company_id=company.id)
    assert total == 3
    assert len(threads) == 3

    # Filter by channel_type
    threads, total = await repo.list_by_company(company_id=company.id, channel_type="telegram")
    assert total == 2
    assert {t.thread_id for t in threads} == {"thread_list_1", "thread_list_3"}

    # Filter by state
    threads, total = await repo.list_by_company(company_id=company.id, state=ThreadState.ACTIVE)
    assert total == 2
    assert {t.thread_id for t in threads} == {"thread_list_1", "thread_list_3"}

    # Filter by both
    threads, total = await repo.list_by_company(
        company_id=company.id,
        channel_type="telegram",
        state=ThreadState.ACTIVE,
    )
    assert total == 2
    assert {t.thread_id for t in threads} == {"thread_list_1", "thread_list_3"}


@pytest.mark.asyncio
async def test_threads_repo_update_state(company_factory):
    """Test updating thread state."""
    company = await company_factory()
    customer = await Customer.create(user_id="state_user", company=company)
    thread = await Thread.create(
        thread_id="thread_state",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
        state=ThreadState.ACTIVE,
    )
    repo = ThreadsRepository()

    updated = await repo.update_state(
        thread=thread,
        state=ThreadState.HANDOFF,
        reason="Manual handoff",
        metadata={"handoff_by": "manager_1"},
    )

    assert updated.state == ThreadState.HANDOFF
    assert "last_state_change" in updated.metadata
    assert updated.metadata["handoff_by"] == "manager_1"


@pytest.mark.asyncio
async def test_threads_repo_set_assistant_mode(company_factory):
    """Test controlling assistant mode."""
    company = await company_factory()
    customer = await Customer.create(user_id="assistant_user", company=company)
    thread = await Thread.create(
        thread_id="thread_assistant",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )
    repo = ThreadsRepository()

    updated = await repo.set_assistant_mode(thread, AssistantMode.INACTIVE, "Manual stop")

    assert updated.assistant_mode == AssistantMode.INACTIVE
    assert "last_assistant_control" in updated.metadata


@pytest.mark.asyncio
async def test_chat_messages_repo_get_by_message_id(company_factory):
    """Test getting message by message_id."""
    company = await company_factory()
    customer = await Customer.create(user_id="msg_user", company=company)
    thread = await Thread.create(
        thread_id="thread_msg",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )
    message = await ChatMessage.create(
        message_id="msg_find",
        thread=thread,
        role=ChatMessageRole.USER,
        content="Test",
    )
    repo = ChatMessagesRepository()

    found = await repo.get_by_message_id("msg_find")
    assert found is not None
    assert found.id == message.id

    not_found = await repo.get_by_message_id("nonexistent")
    assert not_found is None


@pytest.mark.asyncio
async def test_chat_messages_repo_create_message(company_factory):
    """Test creating message via repository."""
    company = await company_factory()
    customer = await Customer.create(user_id="create_msg_user", company=company)
    thread = await Thread.create(
        thread_id="thread_create_msg",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )
    repo = ChatMessagesRepository()

    message = await repo.create_message(
        thread=thread,
        role=ChatMessageRole.USER,
        content="Hello",
        message_id="msg_custom",
        metadata={"source": "test"},
        attachments=[{"type": "image", "url": "test.jpg"}],
    )

    assert message.message_id == "msg_custom"
    assert message.role == ChatMessageRole.USER
    assert message.content == "Hello"
    assert message.metadata == {"source": "test"}
    assert message.attachments == [{"type": "image", "url": "test.jpg"}]


@pytest.mark.asyncio
async def test_chat_messages_repo_list_by_thread(company_factory):
    """Test listing messages by thread with pagination."""
    company = await company_factory()
    customer = await Customer.create(user_id="list_msg_user", company=company)
    thread = await Thread.create(
        thread_id="thread_list_msg",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )

    # Create multiple messages
    for i in range(5):
        await ChatMessage.create(
            message_id=f"msg_list_{i}",
            thread=thread,
            role=ChatMessageRole.USER,
            content=f"Message {i}",
        )

    repo = ChatMessagesRepository()

    # List all
    messages, total = await repo.list_by_thread(thread)
    assert total == 5
    assert len(messages) == 5

    # Pagination
    messages, total = await repo.list_by_thread(thread, limit=2, offset=0)
    assert total == 5
    assert len(messages) == 2

    messages, total = await repo.list_by_thread(thread, limit=2, offset=2)
    assert total == 5
    assert len(messages) == 2


@pytest.mark.asyncio
async def test_chat_messages_repo_get_recent_history(company_factory):
    """Test getting recent message history."""
    company = await company_factory()
    customer = await Customer.create(user_id="history_user", company=company)
    thread = await Thread.create(
        thread_id="thread_history",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )

    # Create messages
    for i in range(10):
        await ChatMessage.create(
            message_id=f"msg_history_{i}",
            thread=thread,
            role=ChatMessageRole.USER if i % 2 == 0 else ChatMessageRole.ASSISTANT,
            content=f"Message {i}",
        )

    repo = ChatMessagesRepository()

    # Get all history
    history = await repo.get_recent_history(thread)
    assert len(history) == 10
    assert history[0]["content"] == "Message 0"  # Should be in chronological order

    # Get limited history
    history = await repo.get_recent_history(thread, limit=5)
    assert len(history) == 5
    assert history[-1]["content"] == "Message 9"  # Most recent


@pytest.mark.asyncio
async def test_chat_messages_repo_get_recent_history_excludes_internal_notes(company_factory):
    company = await company_factory()
    customer = await Customer.create(user_id="history_notes_user", company=company)
    thread = await Thread.create(
        thread_id="thread_history_notes",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )

    await ChatMessage.create(
        message_id="msg_visible_1",
        thread=thread,
        role=ChatMessageRole.USER,
        content="Hello",
        type=ChatMessageType.TEXT,
    )
    await ChatMessage.create(
        message_id="msg_note_1",
        thread=thread,
        role=ChatMessageRole.MANAGER,
        content="Secret",
        type=ChatMessageType.INTERNAL_NOTE,
    )
    await ChatMessage.create(
        message_id="msg_visible_2",
        thread=thread,
        role=ChatMessageRole.ASSISTANT,
        content="Reply",
        type=ChatMessageType.TEXT,
    )

    repo = ChatMessagesRepository()
    history = await repo.get_recent_history(thread, limit=2, exclude_internal_notes=True)
    assert len(history) == 2
    contents = {row["content"] for row in history}
    assert contents == {"Hello", "Reply"}
    assert all("transcription" in row for row in history)


@pytest.mark.asyncio
async def test_chat_messages_repo_update_status(company_factory):
    """Test updating message status."""
    company = await company_factory()
    customer = await Customer.create(user_id="status_user", company=company)
    thread = await Thread.create(
        thread_id="thread_status",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )
    message = await ChatMessage.create(
        message_id="msg_status",
        thread=thread,
        role=ChatMessageRole.USER,
        content="Test",
        status=ChatMessageStatus.PENDING,
    )
    repo = ChatMessagesRepository()

    delivered_at = datetime.now(tz=UTC)
    updated = await repo.update_status(
        message=message,
        status=ChatMessageStatus.SENT,
        delivered_at=delivered_at,
        metadata={"delivery_method": "push"},
    )

    assert updated.status == ChatMessageStatus.SENT
    assert updated.delivered_at == delivered_at
    assert updated.metadata == {"delivery_method": "push"}


@pytest.mark.asyncio
async def test_chat_messages_repo_delete_by_thread(company_factory):
    """Test deleting all messages in a thread."""
    company = await company_factory()
    customer = await Customer.create(user_id="delete_user", company=company)
    thread = await Thread.create(
        thread_id="thread_delete",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )

    # Create messages
    for i in range(5):
        await ChatMessage.create(
            message_id=f"msg_delete_{i}",
            thread=thread,
            role=ChatMessageRole.USER,
            content=f"Message {i}",
        )

    repo = ChatMessagesRepository()

    deleted_count = await repo.delete_by_thread(thread)
    assert deleted_count == 5

    # Verify messages are deleted
    messages, total = await repo.list_by_thread(thread)
    assert total == 0
    assert len(messages) == 0
