"""Tests for TaskService."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from common.models import TaskAutoAction

from src.backend.modules.orders.models import OrderLog, OrderLogType
from src.backend.modules.tasks.exceptions import OrderNotFoundError, TaskNotFoundError
from src.backend.modules.tasks.models import CompletedByType, TaskType
from src.backend.modules.tasks.schemas import CreateOrderTaskRequest
from src.backend.modules.tasks.service import TaskService


@pytest.mark.asyncio
async def test_create_order_task_success(
    task_service: TaskService,
    order_with_customer: tuple,
):
    """Test successful task creation."""
    order, _, company = order_with_customer

    data = CreateOrderTaskRequest(
        title="Test Task",
        description="Test description",
        type=TaskType.MANUAL,
        due_date=datetime.now(UTC) + timedelta(days=1),
    )

    task = await task_service.create_order_task(
        company_id=company.id,
        order_id=order.id,
        data=data,
    )

    assert task.id is not None
    assert task.title == "Test Task"
    assert task.description == "Test description"
    assert task.type == TaskType.MANUAL
    assert task.company_id == company.id
    assert task.subject_id == order.id
    assert task.completed is False
    assert task.cancelled_at is None

    logs = await OrderLog.filter(order_id=order.id, type=OrderLogType.TASK_CREATED).all()
    assert len(logs) == 1
    assert logs[0].data["task_id"] == task.id
    assert logs[0].data["title"] == "Test Task"


@pytest.mark.asyncio
async def test_create_task_validates_order_exists(
    task_service: TaskService,
    company,
):
    """Test that task creation validates order exists."""
    data = CreateOrderTaskRequest(
        title="Test Task",
        type=TaskType.MANUAL,
        due_date=datetime.now(UTC) + timedelta(days=1),
    )

    with pytest.raises(OrderNotFoundError):
        await task_service.create_order_task(
            company_id=company.id,
            order_id=99999,
            data=data,
        )


@pytest.mark.asyncio
async def test_create_ai_task_requires_auto_action(
    task_service: TaskService,
    order_with_customer: tuple,
):
    """Test that AI_SCHEDULED tasks require auto_action."""
    order, _, company = order_with_customer

    with pytest.raises(ValidationError):
        CreateOrderTaskRequest(
            title="AI Task",
            type=TaskType.AI_SCHEDULED,
            due_date=datetime.now(UTC) + timedelta(days=1),
            auto_action=None,
        )


@pytest.mark.asyncio
async def test_create_manual_task_rejects_auto_action(
    task_service: TaskService,
    order_with_customer: tuple,
):
    """Test that MANUAL tasks cannot have auto_action."""
    order, _, company = order_with_customer

    with pytest.raises(ValidationError):
        CreateOrderTaskRequest(
            title="Manual Task",
            type=TaskType.MANUAL,
            due_date=datetime.now(UTC) + timedelta(days=1),
            auto_action=TaskAutoAction.SEND_FOLLOWUP_MESSAGE,
        )


@pytest.mark.asyncio
async def test_create_task_validates_due_date_in_future(
    task_service: TaskService,
    order_with_customer: tuple,
):
    """Test that due_date must be in the future."""
    order, _, company = order_with_customer

    data = CreateOrderTaskRequest(
        title="Past Task",
        type=TaskType.MANUAL,
        due_date=datetime.now(UTC) - timedelta(days=1),
    )

    with pytest.raises(ValueError, match="due_date must be in the future"):
        await task_service.create_order_task(
            company_id=company.id,
            order_id=order.id,
            data=data,
        )


@pytest.mark.asyncio
async def test_complete_task_idempotent(
    task_service: TaskService,
    completed_task: tuple,
):
    """Test that completing an already completed task is idempotent."""
    task, order, company = completed_task

    result = await task_service.complete_task(company_id=company.id, task_id=task.id)

    assert result.completed is True
    assert result.completed_at is not None
    assert result.completed_by_type == CompletedByType.USER


@pytest.mark.asyncio
async def test_complete_task_logs_to_order(
    task_service: TaskService,
    task_for_order: tuple,
):
    """Test that completing a task logs to order history."""
    task, order, company = task_for_order

    await task_service.complete_task(company_id=company.id, task_id=task.id)

    logs = await OrderLog.filter(order_id=order.id, type=OrderLogType.TASK_COMPLETED).all()
    assert len(logs) == 1
    assert logs[0].data["task_id"] == task.id
    assert logs[0].data["completed_by_type"] == "user"


@pytest.mark.asyncio
async def test_complete_task_validates_company_id(
    task_service: TaskService,
    task_for_order: tuple,
    company,
):
    """Test that completing a task validates company_id."""
    task, _, _ = task_for_order

    with pytest.raises(TaskNotFoundError):
        await task_service.complete_task(company_id=company.id + 999, task_id=task.id)


@pytest.mark.asyncio
async def test_get_order_with_tasks(
    task_service: TaskService,
    order_with_customer: tuple,
    task_repository,
):
    """Test getting order with its tasks."""
    order, _, company = order_with_customer

    task1 = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Task 1",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.MANUAL,
    )

    task2 = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Task 2",
        due_date=datetime.now(UTC) + timedelta(days=2),
        type=TaskType.MANUAL,
    )

    result_order, tasks = await task_service.get_order_with_tasks(
        company_id=company.id,
        order_id=order.id,
    )

    assert result_order.id == order.id
    assert len(tasks) == 2
    assert tasks[0].id == task1.id
    assert tasks[1].id == task2.id


@pytest.mark.asyncio
async def test_get_order_with_tasks_validates_order_exists(
    task_service: TaskService,
    company,
):
    """Test that get_order_with_tasks validates order exists."""
    with pytest.raises(OrderNotFoundError):
        await task_service.get_order_with_tasks(
            company_id=company.id,
            order_id=99999,
        )
