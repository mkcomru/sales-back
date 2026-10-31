"""Tests for Order Logs functionality."""

from __future__ import annotations

import pytest

from src.backend.modules.orders.models import OrderLog, OrderLogType, OrderResult


@pytest.mark.asyncio
async def test_create_order_creates_log(
    orders_repo,
    customer_with_company,
    manager_user,
):
    """Test that creating an order creates ORDER_CREATED log."""
    customer, company = customer_with_company
    manager, _, _ = manager_user

    order_number = await orders_repo.get_next_order_number(company.id)
    order = await orders_repo.create_order(
        company_id=company.id,
        customer_id=customer.id,
        order_number=order_number,
        initial_channel="whatsapp",
        assignee_id=manager.id,
        author_id=manager.id,
    )

    logs = await OrderLog.filter(order_id=order.id).all()
    assert len(logs) == 1
    assert logs[0].type == OrderLogType.ORDER_CREATED
    assert logs[0].author_id == manager.id
    assert logs[0].data["order_number"] == order_number
    assert logs[0].data["initial_channel"] == "whatsapp"
    assert logs[0].data["assignee_id"] == manager.id


@pytest.mark.asyncio
async def test_create_order_system_creates_log_without_author(
    orders_repo,
    customer_with_company,
):
    """Test that system-created order has log with null author."""
    customer, company = customer_with_company

    order_number = await orders_repo.get_next_order_number(company.id)
    order = await orders_repo.create_order(
        company_id=company.id,
        customer_id=customer.id,
        order_number=order_number,
        initial_channel="telegram",
        author_id=None,
    )

    logs = await OrderLog.filter(order_id=order.id).all()
    assert len(logs) == 1
    assert logs[0].type == OrderLogType.ORDER_CREATED
    assert logs[0].author_id is None


@pytest.mark.asyncio
async def test_update_stage_creates_log(
    order_with_customer,
    manager_user,
    orders_repo,
    clear_stages,
):
    """Test that updating stage creates STAGE_CHANGE log."""
    from src.backend.modules.stages.models import StageTemplate

    order, _, company = order_with_customer
    manager, _, _ = manager_user

    # Clear default stages
    await clear_stages(company.id)

    # Create stage templates
    stage1 = await StageTemplate.create(
        company_id=company.id,
        name="Stage 1",
        position=0,
    )
    stage2 = await StageTemplate.create(
        company_id=company.id,
        name="Stage 2",
        position=1,
    )

    # Set initial stage
    await orders_repo.update_stage(order, stage1, author_id=None)

    # Update to new stage
    await orders_repo.update_stage(order, stage2, author_id=manager.id)

    logs = await OrderLog.filter(order_id=order.id, type=OrderLogType.STAGE_CHANGE).all()
    assert len(logs) == 2  # Initial + update
    last_log = logs[-1]
    assert last_log.data["from_stage_id"] == stage1.id
    assert last_log.data["to_stage_id"] == stage2.id
    assert last_log.data["trigger"] == "manual"
    assert last_log.author_id == manager.id


@pytest.mark.asyncio
async def test_update_stage_system_creates_log_with_auto_trigger(
    order_with_customer,
    orders_repo,
    clear_stages,
):
    """Test that system stage update has auto trigger."""
    from src.backend.modules.stages.models import StageTemplate

    order, _, company = order_with_customer

    # Clear default stages
    await clear_stages(company.id)

    stage = await StageTemplate.create(
        company_id=company.id,
        name="Auto Stage",
        position=0,
    )

    await orders_repo.update_stage(order, stage, author_id=None)

    logs = await OrderLog.filter(order_id=order.id, type=OrderLogType.STAGE_CHANGE).all()
    assert len(logs) == 1
    assert logs[0].data["trigger"] == "auto"
    assert logs[0].author_id is None


@pytest.mark.asyncio
async def test_update_assignee_creates_log(
    order_with_customer,
    manager_user,
    orders_repo,
):
    """Test that updating assignee creates ASSIGNEE_CHANGE log."""
    order, _, _ = order_with_customer
    manager, _, _ = manager_user

    assert order.assignee_id is None

    await orders_repo.update_assignee(order, manager.id, author_id=manager.id)

    logs = await OrderLog.filter(order_id=order.id, type=OrderLogType.ASSIGNEE_CHANGE).all()
    assert len(logs) == 1
    assert logs[0].data["from_user_id"] is None
    assert logs[0].data["to_user_id"] == manager.id
    assert logs[0].author_id == manager.id


