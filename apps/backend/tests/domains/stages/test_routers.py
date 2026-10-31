"""Tests for Stages API endpoints."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_list_stages_empty(api_client, authenticated_user_with_company, clear_stages):
    """Test GET /companies/{company_id}/stages returns empty list."""
    auth_data = authenticated_user_with_company
    company_id = auth_data["company"].id

    # Clear default stages
    await clear_stages(company_id)

    response = await api_client.get(
        f"/api/v1/companies/{company_id}/stages",
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data == []


@pytest.mark.asyncio
async def test_list_stages_with_data(api_client, company_without_stages, stage_templates, test_superuser, settings):
    """Test GET /companies/{company_id}/stages returns sorted stages."""
    from src.backend.modules.auth.service import AuthService
    from src.backend.modules.users.models import CompanyUser, UserRole

    # Create company user for test_superuser
    await CompanyUser.get_or_create(
        user_id=test_superuser.id,
        company_id=company_without_stages.id,
        defaults={"role": UserRole.OWNER},
    )

    # Get auth token
    auth_service = AuthService(settings)
    token = auth_service.create_access_token(user_id=test_superuser.id, is_superuser=test_superuser.is_superuser)

    response = await api_client.get(
        f"/api/v1/companies/{company_without_stages.id}/stages",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5

    # Check sorted by position
    positions = [stage["position"] for stage in data]
    assert positions == [0, 1, 2, 3, 4]

    # Check names
    names = [stage["name"] for stage in data]
    assert "Новый" in names
    assert "Квалификация" in names


@pytest.mark.asyncio
async def test_create_stage_success(api_client, authenticated_user_with_company, clear_stages):
    """Test POST /companies/{company_id}/stages creates stage."""
    auth_data = authenticated_user_with_company
    company_id = auth_data["company"].id

    # Clear default stages
    await clear_stages(company_id)

    payload = {
        "name": "New Stage",
        "color": "#ff0000",
        "transition_condition": {"$any": True},
    }

    response = await api_client.post(
        f"/api/v1/companies/{company_id}/stages",
        json=payload,
        headers=auth_data["headers"],
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "New Stage"
    assert data["color"] == "#ff0000"
    assert data["position"] == 0  # First stage


@pytest.mark.asyncio
async def test_create_stage_assigns_next_position(api_client, authenticated_user_with_company, clear_stages):
    """Test POST assigns position = max + 1."""
    from src.backend.modules.stages.models import StageTemplate

    auth_data = authenticated_user_with_company
    company_id = auth_data["company"].id

    # Clear default stages
    await clear_stages(company_id)

    # Create one stage at position 0
    _ = await StageTemplate.create(
        company_id=company_id,
        name="Test Stage",
        color="#3b82f6",
        position=0,
        transition_condition={"$any": True},
    )

    payload = {
        "name": "Second Stage",
        "color": "#00ff00",
    }

    response = await api_client.post(
        f"/api/v1/companies/{company_id}/stages",
        json=payload,
        headers=auth_data["headers"],
    )

    assert response.status_code == 201
    data = response.json()
    assert data["position"] == 1  # After existing stage at position 0


@pytest.mark.asyncio
async def test_create_stage_with_invalid_condition(api_client, authenticated_user_with_company):
    """Test POST with invalid transition_condition returns 400."""
    auth_data = authenticated_user_with_company
    company_id = auth_data["company"].id

    payload = {
        "name": "Invalid Stage",
        "color": "#ff0000",
        "transition_condition": {"$invalid_operator": True},
    }

    response = await api_client.post(
        f"/api/v1/companies/{company_id}/stages",
        json=payload,
        headers=auth_data["headers"],
    )

    assert response.status_code == 422  # FastAPI validation error
    assert "condition" in response.text.lower() or "invalid" in response.text.lower()


@pytest.mark.asyncio
async def test_create_final_stage_success(api_client, authenticated_user_with_company):
    """Test POST with is_final=True succeeds (no result field required)."""
    auth_data = authenticated_user_with_company
    company_id = auth_data["company"].id

    payload = {
        "name": "Final Stage",
        "color": "#ff0000",
        "is_final": True,
    }

    response = await api_client.post(
        f"/api/v1/companies/{company_id}/stages",
        json=payload,
        headers=auth_data["headers"],
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Final Stage"
    assert data["is_final"] is True


@pytest.mark.asyncio
async def test_update_stage_success(api_client, authenticated_user_with_company, clear_stages):
    """Test PATCH /companies/{company_id}/stages/{id} updates stage."""
    from src.backend.modules.stages.models import StageTemplate

    auth_data = authenticated_user_with_company
    company_id = auth_data["company"].id

    # Clear default stages and create test stage
    await clear_stages(company_id)
    stage_template = await StageTemplate.create(
        company_id=company_id,
        name="Test Stage",
        color="#3b82f6",
        position=0,
        transition_condition={"$any": True},
    )

    payload = {
        "name": "Updated Stage",
        "color": "#0000ff",
    }

    response = await api_client.patch(
        f"/api/v1/companies/{company_id}/stages/{stage_template.id}",
        json=payload,
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Stage"
    assert data["color"] == "#0000ff"
    assert data["position"] == stage_template.position  # Position unchanged


@pytest.mark.asyncio
async def test_update_stage_with_invalid_condition(api_client, authenticated_user_with_company, stage_template):
    """Test PATCH with invalid transition_condition returns 400."""
    auth_data = authenticated_user_with_company
    company_id = auth_data["company"].id

    payload = {
        "transition_condition": {"$bad_operator": "value"},
    }

    response = await api_client.patch(
        f"/api/v1/companies/{company_id}/stages/{stage_template.id}",
        json=payload,
        headers=auth_data["headers"],
    )

    assert response.status_code == 422  # FastAPI validation error


@pytest.mark.asyncio
async def test_delete_stage_success(api_client, authenticated_user_with_company, clear_stages):
    """Test DELETE /companies/{company_id}/stages/{id} deletes stage."""
    from src.backend.modules.stages.models import StageTemplate

    auth_data = authenticated_user_with_company
    company_id = auth_data["company"].id

    # Clear default stages and create test stage
    await clear_stages(company_id)
    stage_template = await StageTemplate.create(
        company_id=company_id,
        name="Test Stage",
        color="#3b82f6",
        position=0,
        transition_condition={"$any": True},
    )

    response = await api_client.delete(
        f"/api/v1/companies/{company_id}/stages/{stage_template.id}",
        headers=auth_data["headers"],
    )

    assert response.status_code == 204

    # Verify deleted
    get_response = await api_client.get(
        f"/api/v1/companies/{company_id}/stages",
        headers=auth_data["headers"],
    )
    stages = get_response.json()
    stage_ids = [s["id"] for s in stages]
    assert stage_template.id not in stage_ids


@pytest.mark.asyncio
async def test_delete_stage_sets_orders_to_null(api_client, authenticated_user_with_company, clear_stages):
    """Test DELETE sets Order.stage to NULL (not cascade delete)."""
    from src.backend.modules.chat.models import Customer
    from src.backend.modules.orders.repository import OrdersRepository
    from src.backend.modules.stages.models import StageTemplate

    auth_data = authenticated_user_with_company
    company_id = auth_data["company"].id

    # Clear default stages and create test stage
    await clear_stages(company_id)
    stage_template = await StageTemplate.create(
        company_id=company_id,
        name="Test Stage",
        color="#3b82f6",
        position=0,
        transition_condition={"$any": True},
    )

    # Create customer and order with this stage
    customer = await Customer.create(
        user_id="test-customer-stage-delete",
        company_id=company_id,
        name="Test Customer",
        meta={},
    )

    orders_repo = OrdersRepository()
    order_number = await orders_repo.get_next_order_number(company_id)
    order = await orders_repo.create_order(
        company_id=company_id,
        customer_id=customer.id,
        order_number=order_number,
    )

    # Assign stage
    await orders_repo.update_stage(order, stage_template, author_id=None)

    # Delete stage
    response = await api_client.delete(
        f"/api/v1/companies/{company_id}/stages/{stage_template.id}",
        headers=auth_data["headers"],
    )

    assert response.status_code == 204

    # Verify order.stage is NULL
    await order.refresh_from_db()
    assert order.stage_id is None


@pytest.mark.asyncio
async def test_delete_system_stage_forbidden(api_client, authenticated_user_with_company, clear_stages):
    """Test DELETE /companies/{company_id}/stages/{id} rejects system stage deletion."""
    from src.backend.modules.stages.models import StageTemplate

    auth_data = authenticated_user_with_company
    company_id = auth_data["company"].id

    # Clear stages and create system stage
    await clear_stages(company_id)
    system_stage = await StageTemplate.create(
        company_id=company_id,
        name="System Stage",
        color="#64748b",
        position=0,
        is_system=True,
        transition_condition={"$any": True},
    )

    # Attempt to delete system stage
    response = await api_client.delete(
        f"/api/v1/companies/{company_id}/stages/{system_stage.id}",
        headers=auth_data["headers"],
    )

    assert response.status_code == 400
    assert "Cannot delete system stage" in response.json()["detail"]

    # Verify stage still exists
    get_response = await api_client.get(
        f"/api/v1/companies/{company_id}/stages",
        headers=auth_data["headers"],
    )
    stages = get_response.json()
    stage_ids = [s["id"] for s in stages]
    assert system_stage.id in stage_ids


@pytest.mark.asyncio
async def test_reorder_stages(api_client, authenticated_user_with_company, clear_stages):
    """Test PUT /companies/{company_id}/stages/reorder changes positions."""
    from src.backend.modules.stages.models import StageTemplate

    auth_data = authenticated_user_with_company
    company_id = auth_data["company"].id

    # Clear default stages and create test stages
    await clear_stages(company_id)
    stage_templates = [
        await StageTemplate.create(company_id=company_id, name="Stage 1", position=0, color="#000001"),
        await StageTemplate.create(company_id=company_id, name="Stage 2", position=1, color="#000002"),
        await StageTemplate.create(company_id=company_id, name="Stage 3", position=2, color="#000003"),
    ]

    # Reverse order
    stage_ids = [s.id for s in reversed(stage_templates)]
    payload = {"stage_ids": stage_ids}

    response = await api_client.put(
        f"/api/v1/companies/{company_id}/stages/reorder",
        json=payload,
        headers=auth_data["headers"],
    )

    assert response.status_code == 200

    # Verify new order
    get_response = await api_client.get(
        f"/api/v1/companies/{company_id}/stages",
        headers=auth_data["headers"],
    )
    stages = get_response.json()

    assert stages[0]["id"] == stage_templates[2].id
    assert stages[0]["position"] == 0

    assert stages[2]["id"] == stage_templates[0].id
    assert stages[2]["position"] == 2


@pytest.mark.asyncio
async def test_reorder_stages_with_missing_id(api_client, authenticated_user_with_company, clear_stages):
    """Test PUT /reorder with non-existent stage ID returns 400."""
    from src.backend.modules.stages.models import StageTemplate

    auth_data = authenticated_user_with_company
    company_id = auth_data["company"].id

    # Clear default stages and create test stage
    await clear_stages(company_id)
    stage = await StageTemplate.create(company_id=company_id, name="Stage 1", position=0, color="#000001")

    payload = {"stage_ids": [99999, stage.id]}

    response = await api_client.put(
        f"/api/v1/companies/{company_id}/stages/reorder",
        json=payload,
        headers=auth_data["headers"],
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_stage_by_id(api_client, authenticated_user_with_company, clear_stages):
    """Test GET /companies/{company_id}/stages/{id} returns single stage."""
    from src.backend.modules.stages.models import StageTemplate

    auth_data = authenticated_user_with_company
    company_id = auth_data["company"].id

    # Clear default stages and create test stage
    await clear_stages(company_id)
    stage_template = await StageTemplate.create(
        company_id=company_id,
        name="Test Stage",
        color="#3b82f6",
        position=0,
        transition_condition={"$any": True},
    )

    response = await api_client.get(
        f"/api/v1/companies/{company_id}/stages/{stage_template.id}",
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == stage_template.id
    assert data["name"] == stage_template.name
