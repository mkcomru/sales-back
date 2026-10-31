"""Tests for GET /customers/{id} endpoint."""

import httpx
import pytest

from src.backend.modules.chat.models import Customer


@pytest.mark.asyncio
async def test_get_customer_detail_success(
    api_client: httpx.AsyncClient, authenticated_user_with_token, company_factory
):
    """Test getting full customer details."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]

    customer = await Customer.create(
        user_id="test_detail_user",
        company=company,
        name="John Doe",
        customer_fields={"goal": "Lose weight", "age": "30", "experience": "Beginner"},
        rejected=False,
        meta={
            "username": "@johndoe",
            "phone": "+1234567890",
            "email": "john@example.com",
            "avatar_url": "https://example.com/avatar.jpg",
            "telegram_id": "123456789",
        },
    )

    response = await api_client.get(
        f"/api/v1/companies/{company.id}/customers/{customer.id}",
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()

    assert data["customer_id"] == customer.id
    assert data["user_id"] == "test_detail_user"
    assert data["name"] == "John Doe"
    assert data["username"] == "@johndoe"
    assert data["phone"] == "+1234567890"
    assert data["email"] == "john@example.com"
    assert data["avatar_url"] == "https://example.com/avatar.jpg"
    assert data["customer_fields"]["goal"] == "Lose weight"
    assert data["customer_fields"]["age"] == "30"
    assert data["customer_fields"]["experience"] == "Beginner"
    assert data["rejected"] is False
    assert data["rejection_reason"] is None
    assert data["meta"]["telegram_id"] == "123456789"
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_get_customer_detail_minimal(
    api_client: httpx.AsyncClient, authenticated_user_with_token, company_factory
):
    """Test getting customer details with minimal data."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]

    customer = await Customer.create(
        user_id="minimal_user",
        company=company,
    )

    response = await api_client.get(
        f"/api/v1/companies/{company.id}/customers/{customer.id}",
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()

    assert data["customer_id"] == customer.id
    assert data["user_id"] == "minimal_user"
    assert data["name"] is None
    assert data["username"] is None
    assert data["phone"] is None
    assert data["email"] is None
    assert data["avatar_url"] is None
    assert data["customer_fields"] == {}
    assert data["rejected"] is False
    assert data["meta"] == {}


@pytest.mark.asyncio
async def test_get_customer_detail_rejected(
    api_client: httpx.AsyncClient, authenticated_user_with_token, company_factory
):
    """Test getting details of rejected customer."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]

    customer = await Customer.create(
        user_id="rejected_user",
        company=company,
        name="Rejected User",
        rejected=True,
        rejection_reason="Not interested",
    )

    response = await api_client.get(
        f"/api/v1/companies/{company.id}/customers/{customer.id}",
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()

    assert data["customer_id"] == customer.id
    assert data["rejected"] is True
    assert data["rejection_reason"] == "Not interested"


@pytest.mark.asyncio
async def test_get_customer_detail_not_found(api_client: httpx.AsyncClient, authenticated_user_with_token):
    """Test getting non-existent customer."""
    auth_data = authenticated_user_with_token

    company = authenticated_user_with_token["company"]
    response = await api_client.get(
        f"/api/v1/companies/{company.id}/customers/99999",
        headers=auth_data["headers"],
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_customer_detail_with_quiz_answers(
    api_client: httpx.AsyncClient, authenticated_user_with_token, company_factory
):
    """Test customer with complex quiz answers."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]

    quiz_data = {
        "goal": "Набрать массу",
        "current_weight": "70",
        "target_weight": "80",
        "height": "180",
        "age": "25",
        "experience": "Intermediate",
        "dietary_restrictions": ["Lactose intolerant"],
        "preferred_workout_time": "Morning",
        "injuries": None,
    }

    customer = await Customer.create(
        user_id="quiz_user",
        company=company,
        name="Quiz User",
        customer_fields=quiz_data,
    )

    response = await api_client.get(
        f"/api/v1/companies/{company.id}/customers/{customer.id}",
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()

    assert data["customer_fields"] == quiz_data
