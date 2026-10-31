"""Integration tests for full funnel flow from order creation to close."""

import pytest

from src.backend.modules.chat.models import Customer
from src.backend.modules.chat.service import ChatService
from src.backend.modules.companies.service import CompaniesService
from src.backend.modules.orders.service import OrderService


@pytest.mark.skip(reason="Needs refactoring to work with default stages auto-creation")
@pytest.mark.asyncio
async def test_full_funnel_from_company_creation_to_order_close(test_superuser, clear_stages):
    """Integration test: create company → default stages → create order → fill fields → auto-close."""

    # 1. Create company (should create default stages)
    companies_service = CompaniesService()
    company = await companies_service.create_company(
        creator_id=test_superuser.id,
        name="Test Funnel Company",
        description="Test",
        rules="Rules",
        tone_of_voice="Professional",
        assistant_name="Assistant",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
        collection_name="test_funnel",
    )

    from src.backend.modules.stages.models import StageTemplate

    # Clear default stages and create custom stages for test
    await clear_stages(company.id)
    await StageTemplate.create(
        company_id=company.id, name="Новый", position=0, color="#000001", transition_condition={"$any": True}
    )
    await StageTemplate.create(
        company_id=company.id,
        name="Квалификация",
        position=1,
        color="#000002",
        transition_condition={"order_fields.budget": {"$gte": 1000}},
    )
    await StageTemplate.create(
        company_id=company.id,
        name="Предложение",
        position=2,
        color="#000003",
        transition_condition={
            "$and": [{"order_fields.budget": {"$gte": 1000}}, {"customer_fields.city": {"$exists": True}}]
        },
    )
    await StageTemplate.create(
        company_id=company.id,
        name="Закрыто",
        position=3,
        color="#000004",
        is_final=True,
        auto_close=True,
        transition_condition=None,
    )

    stages = await StageTemplate.filter(company_id=company.id).order_by("position").all()
    assert len(stages) == 4

    # 2. Create customer
    customer = await Customer.create(
        user_id="test-funnel-user",
        company_id=company.id,
        name="Test Customer",
        meta={},
        customer_fields={"city": "Moscow", "phone": "+7900"},
    )

    # 3. Create order (should get initial stage)
    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    await order.fetch_related("stage")
    assert order.stage is not None
    assert order.stage.position == 0
    assert order.stage.name == "Новый"

    # 4. Fill budget field (should transition to "Квалификация")
    order = await order_service.update_order_fields(order.id, {"budget": 5000})
    await order.fetch_related("stage")
    assert order.stage.position == 1
    assert order.stage.name == "Квалификация"

    # 5. Fill more fields (should transition to "Предложение")
    # Stage "Предложение" requires budget >= 1000 AND city exists
    # City already exists in customer_fields, so should transition
    order = await order_service.recalculate_stage(order.id)
    await order.fetch_related("stage")
    assert order.stage.position == 2
    assert order.stage.name == "Предложение"

    # 6. Final stage cannot be reached by auto-transition (no transition_condition)
    # Order should stay on "Предложение" stage
    order = await order_service.recalculate_stage(order.id)
    await order.fetch_related("stage")

    # Should still be on "Предложение" stage (position 2)
    assert order.stage.position == 2
    assert order.stage.is_final is False

    # Order should NOT be auto-closed (final stage unreachable by auto-transition)
    assert order.closed_at is None
    assert order.result is None


