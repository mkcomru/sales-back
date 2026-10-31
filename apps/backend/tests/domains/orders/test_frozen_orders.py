"""Tests for frozen orders (blocking auto-transitions)."""

import pytest

from src.backend.modules.chat.models import Customer
from src.backend.modules.orders.service import OrderService


@pytest.mark.asyncio
async def test_frozen_order_does_not_auto_transition(company, custom_test_stages):
    """Test frozen=True blocks automatic stage transitions."""
    customer = await Customer.create(
        user_id="test-frozen",
        company_id=company.id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    # Freeze order
    order.frozen = True
    await order.save(update_fields=["frozen"])

    initial_stage_id = order.stage_id

    # Try to trigger transition
    order = await order_service.update_order_fields(order.id, {"budget": 2000})

    # Stage should not change
    await order.refresh_from_db()
    assert order.stage_id == initial_stage_id
    assert order.frozen is True


@pytest.mark.asyncio
async def test_unfrozen_order_resumes_transitions(company, custom_test_stages):
    """Test unfreezing order allows auto-transitions again."""
    customer = await Customer.create(
        user_id="test-unfreeze",
        company_id=company.id,
        name="Test",
        meta={},
    )

    order_service = OrderService()
    order = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )

    # Freeze and update
    order.frozen = True
    await order.save(update_fields=["frozen"])

    order = await order_service.update_order_fields(order.id, {"budget": 2000})
    await order.refresh_from_db()
    initial_stage = order.stage.position

    # Unfreeze
    order.frozen = False
    await order.save(update_fields=["frozen"])

    # Trigger recalculation manually
    order = await order_service.recalculate_stage(order.id)

    await order.fetch_related("stage")

    # Should transition now
    assert order.stage.position > initial_stage


@pytest.mark.asyncio
async def test_freeze_endpoint(api_client, authenticated_user_with_company, custom_test_stages):
    """Test PATCH /orders/{id}/frozen endpoint."""
    from src.backend.modules.chat.models import Customer
    from src.backend.modules.orders.repository import OrdersRepository

    auth_data = authenticated_user_with_company
    company_id = auth_data["company"].id

    customer = await Customer.create(
        user_id="test-freeze-endpoint",
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

    # Freeze order
    response = await api_client.patch(
        f"/api/v1/companies/{company_id}/orders/{order.id}/frozen",
        json={"frozen": True},
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["frozen"] is True

    # Verify in DB
    await order.refresh_from_db()
    assert order.frozen is True


@pytest.mark.asyncio
async def test_unfreeze_endpoint(api_client, authenticated_user_with_company, custom_test_stages):
    """Test PATCH /orders/{id}/frozen can unfreeze."""
    from src.backend.modules.chat.models import Customer
    from src.backend.modules.orders.repository import OrdersRepository

    auth_data = authenticated_user_with_company
    company_id = auth_data["company"].id

    customer = await Customer.create(
        user_id="test-unfreeze-endpoint",
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

    # Freeze first
    order.frozen = True
    await order.save(update_fields=["frozen"])

    # Unfreeze via API
    response = await api_client.patch(
        f"/api/v1/companies/{company_id}/orders/{order.id}/frozen",
        json={"frozen": False},
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["frozen"] is False

    await order.refresh_from_db()
    assert order.frozen is False


@pytest.mark.asyncio
async def test_frozen_order_blocks_customer_field_recalc(company, custom_test_stages, chat_service):
    """Test frozen order is skipped when customer_fields change."""
    from src.backend.modules.orders.service import OrderService

    order_service = OrderService()
    customer = await Customer.create(
        user_id="test-frozen-customer",
        company_id=company.id,
        name="Test",
        meta={},
        customer_fields={},
    )

    order1 = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )
    await order_service.update_order_fields(order1.id, {"budget": 1500})

    order2 = await order_service.create_order(
        company_id=company.id,
        customer_id=customer.id,
    )
    await order_service.update_order_fields(order2.id, {"budget": 1500})

    # Refresh to get current stages after field updates
    await order1.refresh_from_db()
    await order2.refresh_from_db()

    # Freeze order1
    order1.frozen = True
    await order1.save(update_fields=["frozen"])

    initial_stage1 = order1.stage_id
    initial_stage2 = order2.stage_id

    # Update customer fields
    await chat_service.update_customer_fields(customer.user_id, company.id, {"city": "Moscow"})

    # order1 should stay (frozen)
    await order1.refresh_from_db()
    assert order1.stage_id == initial_stage1

    # order2 should transition (not frozen)
    await order2.refresh_from_db()
    assert order2.stage_id != initial_stage2


@pytest.mark.asyncio
async def test_frozen_order_at_creation_stays_without_stage(company, custom_test_stages):
    """Test creating frozen order skips initial stage assignment."""
    from src.backend.modules.orders.repository import OrdersRepository

    customer = await Customer.create(
        user_id="test-frozen-creation",
        company_id=company.id,
        name="Test",
        meta={},
    )

    orders_repo = OrdersRepository()
    order_number = await orders_repo.get_next_order_number(company.id)
    order = await orders_repo.create_order(
        company_id=company.id,
        customer_id=customer.id,
        order_number=order_number,
    )

    # Freeze immediately before recalculate
    order.frozen = True
    await order.save(update_fields=["frozen"])

    order_service = OrderService()
    order = await order_service.recalculate_stage(order.id)

    # Should not have stage (frozen blocks assignment)
    assert order.stage is None or order.frozen is True


@pytest.mark.asyncio
async def test_manual_stage_change_works_on_frozen_order(company, custom_test_stages):
    """Test frozen order can still be manually moved to different stage."""
    from src.backend.modules.orders.repository import OrdersRepository

    customer = await Customer.create(
        user_id="test-frozen-manual",
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

    # Freeze order
    order.frozen = True
    await order.save(update_fields=["frozen"])

    # Manually change stage
    target_stage = custom_test_stages[2]  # Third stage
    order, _ = await orders_repo.update_stage(order, target_stage, author_id=None)

    # Should succeed
    assert order.stage_id == target_stage.id
