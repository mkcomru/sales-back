"""Ping evaluator: thread filter uses assistant_active and excludes HANDOFF (042: assistant_mode)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.backend.modules.billing.models import BillingStatus
from src.backend.modules.chat.models import AssistantMode, Customer, Thread, ThreadState
from src.backend.modules.orders.repository import OrdersRepository
from src.backend.modules.pings.evaluator import evaluate_pings
from src.backend.modules.stages.models import StageTemplate
from src.backend.modules.tasks.models import Task, TaskSubjectType
from src.backend.modules.tasks.repository import TaskRepository


async def _count_open_tasks_for_order(order_id: int) -> int:
    return await Task.filter(
        subject_type=TaskSubjectType.ORDER,
        subject_id=order_id,
        completed=False,
        cancelled_at__isnull=True,
    ).count()


@pytest.mark.asyncio
async def test_evaluate_pings_skips_thread_when_assistant_inactive(company) -> None:
    customer = await Customer.create(user_id="ping-eval-inactive", company_id=company.id, meta={})
    orders_repo = OrdersRepository()
    order_number = await orders_repo.get_next_order_number(company.id)
    order = await orders_repo.create_order(
        company_id=company.id,
        customer_id=customer.id,
        order_number=order_number,
        initial_channel="telegram",
    )
    stage = await StageTemplate.filter(company_id=company.id).first()
    assert stage is not None
    order.stage_id = stage.id
    order.charged_at = datetime.now(UTC)
    order.billing_status = BillingStatus.ACTIVE
    await order.save(update_fields=["stage_id", "charged_at", "billing_status"])

    await Thread.create(
        thread_id="ping-eval-thread-inactive",
        customer_id=customer.id,
        company_id=company.id,
        active_order_id=order.id,
        channel_type="telegram",
        conversation_id="conv-ping-inactive",
        state=ThreadState.ACTIVE,
        assistant_mode=AssistantMode.INACTIVE,
        last_customer_message_at=datetime.now(UTC) - timedelta(minutes=10),
    )

    task_repo = TaskRepository()
    before = await _count_open_tasks_for_order(order.id)
    await evaluate_pings(task_repo)
    after = await _count_open_tasks_for_order(order.id)
    assert after == before


@pytest.mark.asyncio
async def test_evaluate_pings_skips_thread_in_handoff_even_if_assistant_active(company) -> None:
    customer = await Customer.create(user_id="ping-eval-handoff", company_id=company.id, meta={})
    orders_repo = OrdersRepository()
    order_number = await orders_repo.get_next_order_number(company.id)
    order = await orders_repo.create_order(
        company_id=company.id,
        customer_id=customer.id,
        order_number=order_number,
        initial_channel="telegram",
    )
    stage = await StageTemplate.filter(company_id=company.id).first()
    assert stage is not None
    order.stage_id = stage.id
    order.charged_at = datetime.now(UTC)
    order.billing_status = BillingStatus.ACTIVE
    await order.save(update_fields=["stage_id", "charged_at", "billing_status"])

    await Thread.create(
        thread_id="ping-eval-thread-handoff",
        customer_id=customer.id,
        company_id=company.id,
        active_order_id=order.id,
        channel_type="telegram",
        conversation_id="conv-ping-handoff",
        state=ThreadState.HANDOFF,
        assistant_mode=AssistantMode.ACTIVE,
        last_customer_message_at=datetime.now(UTC) - timedelta(minutes=10),
    )

    task_repo = TaskRepository()
    before = await _count_open_tasks_for_order(order.id)
    await evaluate_pings(task_repo)
    after = await _count_open_tasks_for_order(order.id)
    assert after == before
