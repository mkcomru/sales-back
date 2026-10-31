"""Tests for PATCH /customers/{id}/quiz-answers endpoint."""

import httpx
import pytest

from src.backend.modules.chat.models import Customer


@pytest.mark.asyncio
async def test_update_customer_fields_success(
    api_client: httpx.AsyncClient, authenticated_user_with_token, company_factory
):
    """Test updating quiz answers."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]

    customer = await Customer.create(
        user_id="quiz_update_user",
        company=company,
        name="Test User",
        customer_fields={"goal": "Lose weight", "age": "30"},
    )

    response = await api_client.patch(
        f"/api/v1/companies/{company.id}/customers/{customer.id}/fields",
        json={"answers": {"goal": "Gain muscle", "experience": "Beginner"}},
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()

    assert data["customer_id"] == customer.id
    assert "goal" in data["updated_answers"]
    assert data["updated_answers"]["goal"] == "Gain muscle"
    assert "experience" in data["updated_answers"]
    assert data["updated_answers"]["experience"] == "Beginner"
    assert "updated_at" in data

    # Verify database update
    await customer.refresh_from_db()
    assert customer.customer_fields["goal"] == "Gain muscle"
    assert customer.customer_fields["age"] == "30"  # Unchanged
    assert customer.customer_fields["experience"] == "Beginner"


@pytest.mark.asyncio
async def test_update_customer_fields_add_new_fields(
    api_client: httpx.AsyncClient, authenticated_user_with_token, company_factory
):
    """Test adding new quiz answer fields."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]

    customer = await Customer.create(
        user_id="quiz_add_user",
        company=company,
        customer_fields={"goal": "Lose weight"},
    )

    response = await api_client.patch(
        f"/api/v1/companies/{company.id}/customers/{customer.id}/fields",
        json={
            "answers": {
                "current_weight": "90",
                "target_weight": "80",
                "height": "180",
            }
        },
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()

    assert len(data["updated_answers"]) == 3
    assert data["updated_answers"]["current_weight"] == "90"
    assert data["updated_answers"]["target_weight"] == "80"
    assert data["updated_answers"]["height"] == "180"

    await customer.refresh_from_db()
    assert customer.customer_fields["goal"] == "Lose weight"  # Unchanged
    assert customer.customer_fields["current_weight"] == "90"
    assert customer.customer_fields["target_weight"] == "80"
    assert customer.customer_fields["height"] == "180"


@pytest.mark.asyncio
async def test_update_customer_fields_empty_quiz(
    api_client: httpx.AsyncClient, authenticated_user_with_token, company_factory
):
    """Test updating quiz answers when customer has no existing answers."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]

    customer = await Customer.create(
        user_id="quiz_empty_user",
        company=company,
    )

    response = await api_client.patch(
        f"/api/v1/companies/{company.id}/customers/{customer.id}/fields",
        json={"answers": {"goal": "Maintain weight", "age": "25"}},
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()

    assert data["updated_answers"]["goal"] == "Maintain weight"
    assert data["updated_answers"]["age"] == "25"

    await customer.refresh_from_db()
    assert customer.customer_fields["goal"] == "Maintain weight"
    assert customer.customer_fields["age"] == "25"


@pytest.mark.asyncio
async def test_update_customer_fields_no_changes(
    api_client: httpx.AsyncClient, authenticated_user_with_token, company_factory
):
    """Test updating quiz answers with same values (no changes)."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]

    customer = await Customer.create(
        user_id="quiz_no_change_user",
        company=company,
        customer_fields={"goal": "Lose weight", "age": "30"},
    )

    response = await api_client.patch(
        f"/api/v1/companies/{company.id}/customers/{customer.id}/fields",
        json={"answers": {"goal": "Lose weight"}},
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()

    # No changes should be reported since value is the same
    assert data["updated_answers"] == {}


@pytest.mark.asyncio
async def test_update_customer_fields_complex_types(
    api_client: httpx.AsyncClient, authenticated_user_with_token, company_factory
):
    """Test updating quiz answers with complex data types."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]

    customer = await Customer.create(
        user_id="quiz_complex_user",
        company=company,
        customer_fields={"goal": "Lose weight"},
    )

    response = await api_client.patch(
        f"/api/v1/companies/{company.id}/customers/{customer.id}/fields",
        json={
            "answers": {
                "dietary_restrictions": ["Lactose intolerant", "Gluten free"],
                "workout_preferences": {
                    "time": "Morning",
                    "duration": 60,
                    "types": ["Cardio", "Strength"],
                },
            }
        },
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()

    assert data["updated_answers"]["dietary_restrictions"] == [
        "Lactose intolerant",
        "Gluten free",
    ]
    assert data["updated_answers"]["workout_preferences"]["time"] == "Morning"

    await customer.refresh_from_db()
    assert customer.customer_fields["dietary_restrictions"] == [
        "Lactose intolerant",
        "Gluten free",
    ]
    assert customer.customer_fields["workout_preferences"]["duration"] == 60


@pytest.mark.asyncio
async def test_update_customer_fields_customer_not_found(api_client: httpx.AsyncClient, authenticated_user_with_token):
    """Test updating quiz answers for non-existent customer."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]

    response = await api_client.patch(
        f"/api/v1/companies/{company.id}/customers/99999/quiz-answers",
        json={"answers": {"goal": "Test"}},
        headers=auth_data["headers"],
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_customer_fields_no_payload(
    api_client: httpx.AsyncClient, authenticated_user_with_token, company_factory
):
    """Test updating quiz answers without payload."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]

    customer = await Customer.create(
        user_id="quiz_no_payload_user",
        company=company,
    )

    response = await api_client.patch(
        f"/api/v1/companies/{customer.id}/customers/{customer.id}/fields",
        json={},
        headers=auth_data["headers"],
    )

    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_update_customer_fields_multiple_fields(
    api_client: httpx.AsyncClient, authenticated_user_with_token, company_factory
):
    """Test updating multiple quiz answer fields at once."""
    auth_data = authenticated_user_with_token
    company = auth_data["company"]

    customer = await Customer.create(
        user_id="quiz_multi_user",
        company=company,
        customer_fields={
            "goal": "Lose weight",
            "current_weight": "100",
            "age": "35",
        },
    )

    response = await api_client.patch(
        f"/api/v1/companies/{company.id}/customers/{customer.id}/fields",
        json={
            "answers": {
                "goal": "Gain muscle",
                "current_weight": "95",
                "target_weight": "100",
                "experience": "Intermediate",
                "preferred_workout_time": "Evening",
            }
        },
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()

    # Should report all changed/added fields
    assert len(data["updated_answers"]) == 5
    assert data["updated_answers"]["goal"] == "Gain muscle"
    assert data["updated_answers"]["current_weight"] == "95"
    assert data["updated_answers"]["target_weight"] == "100"
    assert data["updated_answers"]["experience"] == "Intermediate"

    await customer.refresh_from_db()
    assert customer.customer_fields["age"] == "35"  # Unchanged
    assert customer.customer_fields["goal"] == "Gain muscle"
    assert customer.customer_fields["target_weight"] == "100"
