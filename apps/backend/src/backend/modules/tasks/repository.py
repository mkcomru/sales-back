"""Task repository with typed creation helpers.

Design: Internal storage uses subject_type + subject_id, but the repository
exposes typed methods (create_order_task) that hide this wiring from callers.
"""

from __future__ import annotations

from datetime import UTC, datetime

from common.models import TaskAutoAction

from src.backend.modules.core.base_repo import BaseRepository
from src.backend.modules.tasks.exceptions import TaskNotFoundError
from src.backend.modules.tasks.models import CompletedByType, Task, TaskSubjectType, TaskType


class TaskRepository(BaseRepository[Task]):
    def __init__(self):
        super().__init__(Task)

    async def get_by_id(self, task_id: int) -> Task:
        """Get task by ID. Raises DoesNotExist if not found."""
        task = await self.model.get_or_none(id=task_id)
        if not task:
            raise TaskNotFoundError(task_id)
        return task

    async def create_order_task(
        self,
        company_id: int,
        order_id: int,
        title: str,
        due_date: datetime,
        type: TaskType,
        *,
        description: str | None = None,
        assignee_id: int | None = None,
        auto_action: str | None = None,
        created_by_id: int | None = None,
        ping_rule_id: int | None = None,
    ) -> Task:
        """Create a task bound to an order. Maps order_id to subject internally."""
        return await self.model.create(
            company_id=company_id,
            subject_type=TaskSubjectType.ORDER,
            subject_id=order_id,
            title=title,
            due_date=due_date,
            type=type,
            description=description,
            assignee_id=assignee_id,
            auto_action=auto_action,
            created_by_id=created_by_id,
            ping_rule_id=ping_rule_id,
        )

    async def get_tasks_for_order(
        self,
        company_id: int,
        order_id: int,
        *,
        include_completed: bool = False,
    ) -> list[Task]:
        """Get tasks for a specific order."""
        query = self.model.filter(
            company_id=company_id,
            subject_type=TaskSubjectType.ORDER,
            subject_id=order_id,
        )
        if not include_completed:
            query = query.filter(completed=False, cancelled_at__isnull=True)
        return await query.order_by("due_date")

    async def get_due_tasks(
        self,
        before: datetime,
        *,
        limit: int = 100,
    ) -> list[Task]:
        """Get pending tasks due before given timestamp. Used by scheduler."""
        return await self.model.filter(
            completed=False,
            cancelled_at__isnull=True,
            due_date__lte=before,
        ).limit(limit)

    async def get_tasks_for_assignee(
        self,
        company_id: int,
        assignee_id: int,
        *,
        include_completed: bool = False,
    ) -> list[Task]:
        """Get tasks assigned to a specific user."""
        query = self.model.filter(company_id=company_id, assignee_id=assignee_id)
        if not include_completed:
            query = query.filter(completed=False, cancelled_at__isnull=True)
        return await query.order_by("due_date")

    async def get_all_company_tasks(
        self,
        company_id: int,
        *,
        include_completed: bool = False,
    ) -> list[Task]:
        """Get all tasks for a company, regardless of assignee."""
        query = self.model.filter(company_id=company_id)
        if not include_completed:
            query = query.filter(completed=False, cancelled_at__isnull=True)
        return await query.order_by("due_date")

    async def complete_task(
        self,
        task_id: int,
        completed_by_type: CompletedByType,
    ) -> Task:
        """Mark task as completed."""
        task = await self.get_by_id(task_id)
        task.completed = True
        task.completed_at = datetime.now(UTC)
        task.completed_by_type = completed_by_type
        task.failure_reason = None
        await task.save()
        return task

    async def cancel_task(self, task_id: int) -> Task:
        """Cancel a task."""
        task = await self.get_by_id(task_id)
        task.cancelled_at = datetime.now(UTC)
        await task.save()
        return task

    async def update_task(self, task_id: int, **updates) -> Task:
        """Update task fields."""
        task = await self.get_by_id(task_id)
        for key, value in updates.items():
            setattr(task, key, value)
        task.updated_at = datetime.now(UTC)
        await task.save()
        return task

    async def record_attempt(self, task_id: int) -> Task:
        """Increment attempt count and update last_attempt_at."""
        task = await self.get_by_id(task_id)
        task.attempt_count += 1
        task.last_attempt_at = datetime.now(UTC)
        await task.save()
        return task

    async def record_failure(self, task_id: int, failure_reason: str) -> Task:
        """Record failure reason (called after record_attempt on failure)."""
        task = await self.get_by_id(task_id)
        task.failure_reason = failure_reason
        await task.save()
        return task

    async def has_ping_since(self, order_id: int, ping_rule_id: int, since: datetime) -> bool:
        """Check if a ping task (pending or completed) exists for this order + rule since a given time.

        Prevents re-scheduling the same ping within the same silence window.
        Cancelled pings don't count — they were explicitly aborted (e.g. by inbound message).
        """
        return await self.model.filter(
            subject_type=TaskSubjectType.ORDER,
            subject_id=order_id,
            ping_rule_id=ping_rule_id,
            cancelled_at__isnull=True,
            created_at__gte=since,
        ).exists()

    async def has_pending_agent_followup(self, order_id: int) -> bool:
        """Check if order has a pending followup reminder created by agent (not auto-ping).

        Only SEND_FOLLOWUP_MESSAGE tasks suppress auto-pings.
        Other auto_action types do not affect the ping chain.
        """
        return await self.model.filter(
            subject_type=TaskSubjectType.ORDER,
            subject_id=order_id,
            type=TaskType.AI_SCHEDULED,
            auto_action=TaskAutoAction.SEND_FOLLOWUP_MESSAGE,
            ping_rule_id__isnull=True,
            completed=False,
            cancelled_at__isnull=True,
        ).exists()

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
        query = self.model.filter(
            subject_type=TaskSubjectType.ORDER,
            subject_id=order_id,
            ping_rule_id__isnull=False,
            completed=False,
            cancelled_at__isnull=True,
        )
        if stage_id is not None:
            query = query.filter(ping_rule__stage_id=stage_id)

        now = datetime.now(UTC)
        count = await query.update(cancelled_at=now)
        return count
