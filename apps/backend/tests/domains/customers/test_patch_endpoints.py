"""Tests for PATCH endpoints (customers, threads)."""

import httpx
import pytest

from src.backend.modules.chat.models import (
    ChatMessage,
    ChatMessageRole,
    Customer,
    Thread,
    ThreadState,
)


@pytest.mark.asyncio
async def test_patch_customer_name_and_phone(
    api_client: httpx.AsyncClient, authenticated_user_with_token, company_factory
):
    """Test updating customer name and phone via PATCH /customers/{id}."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]

    customer = await Customer.create(
        user_id="patch_customer_user",
        company=company,
        name="Old Name",
        meta={"phone": "+1234567890"},
    )

    response = await api_client.patch(
        f"/api/v1/companies/{company.id}/customers/{customer.id}",
        json={"name": "New Name", "phone": "+0987654321"},
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["customer_id"] == customer.id
    assert data["name"] == "New Name"
    assert data["phone"] == "+0987654321"

    await customer.refresh_from_db()
    assert customer.name == "New Name"
    assert customer.meta["phone"] == "+0987654321"


@pytest.mark.asyncio
async def test_patch_customer_partial_update(
    api_client: httpx.AsyncClient, authenticated_user_with_token, company_factory
):
    """Test partial update (only name) via PATCH /customers/{id}."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]

    customer = await Customer.create(
        user_id="patch_partial_user",
        company=company,
        name="Initial Name",
        meta={"phone": "+1111111111"},
    )

    response = await api_client.patch(
        f"/api/v1/companies/{company.id}/customers/{customer.id}",
        json={"name": "Updated Name"},
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["phone"] == "+1111111111"


@pytest.mark.asyncio
async def test_patch_thread_custom_fields(
    api_client: httpx.AsyncClient, authenticated_user_with_token, company_factory
):
    """Test updating thread custom fields via PATCH /threads/{id}/fields."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]

    customer = await Customer.create(user_id="patch_fields_user", company=company)
    thread = await Thread.create(
        thread_id="thread_patch_fields",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
        state=ThreadState.ACTIVE,
        metadata={"custom_fields": {"goal": "Похудеть", "age": "25"}},
    )

    response = await api_client.patch(
        f"/api/v1/companies/{company.id}/threads/{thread.thread_id}/fields",
        json={"fields": {"goal": "Набрать массу", "experience": "Новичок"}},
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["thread_id"] == thread.thread_id
    assert "updated_fields" in data

    await thread.refresh_from_db()
    custom_fields = thread.metadata.get("custom_fields", {})
    assert custom_fields["goal"] == "Набрать массу"
    assert custom_fields["experience"] == "Новичок"
    assert custom_fields["age"] == "25"

    messages = await ChatMessage.filter(thread=thread, role=ChatMessageRole.SYSTEM).all()
    assert len(messages) == 1
    assert "Обновлены поля диалога" in messages[0].content


@pytest.mark.asyncio
async def test_patch_customer_not_found(api_client: httpx.AsyncClient, authenticated_user_with_token):
    """Test PATCH /customers/{id} with non-existent customer."""
    auth_data = authenticated_user_with_token

    company = authenticated_user_with_token["company"]
    response = await api_client.patch(
        f"/api/v1/companies/{company.id}/customers/99999",
        json={"name": "Test"},
        headers=auth_data["headers"],
    )

    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.skip(reason="Stage moved from Thread to Order (migration 32)")
async def test_patch_thread_stage_without_stage(
    api_client: httpx.AsyncClient, authenticated_user_with_token, company_factory
):
    """Test PATCH /threads/{id}/stage without stage parameter."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]

    customer = await Customer.create(user_id="patch_no_stage_user", company=company)
    thread = await Thread.create(
        thread_id="thread_patch_no_stage",
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test-connector",
        state=ThreadState.ACTIVE,
    )

    response = await api_client.patch(
        f"/api/v1/companies/{company.id}/threads/{thread.thread_id}/stage",
        json={},
        headers=auth_data["headers"],
    )

    assert response.status_code == 422
