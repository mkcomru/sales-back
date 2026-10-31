"""Tests for manual stage recalculation."""

import pytest

from src.backend.modules.chat.models import Customer
from src.backend.modules.orders.service import OrderService


@pytest.mark.asyncio
async def test_recalculate_stage_manual_trigger(company, custom_test_stages):
    """Test manual recalculate_stage() works."""
    customer = await Customer.create(
        user_id="test-manual-recalc",
        company_id=company.id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    # Manually set order_fields without triggering auto-transition
    order.order_fields = {"budget": 2000}
    await order.save(update_fields=["order_fields"])

    initial_stage = order.stage_id

    # Manually trigger recalculation
    order = await order_service.recalculate_stage(order.id)

    # Should transition
    await order.fetch_related("stage")
    assert order.stage_id != initial_stage
    assert order.stage.position > 0


@pytest.mark.asyncio
async def test_recalculate_stage_endpoint(api_client, authenticated_user_with_company, clear_stages):
    """Test POST /orders/{id}/recalculate-stage endpoint."""
    from src.backend.modules.chat.models import Customer
    from src.backend.modules.stages.models import StageTemplate

    auth_data = authenticated_user_with_company
    company_id = auth_data["company"].id

    # Clear default stages and create test stages for this company
    await clear_stages(company_id)

    _ = await StageTemplate.create(
        company_id=company_id,
        name="Новый",
        position=0,
        transition_condition={"$any": True},
    )
    _ = await StageTemplate.create(
        company_id=company_id,
        name="Квалификация",
        position=1,
        transition_condition={"order_fields.budget": {"$gte": 1000}},
    )

    customer = await Customer.create(
        user_id="test-recalc-endpoint",
        company_id=company_id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company_id,
        customer_id=customer.id,
    )

    # Set fields manually (without triggering recalculation)
    order.order_fields = {"budget": 2500}
    await order.save(update_fields=["order_fields"])

    response = await api_client.post(
        f"/api/v1/companies/{company_id}/orders/{order.id}/recalculate-stage",
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()

    # Should have transitioned
    assert data["stage"]["position"] > 0


@pytest.mark.asyncio
async def test_recalculate_company_stages_endpoint(api_client, authenticated_user_with_company, clear_stages):
    """Test POST /companies/{id}/stages/recalculate recalculates all orders."""
    from src.backend.modules.chat.models import Customer
    from src.backend.modules.stages.models import StageTemplate

    auth_data = authenticated_user_with_company
    company_id = auth_data["company"].id

    # Clear default stages and create test stages for this company
    await clear_stages(company_id)

    _ = await StageTemplate.create(
        company_id=company_id,
        name="Новый",
        position=0,
        transition_condition={"$any": True},
    )
    _ = await StageTemplate.create(
        company_id=company_id,
        name="Квалификация",
        position=1,
        transition_condition={"order_fields.budget": {"$gte": 1000}},
    )

    customer = await Customer.create(
        user_id="test-company-recalc",
        company_id=company_id,
        name="Test",
        meta={},
    )

    order_service = OrderService()

    # Create 2 orders with budget set manually
    order1 = await order_service.create_order(
        company_id=company_id,
        customer_id=customer.id,
    )
    order1.order_fields = {"budget": 1500}
    await order1.save(update_fields=["order_fields"])

    order2 = await order_service.create_order(
        company_id=company_id,
        customer_id=customer.id,
    )
    order2.order_fields = {"budget": 2500}
    await order2.save(update_fields=["order_fields"])

    # Both should be on stage 0 initially (no auto-transition triggered)
    await order1.refresh_from_db()
    await order2.refresh_from_db()
    initial_stage1 = order1.stage_id
    initial_stage2 = order2.stage_id

    # Trigger company-wide recalculation
    response = await api_client.post(
        f"/api/v1/companies/{company_id}/stages/recalculate",
        headers=auth_data["headers"],
    )

    assert response.status_code == 202  # Async operation returns 202 Accepted
    data = response.json()
    assert "processed" in data and "transitions" in data and "errors" in data
    assert data["processed"] == 2  # Both orders processed
    assert data["errors"] == 0

    # Both orders should have transitioned
    await order1.refresh_from_db()
    await order2.refresh_from_db()

    await order1.fetch_related("stage")
    await order2.fetch_related("stage")

    # Should be on different stages than initial
    assert order1.stage_id != initial_stage1 or order1.stage.position > 0
    assert order2.stage_id != initial_stage2 or order2.stage.position > 0


@pytest.mark.asyncio
async def test_recalculate_skips_frozen_orders(company, custom_test_stages):
    """Test recalculate_stage skips frozen orders."""
    customer = await Customer.create(
        user_id="test-recalc-frozen",
        company_id=company.id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    # Freeze and set fields
    order.frozen = True
    order.order_fields = {"budget": 5000}
    await order.save(update_fields=["frozen", "order_fields"])

    initial_stage = order.stage_id

    # Try to recalculate
    order = await order_service.recalculate_stage(order.id)

    # Should not change
    assert order.stage_id == initial_stage


@pytest.mark.asyncio
async def test_recalculate_skips_closed_orders(company, custom_test_stages):
    """Test recalculate_stage skips closed orders."""
    from src.backend.modules.orders.repository import OrdersRepository

    customer = await Customer.create(
        user_id="test-recalc-closed",
        company_id=company.id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    orders_repo = OrdersRepository()

    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    # Close order
    from src.backend.modules.orders.models import OrderResult

    await orders_repo.close_order(order, OrderResult.WON, author_id=None)

    # Set fields and try to recalculate
    order.order_fields = {"budget": 5000}
    await order.save(update_fields=["order_fields"])

    initial_stage = order.stage_id

    order = await order_service.recalculate_stage(order.id)

    # Should not change
    assert order.stage_id == initial_stage


@pytest.mark.asyncio
async def test_recalculate_with_no_stages(company_without_stages):
    """Test recalculate_stage when company has no stages."""
    customer = await Customer.create(
        user_id="test-recalc-no-stages",
        company_id=company_without_stages.id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    orders_repo = order_service.orders_repo

    order_number = await orders_repo.get_next_order_number(company_without_stages.id)
    order = await orders_repo.create_order(
        company_id=company_without_stages.id,
        customer_id=customer.id,
        order_number=order_number,
    )

    # Should not raise error
    order = await order_service.recalculate_stage(order.id)

    # Stage should be None
    assert order.stage is None


@pytest.mark.asyncio
async def test_recalculate_moves_to_furthest_matching_stage(company, custom_test_stages):
    """Test recalculate moves to the furthest stage that matches."""
    customer = await Customer.create(
        user_id="test-recalc-furthest",
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

    # Set fields that match multiple stages
    order.order_fields = {"budget": 3000}
    await order.save(update_fields=["order_fields"])

    # Recalculate
    order = await order_service.recalculate_stage(order.id)

    await order.fetch_related("stage")

    # Should be on stage 2 (Предложение) because both budget and city conditions are met
    # Not just stage 1 (Квалификация) which only requires budget
    assert order.stage.position == 2


@pytest.mark.asyncio
async def test_recalculate_uses_completed_stages_context(company, clear_stages):
    """Test recalculate_stage uses completed_stages in conditions."""
    from src.backend.modules.stages.models import StageTemplate

    # Clear default stages
    await clear_stages(company.id)

    _ = await StageTemplate.create(
        company_id=company.id,
        name="First",
        position=0,
        transition_condition={"$any": True},
    )

    stage2 = await StageTemplate.create(
        company_id=company.id,
        name="Second",
        position=1,
        transition_condition={"order_fields.ready": {"$eq": True}},
    )

    stage3 = await StageTemplate.create(
        company_id=company.id,
        name="Third",
        position=2,
        transition_condition={"$stage_completed": stage2.id},
    )

    customer = await Customer.create(
        user_id="test-recalc-completed",
        company_id=company.id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    # Move to stage 2
    order = await order_service.update_order_fields(order.id, {"ready": True})
    await order.fetch_related("stage")
    assert order.stage_id == stage2.id

    # Now stage3 condition is met ($stage_completed)
    order = await order_service.recalculate_stage(order.id)
    await order.fetch_related("stage")

    # Should move to stage 3
    assert order.stage_id == stage3.id


@pytest.mark.asyncio
async def test_recalculate_stage_not_found_error(order_service):
    """Test recalculate_stage raises error for non-existent order."""
    with pytest.raises(ValueError, match="not found"):
        await order_service.recalculate_stage(99999)
