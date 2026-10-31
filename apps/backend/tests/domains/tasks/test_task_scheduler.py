"""Tests for TaskSchedulerWorker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from common.models import TaskAutoAction

from src.backend.modules.tasks.models import CompletedByType, TaskType
from src.backend.modules.tasks.repository import TaskRepository
from src.backend.workers.task_executor import TaskExecutor
from src.backend.workers.task_scheduler import TaskSchedulerWorker


def _make_worker(task_repo: TaskRepository, executor: MagicMock) -> TaskSchedulerWorker:
    return TaskSchedulerWorker(
        task_repo=task_repo,
        executor=executor,
        sales_agent_client=MagicMock(),
    )


@pytest.mark.asyncio
async def test_processes_due_tasks(
    order_with_customer: tuple,
    task_repository: TaskRepository,
):
    """Test that scheduler processes due tasks."""
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
        type=TaskType.AI_SCHEDULED,
        auto_action=TaskAutoAction.SEND_FOLLOWUP_MESSAGE.value,
    )

    executor = MagicMock(spec=TaskExecutor)
    executor.execute_ai_task = AsyncMock()

    scheduler = _make_worker(task_repository, executor)

    await scheduler.tick()

    executor.execute_ai_task.assert_called_once()
    call_args = executor.execute_ai_task.call_args[0][0]
    assert call_args.id == due_task.id


@pytest.mark.asyncio
async def test_skips_completed_tasks(
    order_with_customer: tuple,
    task_repository: TaskRepository,
):
    """Test that scheduler skips completed tasks."""
    order, _, company = order_with_customer

    completed_task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Completed Task",
        due_date=datetime.now(UTC) - timedelta(hours=1),
        type=TaskType.AI_SCHEDULED,
        auto_action=TaskAutoAction.SEND_FOLLOWUP_MESSAGE.value,
    )

    await task_repository.complete_task(completed_task.id, CompletedByType.SYSTEM)

    executor = MagicMock(spec=TaskExecutor)
    executor.execute_ai_task = AsyncMock()

    scheduler = _make_worker(task_repository, executor)

    await scheduler.tick()

    executor.execute_ai_task.assert_not_called()


@pytest.mark.asyncio
async def test_skips_cancelled_tasks(
    order_with_customer: tuple,
    task_repository: TaskRepository,
):
    """Test that scheduler skips cancelled tasks."""
    order, _, company = order_with_customer

    cancelled_task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Cancelled Task",
        due_date=datetime.now(UTC) - timedelta(hours=1),
        type=TaskType.AI_SCHEDULED,
        auto_action=TaskAutoAction.SEND_FOLLOWUP_MESSAGE.value,
    )

    await task_repository.cancel_task(cancelled_task.id)

    executor = MagicMock(spec=TaskExecutor)
    executor.execute_ai_task = AsyncMock()

    scheduler = _make_worker(task_repository, executor)

    await scheduler.tick()

    executor.execute_ai_task.assert_not_called()


@pytest.mark.asyncio
async def test_skips_manual_tasks(
    order_with_customer: tuple,
    task_repository: TaskRepository,
):
    """Test that scheduler skips manual tasks."""
    order, _, company = order_with_customer

    _manual_task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Manual Task",
        due_date=datetime.now(UTC) - timedelta(hours=1),
        type=TaskType.MANUAL,
    )

    executor = MagicMock(spec=TaskExecutor)
    executor.execute_ai_task = AsyncMock()

    scheduler = _make_worker(task_repository, executor)

    await scheduler.tick()

    executor.execute_ai_task.assert_not_called()


@pytest.mark.asyncio
async def test_handles_execution_failure_gracefully(
    order_with_customer: tuple,
    task_repository: TaskRepository,
):
    """Test that scheduler handles execution failures gracefully."""
    order, _, company = order_with_customer

    due_task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Due Task",
        due_date=datetime.now(UTC) - timedelta(hours=1),
        type=TaskType.AI_SCHEDULED,
        auto_action=TaskAutoAction.SEND_FOLLOWUP_MESSAGE.value,
    )

    executor = MagicMock(spec=TaskExecutor)

    async def mock_execute_with_error_handling(task):
        await task_repository.record_attempt(task.id)
        await task_repository.record_failure(task.id, "Execution failed")

    executor.execute_ai_task = AsyncMock(side_effect=mock_execute_with_error_handling)

    scheduler = _make_worker(task_repository, executor)

    await scheduler.tick()

    executor.execute_ai_task.assert_called_once()

    fresh_task = await task_repository.get_by_id(due_task.id)
    assert fresh_task.completed is False
    assert fresh_task.failure_reason == "Execution failed"


@pytest.mark.asyncio
async def test_at_least_once_delivery(
    order_with_customer: tuple,
    task_repository: TaskRepository,
):
    """Test that scheduler re-fetches tasks to ensure at-least-once delivery."""
    order, _, company = order_with_customer

    due_task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Due Task",
        due_date=datetime.now(UTC) - timedelta(hours=1),
        type=TaskType.AI_SCHEDULED,
        auto_action=TaskAutoAction.SEND_FOLLOWUP_MESSAGE.value,
    )

    executor = MagicMock(spec=TaskExecutor)
    executor.execute_ai_task = AsyncMock()

    scheduler = _make_worker(task_repository, executor)

    await scheduler.tick()

    executor.execute_ai_task.assert_called_once()
    call_args = executor.execute_ai_task.call_args[0][0]
    assert call_args.id == due_task.id

    fresh_task = await task_repository.get_by_id(due_task.id)
    assert fresh_task.id == call_args.id
