"""Task service orchestrating validation, business logic, and cross-module interactions.

Design principles:
- Service methods accept explicit IDs and resolve to model instances when needed
- Validation is fail-fast: invalid input raises immediately
- Order events are logged for traceability
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog

from src.backend.modules.orders.service import OrderService
from src.backend.modules.tasks.exceptions import OrderNotFoundError, TaskNotFoundError
from src.backend.modules.tasks.models import CompletedByType, Task, TaskSubjectType, TaskType
from src.backend.modules.tasks.repository import TaskRepository
from src.backend.modules.tasks.schemas import CreateOrderTaskRequest

log = structlog.get_logger(__name__)


class TaskService:
    """Service for managing tasks."""

    def __init__(self, repo: TaskRepository, order_service: OrderService):
        self.repo = repo
        self.order_service = order_service

    async def create_order_task(
        self,
        company_id: int,
        order_id: int,
        data: CreateOrderTaskRequest,
        created_by_id: int | None = None,
    ) -> Task:
        """Create a task bound to an order."""
        order = await self.order_service.get_order(company_id, order_id)
        if not order:
            raise OrderNotFoundError(order_id)

        if data.type == TaskType.AI_SCHEDULED and not data.auto_action:
            raise ValueError("AI_SCHEDULED tasks require auto_action")
        if data.type == TaskType.MANUAL and data.auto_action:
            raise ValueError("MANUAL tasks cannot have auto_action")

        if data.due_date.replace(tzinfo=UTC) <= datetime.now(UTC):
            raise ValueError("due_date must be in the future")

        task = await self.repo.create_order_task(
            company_id=company_id,
            order_id=order_id,
            title=data.title,
            due_date=data.due_date,
            type=data.type,
            description=data.description,
            assignee_id=data.assignee_id,
            auto_action=data.auto_action.value if data.auto_action else None,
            created_by_id=created_by_id,
        )

        await self.order_service.log_event(
            order_id=order_id,
            event_type="task_created",
            data={"task_id": task.id, "title": task.title},
        )

        return task

    async def get_order_task(self, company_id: int, order_id: int, task_id: int) -> Task:
        """Return task if it belongs to company and order. Raises TaskNotFoundError otherwise."""
        task = await self.repo.get_by_id(task_id)
        if task.company_id != company_id:
            raise TaskNotFoundError(task_id)
        if task.subject_type != TaskSubjectType.ORDER or task.subject_id != order_id:
            raise TaskNotFoundError(task_id)
        return task

    async def complete_task(
        self,
        company_id: int,
        task_id: int,
    ) -> Task:
        """Complete task by user. For system completion, use repository directly."""
        task = await self.repo.get_by_id(task_id)

        if task.company_id != company_id:
            raise TaskNotFoundError(task_id)

        if task.completed:
            return task

        task = await self.repo.complete_task(task_id, completed_by_type=CompletedByType.USER)

        if task.subject_type == TaskSubjectType.ORDER:
            await self.order_service.log_event(
                order_id=task.get_order_id(),
                event_type="task_completed",
                data={"task_id": task.id, "completed_by_type": "user"},
            )

        return task

    async def cancel_pending_pings_for_order(
        self,
        order_id: int,
        *,
        stage_id: int | None = None,
    ) -> int:
        """Cancel all pending auto-ping tasks for an order.

        If stage_id is provided, only cancels pings for that stage's rules.
        Returns the number of cancelled tasks.
        """
        return await self.repo.cancel_pending_pings_for_order(order_id, stage_id=stage_id)

    async def get_order_with_tasks(
        self,
        company_id: int,
        order_id: int,
    ) -> tuple:
        """Higher-level method returning resolved Order + its tasks."""
        order = await self.order_service.get_order(company_id, order_id)
        if not order:
            raise OrderNotFoundError(order_id)
        tasks = await self.repo.get_tasks_for_order(company_id, order_id)
        return order, tasks
