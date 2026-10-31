"""Tests for TaskRepository."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from common.models import TaskAutoAction

from src.backend.modules.tasks.exceptions import TaskNotFoundError
from src.backend.modules.tasks.models import CompletedByType, TaskType
from src.backend.modules.tasks.repository import TaskRepository


@pytest.mark.asyncio
async def test_create_order_task(
    task_repository: TaskRepository,
    order_with_customer: tuple,
):
    """Test creating an order task."""
    order, _, company = order_with_customer

    task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Test Task",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.MANUAL,
        description="Test description",
    )

    assert task.id is not None
    assert task.title == "Test Task"
    assert task.description == "Test description"
    assert task.type == TaskType.MANUAL
    assert task.company_id == company.id
    assert task.subject_id == order.id
    assert task.get_order_id() == order.id


@pytest.mark.asyncio
async def test_get_by_id_success(
    task_repository: TaskRepository,
    task_for_order: tuple,
):
    """Test getting task by ID."""
    task, _, _ = task_for_order

    result = await task_repository.get_by_id(task.id)

    assert result.id == task.id
    assert result.title == task.title


@pytest.mark.asyncio
async def test_get_by_id_not_found(task_repository: TaskRepository):
    """Test getting non-existent task raises error."""
    with pytest.raises(TaskNotFoundError):
        await task_repository.get_by_id(99999)


@pytest.mark.asyncio
async def test_get_tasks_for_order(
    task_repository: TaskRepository,
    order_with_customer: tuple,
):
    """Test getting tasks for an order."""
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

    tasks = await task_repository.get_tasks_for_order(
        company_id=company.id,
        order_id=order.id,
    )

    assert len(tasks) == 2
    assert tasks[0].id == task1.id
    assert tasks[1].id == task2.id


@pytest.mark.asyncio
async def test_get_tasks_for_order_excludes_completed(
    task_repository: TaskRepository,
    completed_task: tuple,
):
    """Test that get_tasks_for_order excludes completed tasks by default."""
    task, order, company = completed_task

    tasks = await task_repository.get_tasks_for_order(
        company_id=company.id,
        order_id=order.id,
        include_completed=False,
    )

    assert len(tasks) == 0


@pytest.mark.asyncio
async def test_get_tasks_for_order_includes_completed(
    task_repository: TaskRepository,
    completed_task: tuple,
):
    """Test that get_tasks_for_order includes completed tasks when requested."""
    task, order, company = completed_task

    tasks = await task_repository.get_tasks_for_order(
        company_id=company.id,
        order_id=order.id,
        include_completed=True,
    )

    assert len(tasks) == 1
    assert tasks[0].id == task.id


@pytest.mark.asyncio
async def test_get_due_tasks(
    task_repository: TaskRepository,
    order_with_customer: tuple,
):
    """Test getting due tasks."""
    order, _, company = order_with_customer

    due_task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Due Task",
        due_date=datetime.now(UTC) - timedelta(hours=1),
        type=TaskType.AI_SCHEDULED,
        auto_action=TaskAutoAction.SEND_FOLLOWUP_MESSAGE.value,
    )

    _future_task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Future Task",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.MANUAL,
    )

    due_tasks = await task_repository.get_due_tasks(before=datetime.now(UTC))

    assert len(due_tasks) == 1
    assert due_tasks[0].id == due_task.id


@pytest.mark.asyncio
async def test_get_due_tasks_excludes_completed(
    task_repository: TaskRepository,
    completed_task: tuple,
):
    """Test that get_due_tasks excludes completed tasks."""
    task, _, _ = completed_task

    due_tasks = await task_repository.get_due_tasks(before=datetime.now(UTC))

    assert len([t for t in due_tasks if t.id == task.id]) == 0


@pytest.mark.asyncio
async def test_get_tasks_for_assignee(
    task_repository: TaskRepository,
    order_with_customer: tuple,
    assignee_user,
):
    """Test getting tasks for an assignee."""
    order, _, company = order_with_customer

    assigned_task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Assigned Task",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.MANUAL,
        assignee_id=assignee_user.id,
    )

    _unassigned_task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Unassigned Task",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.MANUAL,
    )

    tasks = await task_repository.get_tasks_for_assignee(
        company_id=company.id,
        assignee_id=assignee_user.id,
    )

    assert len(tasks) == 1
    assert tasks[0].id == assigned_task.id


@pytest.mark.asyncio
async def test_complete_task(
    task_repository: TaskRepository,
    task_for_order: tuple,
):
    """Test completing a task."""
    task, _, _ = task_for_order

    result = await task_repository.complete_task(task.id, CompletedByType.USER)

    assert result.completed is True
    assert result.completed_at is not None
    assert result.completed_by_type == CompletedByType.USER
    assert result.failure_reason is None


@pytest.mark.asyncio
async def test_cancel_task(
    task_repository: TaskRepository,
    task_for_order: tuple,
):
    """Test cancelling a task."""
    task, _, _ = task_for_order

    result = await task_repository.cancel_task(task.id)

    assert result.cancelled_at is not None
    assert result.completed is False


@pytest.mark.asyncio
async def test_update_task(
    task_repository: TaskRepository,
    task_for_order: tuple,
):
    """Test updating a task."""
    task, _, _ = task_for_order

    result = await task_repository.update_task(
        task.id,
        title="Updated Title",
        description="Updated description",
    )

    assert result.title == "Updated Title"
    assert result.description == "Updated description"


@pytest.mark.asyncio
async def test_record_attempt(
    task_repository: TaskRepository,
    ai_task_for_order: tuple,
):
    """Test recording an attempt."""
    task, _, _ = ai_task_for_order

    initial_count = task.attempt_count
    result = await task_repository.record_attempt(task.id)

    assert result.attempt_count == initial_count + 1
    assert result.last_attempt_at is not None


@pytest.mark.asyncio
async def test_record_failure(
    task_repository: TaskRepository,
    ai_task_for_order: tuple,
):
    """Test recording a failure."""
    task, _, _ = ai_task_for_order

    result = await task_repository.record_failure(task.id, "Test failure reason")

    assert result.failure_reason == "Test failure reason"


@pytest.mark.asyncio
async def test_get_order_id_success(
    task_repository: TaskRepository,
    order_with_customer: tuple,
):
    """Test that get_order_id returns order_id for ORDER tasks."""
    order, _, company = order_with_customer

    task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Test Task",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.MANUAL,
    )

    assert task.get_order_id() == order.id
