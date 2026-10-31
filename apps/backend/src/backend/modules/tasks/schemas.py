"""Task API schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from common.models import TaskAutoAction
from common.models.pagination import PaginatedResponse

from src.backend.modules.tasks.models import CompletedByType, Task, TaskType


class CreateOrderTaskRequest(BaseModel):
    """Request schema for creating an order task."""

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    type: TaskType
    due_date: datetime
    assignee_id: int | None = None
    auto_action: TaskAutoAction | None = None

    @model_validator(mode="after")
    def validate_type_action_consistency(self):
        """Validate that AI_SCHEDULED tasks have auto_action and MANUAL tasks don't."""
        if self.type == TaskType.AI_SCHEDULED and not self.auto_action:
            raise ValueError("AI_SCHEDULED tasks require auto_action")
        if self.type == TaskType.MANUAL and self.auto_action:
            raise ValueError("MANUAL tasks cannot have auto_action")
        return self


class UpdateTaskRequest(BaseModel):
    """Request schema for updating a task."""

    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    due_date: datetime | None = None
    assignee_id: int | None = None


class TaskResponse(BaseModel):
    """Response schema for task."""

    id: int
    company_id: int
    order_id: int
    title: str
    description: str | None
    type: TaskType
    due_date: datetime
    assignee_id: int | None
    auto_action: TaskAutoAction | None
    completed: bool
    completed_at: datetime | None
    completed_by_type: CompletedByType | None
    cancelled_at: datetime | None
    is_overdue: bool
    created_at: datetime
    created_by_id: int | None
    attempt_count: int
    last_attempt_at: datetime | None
    failure_reason: str | None
    ping_rule_id: int | None

    @classmethod
    def from_model(cls, task: Task) -> TaskResponse:
        """Create TaskResponse from Task model."""
        order_id = task.get_order_id() if task.subject_type.value == "order" else 0
        return cls(
            id=task.id,
            company_id=task.company_id,
            order_id=order_id,
            title=task.title,
            description=task.description,
            type=task.type,
            due_date=task.due_date,
            assignee_id=task.assignee_id,
            auto_action=task.auto_action,
            completed=task.completed,
            completed_at=task.completed_at,
            completed_by_type=task.completed_by_type,
            cancelled_at=task.cancelled_at,
            is_overdue=task.is_overdue,
            created_at=task.created_at,
            created_by_id=task.created_by_id,
            attempt_count=task.attempt_count,
            last_attempt_at=task.last_attempt_at,
            failure_reason=task.failure_reason,
            ping_rule_id=task.ping_rule_id,
        )


TaskListResponse = PaginatedResponse[TaskResponse]
