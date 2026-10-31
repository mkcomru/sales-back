"""Tests for Orders API endpoints."""

from __future__ import annotations

import pytest

from src.backend.modules.orders.models import OrderLog, OrderLogType, OrderResult


@pytest.mark.asyncio
async def test_create_order_endpoint(
    api_client,
    authenticated_user_with_company,
):
    """Test POST /companies/{company_id}/orders creates order and log."""
    from src.backend.modules.chat.models import Customer

    auth_data = authenticated_user_with_company

    customer = await Customer.create(
        user_id="test-customer-api",
        company_id=auth_data["company"].id,
        name="API Test Customer",
        meta={},
    )

    response = await api_client.post(
        f"/api/v1/companies/{auth_data['company'].id}/orders",
        json={
            "customer_id": customer.id,
            "assignee_id": auth_data["company_user"].id,
        },
        headers=auth_data["headers"],
    )

    assert response.status_code == 201
    data = response.json()
    assert data["order_number"] == 1
    assert data["customer"]["id"] == customer.id

    logs = await OrderLog.filter(order_id=data["id"], type=OrderLogType.ORDER_CREATED).all()
    assert len(logs) == 1
    assert logs[0].author_id == auth_data["company_user"].id


@pytest.mark.asyncio
async def test_update_order_stage_endpoint(
    api_client,
    order_for_authenticated_user,
    clear_stages,
):
    """Test PATCH /companies/{company_id}/orders/{order_id} updates stage and creates log."""
    from src.backend.modules.stages.models import StageTemplate

    order, _, auth_data = order_for_authenticated_user

    # Clear default stages
    await clear_stages(auth_data["company"].id)

    # Create initial stage
    initial_stage = await StageTemplate.create(
        company_id=auth_data["company"].id,
        name="Initial Stage",
        position=0,
        transition_condition={"$any": True},
    )

    # Create target stage
    target_stage = await StageTemplate.create(
        company_id=auth_data["company"].id,
        name="Test Stage",
        position=1,
    )

    # Set order to initial stage first
    from src.backend.modules.orders.repository import OrdersRepository

    orders_repo = OrdersRepository()
    order, _ = await orders_repo.update_stage(order, initial_stage, author_id=None)

    response = await api_client.patch(
        f"/api/v1/companies/{auth_data['company'].id}/orders/{order.id}",
        json={"stage_id": target_stage.id},
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["stage"] is not None, f"Stage is None in response: {data}"
    assert data["stage"]["id"] == target_stage.id

    logs = await OrderLog.filter(order_id=order.id, type=OrderLogType.STAGE_CHANGE).all()
    assert len(logs) >= 1
    last_log = logs[-1]
    assert last_log.data["to_stage_id"] == target_stage.id
    assert last_log.author_id == auth_data["company_user"].id


@pytest.mark.asyncio
async def test_update_order_fields_endpoint(
    api_client,
    order_for_authenticated_user,
):
    """Test PATCH /companies/{company_id}/orders/{order_id} updates fields and creates logs."""
    order, _, auth_data = order_for_authenticated_user

    response = await api_client.patch(
        f"/api/v1/companies/{auth_data['company'].id}/orders/{order.id}",
        json={
            "order_fields": {
                "budget": 200000,
                "destination": "Egypt",
            }
        },
        headers=auth_data["headers"],
    )

    assert response.status_code == 200

    logs = await OrderLog.filter(order_id=order.id, type=OrderLogType.FIELD_CHANGE).all()
    assert len(logs) == 2


@pytest.mark.asyncio
async def test_update_order_assignee_endpoint(
    api_client,
    order_for_authenticated_user,
):
    """Test PUT /companies/{company_id}/orders/{order_id}/assignee updates assignee and creates log."""
    from src.backend.modules.users.models import CompanyUser, User, UserRole

    order, _, auth_data = order_for_authenticated_user

    manager_user_obj = await User.create(
        first_name="Manager",
        last_name="Test",
        email="manager-test@test.com",
        hashed_password="hashed",  # pragma: allowlist secret
        is_active=True,
    )
    manager = await CompanyUser.create(
        user_id=manager_user_obj.id,
        company_id=auth_data["company"].id,
        role=UserRole.ADMIN,
    )

    response = await api_client.put(
        f"/api/v1/companies/{auth_data['company'].id}/orders/{order.id}/assignee",
        json={"assignee_id": manager.id},
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["assignee"]["id"] == manager.id

    logs = await OrderLog.filter(order_id=order.id, type=OrderLogType.ASSIGNEE_CHANGE).all()
    assert len(logs) == 1
    assert logs[0].data["to_user_id"] == manager.id


@pytest.mark.asyncio
async def test_close_order_endpoint(
    api_client,
    order_for_authenticated_user,
):
    """Test POST /companies/{company_id}/orders/{order_id}/close closes order and creates log."""
    order, _, auth_data = order_for_authenticated_user

    response = await api_client.post(
        f"/api/v1/companies/{auth_data['company'].id}/orders/{order.id}/close",
        json={"result": OrderResult.WON.value},
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["result"] == OrderResult.WON.value
    assert data["closed_at"] is not None

    logs = await OrderLog.filter(order_id=order.id, type=OrderLogType.STAGE_CHANGE).all()
    assert len(logs) >= 1
    last_log = logs[-1]
    assert last_log.data["result"] == OrderResult.WON.value


@pytest.mark.asyncio
async def test_get_order_logs_endpoint(
    api_client,
    order_for_authenticated_user,
    orders_repo,
    clear_stages,
):
    """Test GET /companies/{company_id}/orders/{order_id}/logs returns logs."""
    from src.backend.modules.stages.models import StageTemplate

    order, _, auth_data = order_for_authenticated_user

    # Clear default stages
    await clear_stages(auth_data["company"].id)

    stage = await StageTemplate.create(
        company_id=auth_data["company"].id,
        name="Test Stage",
        position=0,
    )

    await orders_repo.update_stage(order, stage, author_id=auth_data["company_user"].id)
    await orders_repo.add_comment(order, "Test comment", author_id=auth_data["company_user"].id)

    response = await api_client.get(
        f"/api/v1/companies/{auth_data['company'].id}/orders/{order.id}/logs",
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2

    assert data[0]["type"] == OrderLogType.COMMENT.value
    assert data[0]["data"]["text"] == "Test comment"
    assert data[0]["author"]["id"] == auth_data["company_user"].id


@pytest.mark.asyncio
async def test_add_comment_endpoint(
    api_client,
    order_for_authenticated_user,
):
    """Test POST /companies/{company_id}/orders/{order_id}/logs adds comment."""
    order, _, auth_data = order_for_authenticated_user

    comment_text = "Клиент хочет рассрочку"

    response = await api_client.post(
        f"/api/v1/companies/{auth_data['company'].id}/orders/{order.id}/logs",
        json={"text": comment_text},
        headers=auth_data["headers"],
    )

    assert response.status_code == 201
    data = response.json()
    assert data["type"] == OrderLogType.COMMENT.value
    assert data["data"]["text"] == comment_text
    assert data["author"]["id"] == auth_data["company_user"].id

    logs = await OrderLog.filter(order_id=order.id, type=OrderLogType.COMMENT).all()
    assert len(logs) == 1


@pytest.mark.asyncio
async def test_get_logs_requires_authentication(
    api_client,
    order_with_customer,
):
    """Test GET /logs endpoint requires authentication."""
    order, _, company = order_with_customer

    response = await api_client.get(
        f"/api/v1/companies/{company.id}/orders/{order.id}/logs",
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_add_comment_requires_authentication(
    api_client,
    order_with_customer,
):
    """Test POST /logs endpoint requires authentication."""
    order, _, company = order_with_customer

    response = await api_client.post(
        f"/api/v1/companies/{company.id}/orders/{order.id}/logs",
        json={"text": "Test"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_add_comment_validates_text_length(
    api_client,
    order_for_authenticated_user,
):
    """Test POST /logs validates text length."""
    order, _, auth_data = order_for_authenticated_user

    response = await api_client.post(
        f"/api/v1/companies/{auth_data['company'].id}/orders/{order.id}/logs",
        json={"text": ""},
        headers=auth_data["headers"],
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_internal_update_stage_creates_system_log(
    api_client,
    service_headers,
    order_with_customer,
    clear_stages,
):
    """Test internal stage update creates log without author (system)."""
    from src.backend.modules.stages.models import StageTemplate

    order, _, company = order_with_customer

    # Clear default stages
    await clear_stages(company.id)

    stage = await StageTemplate.create(
        company_id=company.id,
        name="System Stage",
        position=0,
    )

    response = await api_client.patch(
        f"/api/v1/internal/orders/{order.id}/stage",
        json={"stage": stage.id},
        headers=service_headers,
    )

    assert response.status_code == 200

    logs = await OrderLog.filter(order_id=order.id, type=OrderLogType.STAGE_CHANGE).all()
    assert len(logs) == 1
    assert logs[0].author_id is None
    assert logs[0].data["trigger"] == "auto"


@pytest.mark.asyncio
async def test_internal_update_fields_creates_system_log(
    api_client,
    service_headers,
    order_with_customer,
):
    """Test unified fields update creates order FIELD_CHANGE log without author (system)."""
    from src.backend.modules.fields.models import AnswerType, Field, FieldLevel

    order, customer, company = order_with_customer

    await Field.create(
        company=company,
        name="budget",
        question="Budget?",
        answer_type=AnswerType.NUMBER,
        level=FieldLevel.ORDER,
    )

    response = await api_client.patch(
        f"/api/v1/internal/chat/customers/{customer.user_id}/fields",
        json={
            "company_id": company.id,
            "order_id": order.id,
            "updates": {"budget": 50000},
        },
        headers=service_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert "budget" in data.get("updated_order", [])

    logs = await OrderLog.filter(order_id=order.id, type=OrderLogType.FIELD_CHANGE).all()
    assert len(logs) == 1
    assert logs[0].author_id is None