@pytest.mark.skip(reason="Needs refactoring to work with default stages auto-creation")
@pytest.mark.asyncio
async def test_order_rejected_flow(test_superuser, clear_stages):
    """Integration test: order gets rejected and moves to lost stage."""
    companies_service = CompaniesService()
    company = await companies_service.create_company(
        creator_id=test_superuser.id,
        name="Test Rejected Company",
        description="Test",
        rules="Rules",
        tone_of_voice="Professional",
        assistant_name="Assistant",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
        collection_name="test_rejected",
    )

    customer = await Customer.create(
        user_id="test-rejected-user",
        company_id=company.id,
        name="Rejected Customer",
        meta={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    # With new logic, final stage cannot be reached by auto-transition
    # Order should stay on initial stage
    order = await order_service.recalculate_stage(order.id)
    await order.fetch_related("stage")

    # Should still be on initial stage (no auto-transition to final)
    assert order.stage.position == 0
    assert order.closed_at is None
    assert order.result is None


@pytest.mark.skip(reason="Needs refactoring to work with default stages auto-creation")
@pytest.mark.asyncio
async def test_multiple_orders_same_customer(test_superuser, clear_stages):
    """Integration test: multiple orders for same customer move independently."""
    companies_service = CompaniesService()
    company = await companies_service.create_company(
        creator_id=test_superuser.id,
        name="Test Multi Order Company",
        description="Test",
        rules="Rules",
        tone_of_voice="Professional",
        assistant_name="Assistant",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
        collection_name="test_multi",
    )

    customer = await Customer.create(
        user_id="test-multi-user",
        company_id=company.id,
        name="Multi Order Customer",
        meta={},
        customer_fields={"city": "Moscow"},
    )

    order_service = OrderService()

    # Create 3 orders
    order1 = await order_service.create_order(company_id=company.id, customer_id=customer.id)
    order2 = await order_service.create_order(company_id=company.id, customer_id=customer.id)
    order3 = await order_service.create_order(company_id=company.id, customer_id=customer.id)

    # All start on stage 0
    await order1.fetch_related("stage")
    await order2.fetch_related("stage")
    await order3.fetch_related("stage")

    assert order1.stage.position == 0
    assert order2.stage.position == 0
    assert order3.stage.position == 0

    # Move order1 forward
    order1 = await order_service.update_order_fields(order1.id, {"budget": 2000})

    # order2 and order3 stay at their current stages
    # (final stage cannot be reached by auto-transition)

    await order1.refresh_from_db()
    await order2.refresh_from_db()
    await order3.refresh_from_db()

    await order1.fetch_related("stage")
    await order2.fetch_related("stage")
    await order3.fetch_related("stage")

    # Check independent movement
    assert order1.stage.position == 2  # Budget + city
    assert order2.stage.position == 0  # Unchanged (no auto-transition to final)
    assert order2.closed_at is None
    assert order3.stage.position == 0  # Unchanged


@pytest.mark.skip(reason="Needs refactoring to work with default stages auto-creation")
@pytest.mark.asyncio
async def test_customer_field_updates_affect_all_orders(test_superuser, clear_stages):
    """Integration test: updating customer_fields recalculates all active orders."""
    companies_service = CompaniesService()
    company = await companies_service.create_company(
        creator_id=test_superuser.id,
        name="Test Customer Fields Company",
        description="Test",
        rules="Rules",
        tone_of_voice="Professional",
        assistant_name="Assistant",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
        collection_name="test_customer_fields",
    )

    customer = await Customer.create(
        user_id="test-customer-fields-user",
        company_id=company.id,
        name="Customer Fields Test",
        meta={},
        customer_fields={},  # No city initially
    )

    order_service = OrderService()

    # Create 2 orders with budget
    order1 = await order_service.create_order(company_id=company.id, customer_id=customer.id)
    order1 = await order_service.update_order_fields(order1.id, {"budget": 1500})

    order2 = await order_service.create_order(company_id=company.id, customer_id=customer.id)
    order2 = await order_service.update_order_fields(order2.id, {"budget": 2500})

    await order1.fetch_related("stage")
    await order2.fetch_related("stage")

    # Both should be on stage 1 (budget only, no city)
    assert order1.stage.position == 1
    assert order2.stage.position == 1

    # Update customer_fields to add city
    chat_service = ChatService(order_service=OrderService())
    await chat_service.update_customer_fields(customer.id, {"city": "Saint Petersburg"})

    # Both orders should now move to stage 2
    await order1.refresh_from_db()
    await order2.refresh_from_db()
    await order1.fetch_related("stage")
    await order2.fetch_related("stage")

    assert order1.stage.position == 2
    assert order2.stage.position == 2


@pytest.mark.skip(reason="Needs refactoring to work with default stages auto-creation")
@pytest.mark.asyncio
async def test_frozen_order_isolation(test_superuser, clear_stages):
    """Integration test: frozen order doesn't move while others do."""
    companies_service = CompaniesService()
    company = await companies_service.create_company(
        creator_id=test_superuser.id,
        name="Test Frozen Company",
        description="Test",
        rules="Rules",
        tone_of_voice="Professional",
        assistant_name="Assistant",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
        collection_name="test_frozen_integration",
    )

    customer = await Customer.create(
        user_id="test-frozen-integration",
        company_id=company.id,
        name="Frozen Test",
        meta={},
        customer_fields={"city": "Moscow"},
    )

    order_service = OrderService()

    order1 = await order_service.create_order(company_id=company.id, customer_id=customer.id)
    order2 = await order_service.create_order(company_id=company.id, customer_id=customer.id)

    # Freeze order1
    order1.frozen = True
    await order1.save(update_fields=["frozen"])

    # Update both orders
    order1 = await order_service.update_order_fields(order1.id, {"budget": 3000})
    order2 = await order_service.update_order_fields(order2.id, {"budget": 3000})

    await order1.fetch_related("stage")
    await order2.fetch_related("stage")

    # order1 should stay on stage 0 (frozen)
    assert order1.stage.position == 0
    assert order1.frozen is True

    # order2 should transition to stage 2 (budget + city)
    assert order2.stage.position == 2
    assert order2.frozen is False


@pytest.mark.skip(reason="Needs refactoring to work with default stages auto-creation")
@pytest.mark.asyncio
async def test_stage_deletion_nullifies_orders(test_superuser, clear_stages):
    """Integration test: deleting stage sets order.stage to NULL."""
    from src.backend.modules.stages.service import StagesService

    companies_service = CompaniesService()
    company = await companies_service.create_company(
        creator_id=test_superuser.id,
        name="Test Delete Stage Company",
        description="Test",
        rules="Rules",
        tone_of_voice="Professional",
        assistant_name="Assistant",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
        collection_name="test_delete_stage",
    )

    customer = await Customer.create(
        user_id="test-delete-stage-user",
        company_id=company.id,
        name="Delete Stage Test",
        meta={},
    )

    order_service = OrderService()
    order = await order_service.create_order(company_id=company.id, customer_id=customer.id)

    initial_stage_id = order.stage_id

    # Delete the stage
    stages_service = StagesService()
    await stages_service.delete_stage(initial_stage_id)

    # Order.stage should be NULL
    await order.refresh_from_db()
    assert order.stage_id is None
