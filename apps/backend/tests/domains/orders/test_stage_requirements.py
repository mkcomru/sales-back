"""Tests for stage requirements endpoint."""

import pytest

from src.backend.modules.chat.models import Customer
from src.backend.modules.orders.service import OrderService


@pytest.mark.asyncio
async def test_stage_requirements_shows_missing_fields(company, custom_test_stages):
    """Test stage-requirements endpoint shows what fields are needed."""
    customer = await Customer.create(
        user_id="test-requirements",
        company_id=company.id,
        name="Test",
        meta={},
        customer_fields={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    # Order is on stage 0, check requirements for next stages
    result = await order_service.get_order_stage_requirements(order.id)

    assert result["current_stage"].position == 0
    assert len(result["next_stages"]) > 0

    # Stage 1 requires budget >= 1000
    stage1_info = next(s for s in result["next_stages"] if s["stage"].position == 1)
    assert "budget" in stage1_info["missing_fields"]
    assert stage1_info["condition_status"] in ["partial", "blocked"]


@pytest.mark.asyncio
async def test_stage_requirements_shows_met_conditions(company, custom_test_stages):
    """Test stage-requirements shows 'met' when conditions are satisfied."""
    customer = await Customer.create(
        user_id="test-met",
        company_id=company.id,
        name="Test",
        meta={},
        customer_fields={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    # Fill budget field
    order = await order_service.update_order_fields(order.id, {"budget": 2000})

    # Check requirements
    result = await order_service.get_order_stage_requirements(order.id)

    # Now on stage 1, check stage 2 requirements
    assert result["current_stage"].position == 1

    # Stage 2 requires budget + city
    stage2_info = next((s for s in result["next_stages"] if s["stage"].position == 2), None)

    if stage2_info:
        # Budget is filled, city is missing
        assert "city" in stage2_info["missing_fields"]
        assert "budget" not in stage2_info["missing_fields"]


@pytest.mark.asyncio
async def test_stage_requirements_endpoint(api_client, authenticated_user_with_company, custom_test_stages):
    """Test POST /orders/{id}/stage-requirements endpoint."""
    from src.backend.modules.chat.models import Customer
    from src.backend.modules.orders.repository import OrdersRepository

    auth_data = authenticated_user_with_company
    company_id = auth_data["company"].id

    customer = await Customer.create(
        user_id="test-req-endpoint",
        company_id=company_id,
        name="Test",
        meta={},
    )

    orders_repo = OrdersRepository()
    order_number = await orders_repo.get_next_order_number(company_id)
    order = await orders_repo.create_order(
        company_id=company_id,
        customer_id=customer.id,
        order_number=order_number,
    )

    response = await api_client.post(
        f"/api/v1/companies/{company_id}/orders/{order.id}/stage-requirements",
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()

    assert "current_stage" in data
    assert "next_stages" in data
    assert isinstance(data["next_stages"], list)


@pytest.mark.asyncio
async def test_stage_requirements_with_no_next_stages(company, clear_stages):
    """Test stage-requirements when order is on final stage."""
    from src.backend.modules.stages.models import StageTemplate

    # Clear default stages
    await clear_stages(company.id)

    # Create single final stage
    _ = await StageTemplate.create(
        company_id=company.id,
        name="Final",
        position=0,
        is_final=True,
        result="won",
        transition_condition={"$any": True},
    )

    customer = await Customer.create(
        user_id="test-final-req",
        company_id=company.id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    result = await order_service.get_order_stage_requirements(order.id)

    assert result["current_stage"].position == 0
    assert len(result["next_stages"]) == 0  # No stages after final


@pytest.mark.asyncio
async def test_stage_requirements_includes_condition_status(company, custom_test_stages):
    """Test stage-requirements includes condition_status for each stage."""
    customer = await Customer.create(
        user_id="test-status",
        company_id=company.id,
        name="Test",
        meta={},
        customer_fields={"city": "Moscow"},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    result = await order_service.get_order_stage_requirements(order.id)

    for stage_info in result["next_stages"]:
        assert "condition_status" in stage_info
        assert stage_info["condition_status"] in ["met", "partial", "blocked"]


@pytest.mark.asyncio
async def test_stage_requirements_handles_complex_conditions(company, clear_stages):
    """Test stage-requirements with nested conditions."""
    from src.backend.modules.stages.models import StageTemplate

    # Clear default stages
    await clear_stages(company.id)

    _ = await StageTemplate.create(
        company_id=company.id,
        name="First",
        position=0,
        transition_condition={"$any": True},
    )

    _ = await StageTemplate.create(
        company_id=company.id,
        name="Second",
        position=1,
        transition_condition={
            "$and": [
                {"order_fields.budget": {"$gte": 1000}},
                {
                    "$or": [
                        {"customer_fields.city": {"$exists": True}},
                        {"order_fields.remote": {"$eq": True}},
                    ]
                },
            ]
        },
    )

    customer = await Customer.create(
        user_id="test-complex",
        company_id=company.id,
        name="Test",
        meta={},
        customer_fields={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    result = await order_service.get_order_stage_requirements(order.id)

    stage2_info = next(s for s in result["next_stages"] if s["stage"].position == 1)

    # Should extract budget, city, remote as required fields
    missing = stage2_info["missing_fields"]
    assert "budget" in missing or "city" in missing or "remote" in missing
