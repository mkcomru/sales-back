"""Router tests for chat messages, threads, and customers."""

from datetime import UTC, datetime

import httpx
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
async def test_internal_get_or_create_customer_new(api_client: httpx.AsyncClient, company_factory, service_headers):
    """Test creating new customer via internal API."""
    company = await company_factory()

    response = await api_client.post(
        "/api/v1/internal/chat/customers/get-or-create",
        headers=service_headers,
        json={
            "user_id": "api_user_new",
            "company_id": company.id,
            "meta": {"username": "apiuser"},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "api_user_new"
    assert data["company_id"] == company.id
    assert data["created"] is True
    assert isinstance(data["customer_id"], int)


@pytest.mark.asyncio
async def test_internal_get_or_create_customer_existing(
    api_client: httpx.AsyncClient, company_factory, service_headers
):
    """Test getting existing customer via internal API."""
    company = await company_factory()
    customer = await Customer.create(
        user_id="api_user_existing",
        company=company,
        meta={"username": "old"},
    )

    response = await api_client.post(
        "/api/v1/internal/chat/customers/get-or-create",
        headers=service_headers,
        json={
            "user_id": "api_user_existing",
            "company_id": company.id,
            "meta": {"username": "new"},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["customer_id"] == customer.id
    assert data["created"] is False

    # Verify meta was updated
    updated = await Customer.get(id=customer.id)
    assert updated.meta == {"username": "new"}


@pytest.mark.asyncio
async def test_internal_get_customer_profile(api_client: httpx.AsyncClient, company_factory, service_headers):
    """Test getting customer profile via internal API."""
    company = await company_factory()
    _ = await Customer.create(
        user_id="api_profile_user",
        company=company,
        customer_fields={"field1": "value1"},
        rejected=False,
    )

    response = await api_client.get(
        "/api/v1/internal/chat/customers/api_profile_user/profile",
        params={"company_id": company.id},
        headers=service_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["customer_fields"] == {"field1": "value1"}
    assert data["rejected"] is False


@pytest.mark.asyncio
async def test_internal_get_customer_answers(api_client: httpx.AsyncClient, company_factory, service_headers):
    """Test getting customer answers via internal API."""
    company = await company_factory()
    _ = await Customer.create(
        user_id="api_answers_user",
        company=company,
        customer_fields={"field1": "value1", "field2": "value2"},
    )

    response = await api_client.get(
        "/api/v1/internal/chat/customers/api_answers_user/answers",
        params={"company_id": company.id},
        headers=service_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data == {"field1": "value1", "field2": "value2"}


@pytest.mark.asyncio
async def test_internal_update_customer_fields(api_client: httpx.AsyncClient, company_factory, service_headers):
    """Test updating customer fields via internal API (unified endpoint)."""
    from src.backend.modules.fields.models import AnswerType, Field, FieldLevel

    company = await company_factory()
    customer = await Customer.create(
        user_id="api_update_user",
        company=company,
        customer_fields={"field1": "value1"},
    )

    await Field.create(
        company=company,
        name="field1",
        question="Field 1",
        answer_type=AnswerType.STRING,
        level=FieldLevel.CUSTOMER,
    )
    await Field.create(
        company=company,
        name="field2",
        question="Field 2",
        answer_type=AnswerType.STRING,
        level=FieldLevel.CUSTOMER,
    )

    response = await api_client.patch(
        "/api/v1/internal/chat/customers/api_update_user/fields",
        headers=service_headers,
        json={
            "company_id": company.id,
            "updates": {"field2": "value2"},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "field2" in data.get("updated_customer", [])

    updated = await Customer.get(id=customer.id)
    assert updated.customer_fields == {"field1": "value1", "field2": "value2"}


@pytest.mark.asyncio
async def test_internal_reject_customer(api_client: httpx.AsyncClient, company_factory, service_headers):
    """Test rejecting customer via internal API."""
    company = await company_factory()
    customer = await Customer.create(user_id="api_reject_user", company=company)

    response = await api_client.post(
        "/api/v1/internal/chat/customers/api_reject_user/reject",
        headers=service_headers,
        json={
            "company_id": company.id,
            "reason": "Spam",
        },
    )

    assert response.status_code == 204

    # Verify rejection
    updated = await Customer.get(id=customer.id)
    assert updated.rejected is True
    assert updated.rejection_reason == "Spam"


@pytest.mark.asyncio
async def test_internal_reset_customer_profile(api_client: httpx.AsyncClient, company_factory, service_headers):
    """Test resetting customer profile via internal API."""
    company = await company_factory()
    customer = await Customer.create(
        user_id="api_reset_user",
        company=company,
        customer_fields={"field1": "value1"},
        rejected=True,
    )
    thread = await Thread.create(
        thread_id="thread_reset_api",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )
    await ChatMessage.create(
        message_id="msg_reset_api",
        thread=thread,
        role=ChatMessageRole.USER,
        content="Test",
    )

    response = await api_client.delete(
        "/api/v1/internal/chat/customers/api_reset_user/profile",
        params={"company_id": company.id},
        headers=service_headers,
    )

    assert response.status_code == 204

    # Verify reset
    updated = await Customer.get(id=customer.id)
    assert updated.customer_fields == {}
    assert updated.rejected is False


@pytest.mark.asyncio
async def test_internal_get_langfuse_session(api_client: httpx.AsyncClient, company_factory, service_headers):
    """Test getting Langfuse session via internal API."""
    company = await company_factory()
    _ = await Customer.create(
        user_id="api_langfuse_user",
        company=company,
        langfuse_sessions={"conv_1": "session_123"},
    )

    response = await api_client.get(
        "/api/v1/internal/chat/customers/api_langfuse_user/langfuse-session",
        params={"company_id": company.id, "conversation_id": "conv_1"},
        headers=service_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "session_123"


@pytest.mark.asyncio
async def test_internal_create_langfuse_session(api_client: httpx.AsyncClient, company_factory, service_headers):
    """Test creating Langfuse session via internal API."""
    company = await company_factory()
    customer = await Customer.create(user_id="api_create_langfuse_user", company=company)

    response = await api_client.post(
        "/api/v1/internal/chat/customers/api_create_langfuse_user/langfuse-session",
        headers=service_headers,
        json={
            "company_id": company.id,
            "conversation_id": "conv_new",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] is not None

    # Verify session was saved
    updated = await Customer.get(id=customer.id)
    assert "conv_new" in updated.langfuse_sessions


@pytest.mark.asyncio
async def test_internal_get_or_create_thread_new(api_client: httpx.AsyncClient, company_factory, service_headers):
    """Test creating new thread via internal API."""
    company = await company_factory()
    _ = await Customer.create(user_id="api_thread_new", company=company)

    response = await api_client.post(
        "/api/v1/internal/chat/threads/get-or-create",
        headers=service_headers,
        json={
            "user_id": "api_thread_new",
            "company_id": company.id,
            "channel_type": "telegram",
            "connector_id": "test-connector",
            "conversation_id": "conv_api_new",
            "meta": {"username": "threaduser"},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "api_thread_new"
    assert data["company_id"] == company.id
    assert data["channel_type"] == "telegram"
    assert data["connector_id"] == "test-connector"
    assert data["conversation_id"] == "conv_api_new"
    assert data["created"] is True
    assert isinstance(data["thread_id"], str)


@pytest.mark.asyncio
async def test_internal_get_or_create_thread_existing(api_client: httpx.AsyncClient, company_factory, service_headers):
    """Test getting existing thread via internal API."""
    company = await company_factory()
    customer = await Customer.create(user_id="api_thread_existing", company=company)
    _ = await Thread.create(
        thread_id="thread_api_existing",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
        conversation_id="conv_api_existing",
    )

    response = await api_client.post(
        "/api/v1/internal/chat/threads/get-or-create",
        headers=service_headers,
        json={
            "user_id": "api_thread_existing",
            "company_id": company.id,
            "channel_type": "telegram",
            "connector_id": "test-connector",
            "conversation_id": "conv_api_existing",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["thread_id"] == "thread_api_existing"
    assert data["created"] is False


@pytest.mark.asyncio
async def test_internal_get_thread_history(api_client: httpx.AsyncClient, company_factory, service_headers):
    """Test getting thread history via internal API."""
    company = await company_factory()
    customer = await Customer.create(user_id="api_history_user", company=company)
    thread = await Thread.create(
        thread_id="thread_api_history",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )

    # Create messages
    for i in range(5):
        await ChatMessage.create(
            message_id=f"msg_history_{i}",
            thread=thread,
            role=ChatMessageRole.USER if i % 2 == 0 else ChatMessageRole.ASSISTANT,
            content=f"Message {i}",
        )

    response = await api_client.post(
        "/api/v1/internal/chat/threads/thread_api_history/history",
        headers=service_headers,
        json={"limit": 10},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5
    assert data[0]["content"] == "Message 0"
    assert data[-1]["content"] == "Message 4"


@pytest.mark.asyncio
async def test_internal_ingest_messages(api_client: httpx.AsyncClient, company_factory, service_headers):
    """Test ingesting messages via internal API."""
    company = await company_factory()
    customer = await Customer.create(user_id="api_ingest_user", company=company)
    thread = await Thread.create(
        thread_id="thread_api_ingest",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )

    response = await api_client.post(
        "/api/v1/internal/chat/threads/thread_api_ingest/messages",
        headers=service_headers,
        json={
            "source": "sales_agent",
            "trace_id": "trace_123",
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
                    "message_id": "msg_ingest_1",
                },
                {
                    "role": "assistant",
                    "content": "Hi there!",
                    "message_id": "msg_ingest_2",
                },
            ],
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert data["thread_id"] == "thread_api_ingest"
    assert data["accepted"] == 2
    assert data["trace_id"] == "trace_123"

    # Verify messages were created
    messages = await ChatMessage.filter(thread=thread).all()
    assert len(messages) == 2


@pytest.mark.asyncio
async def test_internal_patch_message_status(api_client: httpx.AsyncClient, company_factory, service_headers):
    """Test patching message status via internal API."""
    company = await company_factory()
    customer = await Customer.create(user_id="api_patch_user", company=company)
    thread = await Thread.create(
        thread_id="thread_api_patch",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )
    message = await ChatMessage.create(
        message_id="msg_api_patch",
        thread=thread,
        role=ChatMessageRole.USER,
        content="Test",
        status=ChatMessageStatus.PENDING,
    )

    _ = message  # Created for test data
    delivered_at = datetime.now(tz=UTC).isoformat()
    response = await api_client.patch(
        "/api/v1/internal/chat/messages/msg_api_patch",
        headers=service_headers,
        json={
            "status": "sent",
            "delivered_at": delivered_at,
            "metadata": {"delivery_method": "push"},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "sent"
    assert data["metadata"] == {"delivery_method": "push"}


@pytest.mark.asyncio
async def test_internal_update_thread_state(api_client: httpx.AsyncClient, company_factory, service_headers):
    """Test updating thread state via internal API."""
    company = await company_factory()
    customer = await Customer.create(user_id="api_state_user", company=company)
    thread = await Thread.create(
        thread_id="thread_api_state",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
        state=ThreadState.ACTIVE,
    )

    response = await api_client.post(
        "/api/v1/internal/chat/threads/thread_api_state/state",
        headers=service_headers,
        json={
            "state": "handoff",
            "reason": "Manual handoff",
            "metadata": {"handoff_by": "manager_1"},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["thread_id"] == "thread_api_state"
    assert data["previous_state"] == "active"
    assert data["state"] == "handoff"

    # Verify state was updated
    updated = await Thread.get(id=thread.id)
    assert updated.state == ThreadState.HANDOFF


@pytest.mark.asyncio
async def test_public_list_threads(api_client: httpx.AsyncClient, authenticated_user_with_token):
    """Test listing threads via public API."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]

    customer = await Customer.create(user_id="public_list_user", company=company)
    thread = await Thread.create(
        thread_id="thread_public_list",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
        state=ThreadState.ACTIVE,
    )
    await ChatMessage.create(
        message_id="msg_public_list",
        thread=thread,
        role=ChatMessageRole.USER,
        content="Last message",
    )

    response = await api_client.get(
        f"/api/v1/companies/{company.id}/threads",
        params={"limit": 10, "offset": 0},
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1
    assert any(t["thread_id"] == "thread_public_list" for t in data["items"])


@pytest.mark.asyncio
async def test_public_list_threads_with_filters(api_client: httpx.AsyncClient, authenticated_user_with_token):
    """Test listing threads with filters via public API."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]

    customer = await Customer.create(user_id="public_filter_user", company=company)
    _ = await Thread.create(
        thread_id="thread_public_filter_1",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
        state=ThreadState.ACTIVE,
    )
    _ = await Thread.create(
        thread_id="thread_public_filter_2",
        customer=customer,
        company=company,
        channel_type="whatsapp",
        connector_id="test-connector",
        state=ThreadState.WAITING_MANAGER,
    )

    # Filter by channel_type
    response = await api_client.get(
        f"/api/v1/companies/{company.id}/threads",
        params={
            "channel_type": "telegram",
            "limit": 10,
            "offset": 0,
        },
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert any(t["thread_id"] == "thread_public_filter_1" for t in data["items"])
    assert not any(t["thread_id"] == "thread_public_filter_2" for t in data["items"])


@pytest.mark.asyncio
async def test_public_get_thread(api_client: httpx.AsyncClient, authenticated_user_with_token, company_factory):
    """Test getting thread detail via public API."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]
    customer = await Customer.create(user_id="public_get_user", company=company)
    thread = await Thread.create(
        thread_id="thread_public_get",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )
    await ChatMessage.create(
        message_id="msg_public_get_1",
        thread=thread,
        role=ChatMessageRole.USER,
        content="User message",
    )
    await ChatMessage.create(
        message_id="msg_public_get_2",
        thread=thread,
        role=ChatMessageRole.ASSISTANT,
        content="Assistant reply",
    )

    response = await api_client.get(
        f"/api/v1/companies/{company.id}/threads/thread_public_get",
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["thread_id"] == "thread_public_get"
    assert len(data["messages"]) == 2
    assert len(data["participants"]) >= 1


@pytest.mark.asyncio
async def test_public_get_thread_not_found(api_client: httpx.AsyncClient, authenticated_user_with_token):
    """Test getting non-existent thread via public API."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]
    response = await api_client.get(
        f"/api/v1/companies/{company.id}/threads/nonexistent",
        headers=auth_data["headers"],
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_public_create_message(api_client: httpx.AsyncClient, authenticated_user_with_token, company_factory):
    """Test creating message via public API."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]
    customer = await Customer.create(user_id="public_msg_user", company=company)
    _ = await Thread.create(
        thread_id="thread_public_msg",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )

    response = await api_client.post(
        f"/api/v1/companies/{company.id}/threads/thread_public_msg/messages",
        json={
            "role": "manager",
            "content": "Manager message",
            "metadata": {"source": "ui"},
        },
        headers=auth_data["headers"],
    )

    assert response.status_code == 201
    data = response.json()
    assert data["role"] == "manager"
    assert data["content"] == "Manager message"
    assert data["thread_id"] == "thread_public_msg"
    assert isinstance(data["message_id"], str)


@pytest.mark.asyncio
async def test_public_list_thread_messages(
    api_client: httpx.AsyncClient, authenticated_user_with_token, company_factory
):
    """Test listing thread messages via public API."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]
    customer = await Customer.create(user_id="public_list_msg_user", company=company)
    thread = await Thread.create(
        thread_id="thread_public_list_msg",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )

    # Create messages
    for i in range(5):
        await ChatMessage.create(
            message_id=f"msg_public_list_{i}",
            thread=thread,
            role=ChatMessageRole.USER,
            content=f"Message {i}",
        )

    response = await api_client.get(
        f"/api/v1/companies/{company.id}/threads/thread_public_list_msg/messages",
        params={"limit": 10, "offset": 0},
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 5


@pytest.mark.asyncio
async def test_public_control_thread_stop_assistant(
    api_client: httpx.AsyncClient, authenticated_user_with_token, company_factory
):
    """Test stopping assistant via public API."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]
    customer = await Customer.create(user_id="public_control_user", company=company)
    thread = await Thread.create(
        thread_id="thread_public_control",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
    )

    response = await api_client.post(
        f"/api/v1/companies/{company.id}/threads/thread_public_control/control/stop_assistant",
        json={"issued_by": "manager_1", "metadata": {}},
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "stop_assistant"
    assert data["assistant_mode"] == "inactive"

    # Verify state
    updated = await Thread.get(id=thread.id)
    assert updated.assistant_mode == AssistantMode.INACTIVE


@pytest.mark.asyncio
async def test_public_control_thread_resume_assistant(
    api_client: httpx.AsyncClient, authenticated_user_with_token, company_factory
):
    """Test resuming assistant via public API."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]
    customer = await Customer.create(user_id="public_resume_user", company=company)
    thread = await Thread.create(
        thread_id="thread_public_resume",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
        assistant_mode=AssistantMode.INACTIVE,
    )

    response = await api_client.post(
        f"/api/v1/companies/{company.id}/threads/thread_public_resume/control/resume_assistant",
        json={"issued_by": "manager_1", "metadata": {}},
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "resume_assistant"
    assert data["assistant_mode"] == "active"

    # Verify state
    updated = await Thread.get(id=thread.id)
    assert updated.assistant_mode == AssistantMode.ACTIVE
