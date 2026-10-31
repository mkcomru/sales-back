"""Model tests for customers, threads, and chat messages."""

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


@pytest.mark.asyncio
async def test_customer_default_fields(company_factory):
    """Test Customer model default values."""
    company = await company_factory()
    customer = Customer(
        user_id="user_123",
        company=company,
    )
    await customer.save()

    assert customer.user_id == "user_123"
    assert customer.company_id == company.id
    assert customer.rejected is False
    assert customer.rejection_reason is None
    assert customer.customer_fields == {}
    assert customer.langfuse_sessions == {}
    assert customer.meta == {}
    assert customer.created_at is not None
    assert customer.updated_at is not None


@pytest.mark.asyncio
async def test_customer_with_meta(company_factory):
    """Test Customer model with meta field containing username."""
    company = await company_factory()
    customer = Customer(
        user_id="user_456",
        company=company,
        meta={"username": "testuser", "phone": "+1234567890"},
    )
    await customer.save()

    assert customer.meta == {"username": "testuser", "phone": "+1234567890"}
    assert customer.meta.get("username") == "testuser"


@pytest.mark.asyncio
async def test_customer_unique_user_id(company_factory):
    """Test Customer user_id uniqueness constraint."""
    from tortoise.exceptions import IntegrityError

    company = await company_factory()
    customer1 = Customer(user_id="unique_user", company=company)
    await customer1.save()

    customer2 = Customer(user_id="unique_user", company=company)
    with pytest.raises(IntegrityError):
        await customer2.save()


@pytest.mark.asyncio
async def test_thread_default_fields(company_factory):
    """Test Thread model default values."""
    company = await company_factory()
    customer = await Customer.create(user_id="user_789", company=company)

    thread = Thread(
        thread_id="thread_001",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
        conversation_id="conv_001",
    )
    await thread.save()

    assert thread.thread_id == "thread_001"
    assert thread.customer_id == customer.id
    assert thread.company_id == company.id
    assert thread.channel_type == "telegram"
    assert thread.conversation_id == "conv_001"
    assert thread.state == ThreadState.ACTIVE
    assert thread.assistant_mode == AssistantMode.ACTIVE
    assert thread.metadata == {}
    assert thread.created_at is not None
    assert thread.updated_at is not None


@pytest.mark.asyncio
async def test_thread_unique_thread_id(company_factory):
    """Test Thread thread_id uniqueness constraint."""
    from tortoise.exceptions import IntegrityError

    company = await company_factory()
    customer = await Customer.create(user_id="user_999", company=company)

    thread1 = Thread(
        thread_id="unique_thread",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )
    await thread1.save()

    thread2 = Thread(
        thread_id="unique_thread",
        customer=customer,
        company=company,
        channel_type="whatsapp",
        connector_id="test-connector",
    )
    with pytest.raises(IntegrityError):
        await thread2.save()


@pytest.mark.asyncio
async def test_chat_message_default_fields(company_factory):
    """Test ChatMessage model default values."""
    company = await company_factory()
    customer = await Customer.create(user_id="user_msg", company=company)
    thread = await Thread.create(
        thread_id="thread_msg",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )

    message = ChatMessage(
        message_id="msg_001",
        thread=thread,
        role=ChatMessageRole.USER,
        content="Hello, world!",
    )
    await message.save()

    assert message.message_id == "msg_001"
    assert message.thread_id == thread.id
    assert message.role == ChatMessageRole.USER
    assert message.content == "Hello, world!"
    assert message.status == ChatMessageStatus.PENDING
    assert message.metadata == {}
    assert message.attachments == []
    assert message.reply_to is None
    assert message.delivered_at is None
    assert message.created_at is not None


@pytest.mark.asyncio
async def test_chat_message_unique_message_id(company_factory):
    """Test ChatMessage message_id uniqueness constraint."""
    from tortoise.exceptions import IntegrityError

    company = await company_factory()
    customer = await Customer.create(user_id="user_dup", company=company)
    thread = await Thread.create(
        thread_id="thread_dup",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )

    message1 = ChatMessage(
        message_id="unique_msg",
        thread=thread,
        role=ChatMessageRole.USER,
        content="First",
    )
    await message1.save()

    message2 = ChatMessage(
        message_id="unique_msg",
        thread=thread,
        role=ChatMessageRole.ASSISTANT,
        content="Second",
    )
    with pytest.raises(IntegrityError):
        await message2.save()


@pytest.mark.asyncio
async def test_customer_thread_relationship(company_factory):
    """Test Customer-Thread relationship."""
    company = await company_factory()
    customer = await Customer.create(user_id="user_rel", company=company)

    _ = await Thread.create(
        thread_id="thread_rel_1",
        customer=customer,
        company=company,
        channel_type="telegram",
    )
    _ = await Thread.create(
        thread_id="thread_rel_2",
        customer=customer,
        company=company,
        channel_type="whatsapp",
    )

    # Test reverse relation
    threads = await customer.threads.all()
    assert len(threads) == 2
    assert {t.thread_id for t in threads} == {"thread_rel_1", "thread_rel_2"}


@pytest.mark.asyncio
async def test_thread_message_relationship(company_factory):
    """Test Thread-ChatMessage relationship."""
    company = await company_factory()
    customer = await Customer.create(user_id="user_msg_rel", company=company)
    thread = await Thread.create(
        thread_id="thread_msg_rel",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )

    _ = await ChatMessage.create(
        message_id="msg_rel_1",
        thread=thread,
        role=ChatMessageRole.USER,
        content="Message 1",
    )
    _ = await ChatMessage.create(
        message_id="msg_rel_2",
        thread=thread,
        role=ChatMessageRole.ASSISTANT,
        content="Message 2",
    )

    # Test reverse relation
    messages = await thread.messages.all()
    assert len(messages) == 2
    assert {m.message_id for m in messages} == {"msg_rel_1", "msg_rel_2"}


@pytest.mark.asyncio
async def test_customer_cascade_delete(company_factory):
    """Test that deleting customer cascades to threads and messages."""
    company = await company_factory()
    customer = await Customer.create(user_id="user_cascade", company=company)
    thread = await Thread.create(
        thread_id="thread_cascade",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )
    message = await ChatMessage.create(
        message_id="msg_cascade",
        thread=thread,
        role=ChatMessageRole.USER,
        content="Test",
    )

    await customer.delete()

    # Thread should be deleted
    thread_exists = await Thread.exists(id=thread.id)
    assert thread_exists is False

    # Message should be deleted
    message_exists = await ChatMessage.exists(id=message.id)
    assert message_exists is False


@pytest.mark.asyncio
async def test_thread_cascade_delete(company_factory):
    """Test that deleting thread cascades to messages."""
    company = await company_factory()
    customer = await Customer.create(user_id="user_thread_cascade", company=company)
    thread = await Thread.create(
        thread_id="thread_cascade_msg",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )
    message = await ChatMessage.create(
        message_id="msg_thread_cascade",
        thread=thread,
        role=ChatMessageRole.USER,
        content="Test",
    )

    await thread.delete()

    # Message should be deleted
    message_exists = await ChatMessage.exists(id=message.id)
    assert message_exists is False

    # Customer should still exist
    customer_exists = await Customer.exists(id=customer.id)
    assert customer_exists is True
