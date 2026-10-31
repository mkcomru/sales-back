"""Task model with polymorphic subject binding.

Design principles:
- Data structure is unified and flexible (subject_type + subject_id pattern)
- External interfaces are strict and descriptive (typed helpers, explicit accessors)
- Fail-fast validation: required fields must be present and valid at creation
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from tortoise import fields

from common.models import TaskAutoAction

from src.backend.modules.core.base_model import BaseModel


class TaskSubjectType(str, Enum):
    """Task subject types."""

    ORDER = "order"


class TaskType(str, Enum):
    """Task types."""

    MANUAL = "manual"
    AI_SCHEDULED = "ai_scheduled"


class CompletedByType(str, Enum):
    """Who completed the task."""

    USER = "user"
    SYSTEM = "system"


class Task(BaseModel):
    """Unified task entity with polymorphic subject binding.

    Subject binding uses subject_type + subject_id internally, but external
    APIs expose typed helpers (create_order_task) and accessors (get_order_id).
    Higher-level services are responsible for resolving IDs to model instances.

    Lifecycle: Tasks are deleted when their subject is deleted (CASCADE).
    For order tasks: if order is deleted, its tasks are deleted too.
    """

    id = fields.IntField(primary_key=True)
    company: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.Company",
        related_name="tasks",
        on_delete=fields.CASCADE,
    )

    subject_type = fields.CharEnumField(TaskSubjectType, max_length=20)
    subject_id = fields.IntField()

    title = fields.CharField(max_length=255)
    description = fields.TextField(null=True)
    type = fields.CharEnumField(TaskType, max_length=20)
    due_date = fields.DatetimeField()

    assignee: fields.ForeignKeyNullableRelation = fields.ForeignKeyField(
        "models.CompanyUser",
        related_name="assigned_tasks",
        on_delete=fields.SET_NULL,
        null=True,
    )

    auto_action = fields.CharEnumField(TaskAutoAction, max_length=50, null=True)
    ping_rule: fields.ForeignKeyNullableRelation = fields.ForeignKeyField(
        "models.PingRule",
        related_name="tasks",
        on_delete=fields.SET_NULL,
        null=True,
    )

    completed = fields.BooleanField(default=False)
    completed_at = fields.DatetimeField(null=True)
    completed_by_type = fields.CharEnumField(CompletedByType, max_length=20, null=True)
    cancelled_at = fields.DatetimeField(null=True)

    attempt_count = fields.IntField(default=0)
    last_attempt_at = fields.DatetimeField(null=True)
    failure_reason = fields.TextField(null=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    created_by: fields.ForeignKeyNullableRelation = fields.ForeignKeyField(
        "models.CompanyUser",
        related_name="created_tasks",
        on_delete=fields.SET_NULL,
        null=True,
    )
    updated_at = fields.DatetimeField(auto_now=True)

    def get_order_id(self) -> int:
        """Returns order_id. Raises ValueError if subject_type != ORDER."""
        if self.subject_type != TaskSubjectType.ORDER:
            raise ValueError(f"Task {self.id} subject is {self.subject_type}, not ORDER")
        return self.subject_id

    @property
    def is_overdue(self) -> bool:
        """Check if task is overdue."""
        if self.completed or self.cancelled_at is not None:
            return False
        normalized_due = (
            self.due_date.astimezone(UTC) if self.due_date.tzinfo is not None else self.due_date.replace(tzinfo=UTC)
        )
        return datetime.now(UTC) > normalized_due

    class Meta(BaseModel.Meta):
        table = "tasks"
        schema = "backend"
        indexes = (
            ("company_id", "subject_type", "subject_id"),
            ("due_date",),
            ("company_id", "assignee_id"),
        )
