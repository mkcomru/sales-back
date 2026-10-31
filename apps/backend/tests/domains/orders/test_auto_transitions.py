"""Tests for automatic stage transitions."""

import pytest

from src.backend.modules.chat.models import Customer
from src.backend.modules.orders.models import OrderLog, OrderLogType
from src.backend.modules.orders.service import OrderService
from src.backend.modules.stages.models import StageTemplate


@pytest.mark.asyncio
async def test_new_order_gets_initial_stage(company, custom_test_stages):
    """Test new order is assigned initial stage with $any condition."""
    customer = await Customer.create(
        user_id="test-initial",
        company_id=company.id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    await order.fetch_related("stage")

    # Should be on first stage (position 0)
    assert order.stage is not None
    assert order.stage.position == 0
    assert order.stage.name == "Новый"


@pytest.mark.asyncio
async def test_order_transitions_when_condition_met(company, custom_test_stages):
    """Test order auto-transitions when field update meets condition."""
    customer = await Customer.create(
        user_id="test-transition",
        company_id=company.id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    # Should start on first stage
    await order.refresh_from_db()
    assert order.stage.position == 0

    # Update budget to meet condition for stage 1 (budget >= 1000)
    order = await order_service.update_order_fields(
        order.id,
        {"budget": 1500},
    )

    await order.fetch_related("stage")

    # Should transition to second stage
    assert order.stage.position == 1
    assert order.stage.name == "Квалификация"


@pytest.mark.asyncio
async def test_order_skips_stages_when_multiple_conditions_met(company, custom_test_stages):
    """Test order can skip stages if multiple conditions are met at once."""
    customer = await Customer.create(
        user_id="test-skip",
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

    # Update budget - should move to stage 2 directly because both conditions are met
    # Stage 1: budget >= 1000
    # Stage 2: budget >= 1000 AND city exists
    order = await order_service.update_order_fields(
        order.id,
        {"budget": 2000},
    )

    await order.fetch_related("stage")

    # Should be on stage 2 (Предложение)
    assert order.stage.position == 2
    assert order.stage.name == "Предложение"


@pytest.mark.asyncio
async def test_order_does_not_transition_backwards(company, custom_test_stages):
    """Test order never moves to lower position stage."""
    customer = await Customer.create(
        user_id="test-no-back",
        company_id=company.id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    # Move to stage 1
    order = await order_service.update_order_fields(order.id, {"budget": 1500})
    await order.fetch_related("stage")
    assert order.stage.position == 1

    # Remove budget - should NOT move back to stage 0
    order = await order_service.update_order_fields(order.id, {"budget": None})
    await order.fetch_related("stage")

    # Should stay on stage 1
    assert order.stage.position == 1


@pytest.mark.asyncio
async def test_order_logs_auto_transition(company, custom_test_stages):
    """Test auto-transition creates OrderLog with trigger=auto."""
    customer = await Customer.create(
        user_id="test-log",
        company_id=company.id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    initial_stage_id = order.stage_id

    # Trigger transition
    order = await order_service.update_order_fields(order.id, {"budget": 1500})

    # Check log
    logs = await OrderLog.filter(
        order_id=order.id,
        type=OrderLogType.STAGE_CHANGE,
    ).all()

    # Should have 2 logs: initial stage assignment + auto-transition
    assert len(logs) >= 2

    # Last log should be auto-transition
    last_log = logs[-1]
    assert last_log.data["from_stage_id"] == initial_stage_id
    assert last_log.data["to_stage_id"] == order.stage_id
    assert last_log.data["trigger"] == "auto"
    assert last_log.author_id is None  # System


@pytest.mark.asyncio
async def test_final_stage_no_auto_transition(company, custom_test_stages):
    """Test final stage cannot be reached by auto-transition (no transition_condition)."""
    customer = await Customer.create(
        user_id="test-final-stage",
        company_id=company.id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    # Move to stage 2 first
    order = await order_service.update_order_fields(
        order.id,
        {"budget": 2000},
    )
    await order.fetch_related("stage")

    # Add customer city to meet stage 2 conditions
    customer.customer_fields = {"city": "Moscow"}
    await customer.save(update_fields=["customer_fields"])

    order = await order_service.recalculate_stage(order.id)
    await order.fetch_related("stage")

    # Should be on stage 2 (Предложение), not final stage
    assert order.stage.position == 2
    assert order.stage.is_final is False

    # Final stage has no transition_condition, so order cannot auto-transition to it
    # Order should NOT be closed
    assert order.closed_at is None
    assert order.result is None


@pytest.mark.asyncio
async def test_customer_fields_change_triggers_recalculation(company, custom_test_stages, chat_service):
    """Test changing customer_fields recalculates all active orders."""
    from src.backend.modules.orders.service import OrderService

    order_service = OrderService()
    customer = await Customer.create(
        user_id="test-customer-recalc",
        company_id=company.id,
        name="Test",
        meta={},
        customer_fields={},
    )

    # Create 2 orders with budget
    order1 = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )
    await order_service.update_order_fields(order1.id, {"budget": 1500})

    order2 = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )
    await order_service.update_order_fields(order2.id, {"budget": 2000})

    await order1.refresh_from_db()
    await order2.refresh_from_db()
    await order1.fetch_related("stage")
    await order2.fetch_related("stage")

    # Both should be on stage 1 (budget condition met, but no city)
    assert order1.stage.position == 1
    assert order2.stage.position == 1

    # Update customer fields to add city
    await chat_service.update_customer_fields(customer.user_id, company.id, {"city": "Moscow"})

    # Both orders should now transition to stage 2 (budget + city)
    await order1.refresh_from_db()
    await order2.refresh_from_db()
    await order1.fetch_related("stage")
    await order2.fetch_related("stage")

    assert order1.stage.position == 2
    assert order2.stage.position == 2


@pytest.mark.asyncio
async def test_closed_order_does_not_recalculate(company, custom_test_stages):
    """Test closed orders are skipped during recalculation."""
    from src.backend.modules.orders.repository import OrdersRepository

    customer = await Customer.create(
        user_id="test-closed",
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

    # Close order manually
    from src.backend.modules.orders.models import OrderResult

    await orders_repo.close_order(order, OrderResult.WON, author_id=None)

    initial_stage_id = order.stage_id

    # Try to trigger recalculation
    order = await order_service.update_order_fields(order.id, {"budget": 5000})

    # Stage should not change
    await order.refresh_from_db()
    assert order.stage_id == initial_stage_id


@pytest.mark.asyncio
async def test_order_with_no_matching_stage_stays_put(company, clear_stages):
    """Test order without matching conditions stays on current stage."""
    # Clear default stages
    await clear_stages(company.id)

    # Create stages with specific conditions (no fallback)
    stage1 = await StageTemplate.create(
        company_id=company.id,
        name="Stage 1",
        position=0,
        transition_condition={"$any": True},
    )

    _ = await StageTemplate.create(
        company_id=company.id,
        name="Stage 2",
        position=1,
        transition_condition={"order_fields.special": {"$eq": "value"}},
    )

    customer = await Customer.create(
        user_id="test-no-match",
        company_id=company.id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    # Should be on stage 1
    await order.refresh_from_db()
    assert order.stage_id == stage1.id

    # Update with field that doesn't match
    order = await order_service.update_order_fields(order.id, {"budget": 1000})

    # Should still be on stage 1
    await order.refresh_from_db()
    assert order.stage_id == stage1.id


@pytest.mark.asyncio
async def test_order_creation_through_thread_assigns_stage(company, custom_test_stages):
    """Test order created via thread gets initial stage."""
    from src.backend.modules.chat.repository import ThreadsRepository

    customer = await Customer.create(
        user_id="test-thread-order",
        company_id=company.id,
        name="Test",
        meta={},
    )

    threads_repo = ThreadsRepository()
    thread, _ = await threads_repo.get_or_create(
        customer=customer,
        company=company,
        channel_type="telegram",
        connector_id="test",
    )

    order_service = OrderService()
    order = await order_service.ensure_active_order(thread)

    await order.fetch_related("stage")

    # Should have initial stage
    assert order.stage is not None
    assert order.stage.position == 0
