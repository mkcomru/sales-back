"""Integration tests for complex transition conditions."""

import pytest

from src.backend.modules.chat.models import Customer
from src.backend.modules.chat.service import ChatService
from src.backend.modules.orders.service import OrderService
from src.backend.modules.stages.models import StageTemplate


@pytest.mark.asyncio
async def test_stage_completed_condition(company, clear_stages):
    """Test $stage_completed operator in real scenario."""

    # Clear default stages
    await clear_stages(company.id)

    # Create stages with $stage_completed dependency
    stage1 = await StageTemplate.create(
        company_id=company.id,
        name="Initial Contact",
        position=0,
        transition_condition={"$any": True},
    )

    stage2 = await StageTemplate.create(
        company_id=company.id,
        name="Needs Assessment",
        position=1,
        transition_condition={"order_fields.contact_made": {"$eq": True}},
    )

    stage3 = await StageTemplate.create(
        company_id=company.id,
        name="Proposal Sent",
        position=2,
        transition_condition={
            "$and": [
                {"$stage_completed": stage2.id},
                {"order_fields.proposal_ready": {"$eq": True}},
            ]
        },
    )

    customer = await Customer.create(
        user_id="test-stage-completed",
        company_id=company.id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    # Start on stage 1
    await order.fetch_related("stage")
    assert order.stage_id == stage1.id

    # Move to stage 2
    order = await order_service.update_order_fields(order.id, {"contact_made": True})
    await order.fetch_related("stage")
    assert order.stage_id == stage2.id

    # Try to move to stage 3 (proposal_ready=True but stage2 completed)
    order = await order_service.update_order_fields(order.id, {"proposal_ready": True})
    await order.fetch_related("stage")

    # Should move to stage 3 because $stage_completed(stage2) is true
    assert order.stage_id == stage3.id


@pytest.mark.asyncio
async def test_prev_stage_completed_condition(company, clear_stages):
    """Test $prev_stage_completed operator in real scenario."""

    # Clear default stages
    await clear_stages(company.id)

    _ = await StageTemplate.create(
        company_id=company.id,
        name="Stage 1",
        position=0,
        transition_condition={"$any": True},
    )

    _ = await StageTemplate.create(
        company_id=company.id,
        name="Stage 2",
        position=1,
        transition_condition={"order_fields.ready_for_2": {"$eq": True}},
    )

    _ = await StageTemplate.create(
        company_id=company.id,
        name="Stage 3",
        position=2,
        transition_condition={
            "$and": [
                {"$prev_stage_completed": True},
                {"order_fields.ready_for_3": {"$eq": True}},
            ]
        },
    )

    customer = await Customer.create(
        user_id="test-prev-completed",
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
    order = await order_service.update_order_fields(order.id, {"ready_for_2": True})
    await order.fetch_related("stage")
    assert order.stage.position == 1

    # Try to move to stage 3
    order = await order_service.update_order_fields(order.id, {"ready_for_3": True})
    await order.fetch_related("stage")

    # Should move because previous stage (stage2, position 1) was completed
    assert order.stage.position == 2


@pytest.mark.asyncio
async def test_nested_and_or_conditions(company, clear_stages):
    """Test complex nested $and/$or conditions."""

    # Clear default stages
    await clear_stages(company.id)

    stage1 = await StageTemplate.create(
        company_id=company.id,
        name="Start",
        position=0,
        transition_condition={"$any": True},
    )

    # Complex condition: (budget > 1000 AND (city exists OR remote=true)) AND category is set
    stage2 = await StageTemplate.create(
        company_id=company.id,
        name="Qualified",
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
                {"order_fields.category": {"$exists": True}},
            ]
        },
    )

    customer = await Customer.create(
        user_id="test-nested",
        company_id=company.id,
        name="Test",
        meta={},
        customer_fields={},  # No city
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    # Set budget and category, but no city or remote
    order = await order_service.update_order_fields(
        order.id,
        {"budget": 2000, "category": "consulting"},
    )
    await order.fetch_related("stage")

    # Should NOT transition (missing city OR remote)
    assert order.stage_id == stage1.id

    # Add remote=true
    order = await order_service.update_order_fields(order.id, {"remote": True})
    await order.fetch_related("stage")

    # Should transition now
    assert order.stage_id == stage2.id


@pytest.mark.asyncio
async def test_not_operator_condition(company, clear_stages):
    """Test $not operator in conditions."""

    # Clear default stages
    await clear_stages(company.id)

    _ = await StageTemplate.create(
        company_id=company.id,
        name="Active",
        position=0,
        transition_condition={"$any": True},
    )

    stage2 = await StageTemplate.create(
        company_id=company.id,
        name="Not Interested",
        position=1,
        transition_condition={"$not": {"order_fields.interested": {"$eq": True}}},
    )

    customer = await Customer.create(
        user_id="test-not",
        company_id=company.id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    # Set interested=False
    order = await order_service.update_order_fields(order.id, {"interested": False})
    await order.fetch_related("stage")

    # Should transition to "Not Interested"
    assert order.stage_id == stage2.id


@pytest.mark.asyncio
async def test_comparison_operators(company, clear_stages):
    """Test all comparison operators in conditions."""

    # Clear default stages
    await clear_stages(company.id)

    _ = await StageTemplate.create(
        company_id=company.id,
        name="Start",
        position=0,
        transition_condition={"$any": True},
    )

    # Test $gt, $gte, $lt, $lte
    _ = await StageTemplate.create(
        company_id=company.id,
        name="Mid Budget",
        position=1,
        transition_condition={
            "$and": [
                {"order_fields.budget": {"$gte": 1000}},
                {"order_fields.budget": {"$lt": 5000}},
            ]
        },
    )

    _ = await StageTemplate.create(
        company_id=company.id,
        name="High Budget",
        position=2,
        transition_condition={"order_fields.budget": {"$gte": 5000}},
    )

    customer = await Customer.create(
        user_id="test-comparison",
        company_id=company.id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    # Set budget to 3000 (should go to stage2)
    order = await order_service.update_order_fields(order.id, {"budget": 3000})
    await order.fetch_related("stage")
    assert order.stage.position == 1

    # Increase budget to 6000 (should go to stage3)
    order = await order_service.update_order_fields(order.id, {"budget": 6000})
    await order.fetch_related("stage")
    assert order.stage.position == 2


@pytest.mark.skip(reason="Needs refactoring to work with default stages auto-creation")
@pytest.mark.asyncio
async def test_exists_operator_with_null_values(company, clear_stages):
    """Test $exists operator handles null/missing values correctly."""

    # Clear default stages
    await clear_stages(company.id)

    stage1 = await StageTemplate.create(
        company_id=company.id,
        name="Start",
        position=0,
        transition_condition={"$any": True},
    )

    stage2 = await StageTemplate.create(
        company_id=company.id,
        name="Has Email",
        position=1,
        transition_condition={"customer_fields.email": {"$exists": True}},
    )

    customer = await Customer.create(
        user_id="test-exists",
        company_id=company.id,
        name="Test",
        meta={},
        customer_fields={"email": None},  # Explicitly None
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    await order.fetch_related("stage")

    # Should NOT transition (email is None)
    assert order.stage_id == stage1.id

    # Set email to actual value
    chat_service = ChatService(order_service=OrderService())
    await chat_service.update_customer_fields(customer.id, {"email": "test@example.com"})

    await order.refresh_from_db()
    await order.fetch_related("stage")

    # Should transition now
    assert order.stage_id == stage2.id


@pytest.mark.skip(reason="Needs refactoring to work with default stages auto-creation")
@pytest.mark.asyncio
async def test_eq_ne_operators(company, clear_stages):
    """Test $eq and $ne operators."""

    # Clear default stages
    await clear_stages(company.id)

    _ = await StageTemplate.create(
        company_id=company.id,
        name="Start",
        position=0,
        transition_condition={"$any": True},
    )

    _ = await StageTemplate.create(
        company_id=company.id,
        name="VIP",
        position=1,
        transition_condition={"order_fields.priority": {"$eq": "high"}},
    )

    _ = await StageTemplate.create(
        company_id=company.id,
        name="Not Low Priority",
        position=2,
        transition_condition={"order_fields.priority": {"$ne": "low"}},
    )

    customer = await Customer.create(
        user_id="test-eq-ne",
        company_id=company.id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    # Set priority to "high"
    order = await order_service.update_order_fields(order.id, {"priority": "high"})
    await order.fetch_related("stage")

    # Should go to VIP (stage2)
    assert order.stage.position == 1


@pytest.mark.asyncio
async def test_multiple_transitions_in_sequence(company, clear_stages):
    """Test order moves through multiple stages sequentially."""

    # Clear default stages
    await clear_stages(company.id)

    stages = []
    for i in range(5):
        condition = {"$any": True} if i == 0 else {"order_fields.step": {"$gte": i}}
        stage = await StageTemplate.create(
            company_id=company.id,
            name=f"Stage {i}",
            position=i,
            transition_condition=condition,
        )
        stages.append(stage)

    customer = await Customer.create(
        user_id="test-sequence",
        company_id=company.id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    # Should start at stage 0
    await order.fetch_related("stage")
    assert order.stage.position == 0

    # Increment step through all stages
    for i in range(1, 5):
        order = await order_service.update_order_fields(order.id, {"step": i})
        await order.fetch_related("stage")
        assert order.stage.position == i


@pytest.mark.asyncio
async def test_condition_evaluation_error_handling(company, clear_stages):
    """Test system handles condition evaluation errors gracefully."""

    # Clear default stages
    await clear_stages(company.id)

    stage1 = await StageTemplate.create(
        company_id=company.id,
        name="Start",
        position=0,
        transition_condition={"$any": True},
    )

    # Create stage with condition that references non-existent context field
    _ = await StageTemplate.create(
        company_id=company.id,
        name="Special",
        position=1,
        transition_condition={"order_fields.value": {"$gte": 100}},
    )

    customer = await Customer.create(
        user_id="test-error-handling",
        company_id=company.id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    # Update with different field (not 'value')
    # Should not crash, just not transition
    order = await order_service.update_order_fields(order.id, {"other_field": "test"})
    await order.fetch_related("stage")

    # Should stay on stage 1 (error doesn't crash system)
    assert order.stage_id == stage1.id