@pytest.mark.asyncio
async def test_update_fields_creates_log_for_each_field(
    order_with_customer,
    manager_user,
    orders_repo,
):
    """Test that updating fields creates FIELD_CHANGE log for each changed field."""
    order, _, _ = order_with_customer
    manager, _, _ = manager_user

    fields = {
        "budget": 150000,
        "destination": "Turkey",
        "dates": "2024-07-15",
    }

    await orders_repo.update_fields(order, fields, author_id=manager.id)

    logs = await OrderLog.filter(order_id=order.id, type=OrderLogType.FIELD_CHANGE).order_by("id").all()
    assert len(logs) == 3

    log_data = {log.data["field"]: log.data for log in logs}

    assert log_data["budget"]["old"] is None
    assert log_data["budget"]["new"] == 150000
    assert log_data["budget"]["level"] == "order"

    assert log_data["destination"]["old"] is None
    assert log_data["destination"]["new"] == "Turkey"

    assert log_data["dates"]["old"] is None
    assert log_data["dates"]["new"] == "2024-07-15"

    for log in logs:
        assert log.author_id == manager.id


@pytest.mark.asyncio
async def test_update_fields_no_log_for_unchanged_fields(
    order_with_customer,
    orders_repo,
):
    """Test that updating field to same value doesn't create log."""
    order, _, _ = order_with_customer

    await orders_repo.update_fields(order, {"budget": 100000})

    logs_before = await OrderLog.filter(order_id=order.id, type=OrderLogType.FIELD_CHANGE).count()

    await orders_repo.update_fields(order, {"budget": 100000})

    logs_after = await OrderLog.filter(order_id=order.id, type=OrderLogType.FIELD_CHANGE).count()

    assert logs_after == logs_before


@pytest.mark.asyncio
async def test_close_order_creates_log(
    order_with_customer,
    manager_user,
    orders_repo,
):
    """Test that closing order creates STAGE_CHANGE log with result."""
    order, _, _ = order_with_customer
    manager, _, _ = manager_user

    await orders_repo.close_order(order, OrderResult.WON, author_id=manager.id)

    logs = await OrderLog.filter(order_id=order.id, type=OrderLogType.STAGE_CHANGE).all()
    assert len(logs) == 1
    assert logs[0].data["result"] == OrderResult.WON.value
    assert logs[0].data["trigger"] == "system"
    assert logs[0].author_id == manager.id


@pytest.mark.asyncio
async def test_add_comment_creates_log(
    order_with_customer,
    manager_user,
    orders_repo,
):
    """Test that adding comment creates COMMENT log."""
    order, _, _ = order_with_customer
    manager, _, _ = manager_user

    comment_text = "Клиент просил перезвонить после 15:00"
    log = await orders_repo.add_comment(order, comment_text, author_id=manager.id)

    assert log.type == OrderLogType.COMMENT
    assert log.data["text"] == comment_text
    assert log.author_id == manager.id


@pytest.mark.asyncio
async def test_get_logs_returns_ordered_by_created_at(
    order_with_customer,
    manager_user,
    orders_repo,
    clear_stages,
):
    """Test that get_logs returns logs ordered by created_at descending."""
    from src.backend.modules.stages.models import StageTemplate

    order, _, company = order_with_customer
    manager, _, _ = manager_user

    # Clear default stages
    await clear_stages(company.id)

    stage = await StageTemplate.create(
        company_id=company.id,
        name="Test Stage",
        position=0,
    )

    await orders_repo.update_stage(order, stage, author_id=manager.id)
    await orders_repo.add_comment(order, "Comment 1", author_id=manager.id)
    await orders_repo.update_fields(order, {"budget": 100000}, author_id=manager.id)
    await orders_repo.add_comment(order, "Comment 2", author_id=manager.id)

    logs = await orders_repo.get_logs(order.id)

    assert len(logs) >= 4

    assert logs[0].type == OrderLogType.COMMENT
    assert logs[0].data["text"] == "Comment 2"

    assert logs[1].type == OrderLogType.FIELD_CHANGE

    assert logs[2].type == OrderLogType.COMMENT
    assert logs[2].data["text"] == "Comment 1"


@pytest.mark.asyncio
async def test_order_log_has_author_relation(
    order_with_customer,
    manager_user,
    orders_repo,
):
    """Test that OrderLog has proper relation to author."""
    order, _, _ = order_with_customer
    manager, user, _ = manager_user

    await orders_repo.add_comment(order, "Test comment", author_id=manager.id)

    logs = await OrderLog.filter(order_id=order.id, type=OrderLogType.COMMENT).select_related("author__user").all()

    assert len(logs) == 1
    log = logs[0]
    assert log.author is not None
    assert log.author.id == manager.id
    assert log.author.user.id == user.id
    assert log.author.user.email == user.email
