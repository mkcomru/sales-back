"""Order models for deal/order management."""

from __future__ import annotations

from enum import Enum

from tortoise import fields

from src.backend.modules.billing.models import BillingStatus
from src.backend.modules.core.base_model import BaseModel


class OrderResult(str, Enum):
    """Order closure result."""

    WON = "won"
    LOST = "lost"


class OrderLogType(str, Enum):
    """Order activity log types."""

    ORDER_CREATED = "order_created"
    STAGE_CHANGE = "stage_change"
    ASSIGNEE_CHANGE = "assignee_change"
    FIELD_CHANGE = "field_change"
    COMMENT = "comment"
    TASK_CREATED = "task_created"
    TASK_COMPLETED = "task_completed"


class Order(BaseModel):
    """Order/deal entity representing a business transaction."""

    id = fields.IntField(primary_key=True)
    order_number = fields.IntField()
    name = fields.CharField(max_length=255, null=True)

    customer: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.Customer",
        related_name="orders",
        on_delete=fields.CASCADE,
    )
    company: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.Company",
        related_name="orders",
        on_delete=fields.CASCADE,
    )
    assignee: fields.ForeignKeyNullableRelation = fields.ForeignKeyField(
        "models.CompanyUser",
        related_name="assigned_orders",
        on_delete=fields.SET_NULL,
        null=True,
    )
    stage: fields.ForeignKeyNullableRelation = fields.ForeignKeyField(
        "models.StageTemplate",
        related_name="orders",
        on_delete=fields.SET_NULL,
        null=True,
    )
    frozen = fields.BooleanField(default=False)

    order_fields = fields.JSONField(default=dict)
    extra_fields = fields.JSONField(default=dict)
    utm_data = fields.JSONField(null=True)
    initial_channel = fields.CharField(max_length=50, null=True)
    result = fields.CharEnumField(OrderResult, max_length=10, null=True)

    billing_status = fields.CharEnumField(BillingStatus, max_length=20, default=BillingStatus.ACTIVE)
    charged_at = fields.DatetimeField(null=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    closed_at = fields.DatetimeField(null=True)

    threads: fields.ReverseRelation
    logs: fields.ReverseRelation

    class Meta(BaseModel.Meta):
        table = "orders"
        schema = "backend"
        unique_together = (("company", "order_number"),)
        indexes = (
            ("customer_id", "closed_at"),
            ("company_id", "stage_id", "frozen", "closed_at"),
            ("assignee_id",),
        )


class OrderLog(BaseModel):
    """Activity log for order changes and comments."""

    id = fields.IntField(primary_key=True)
    order: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.Order",
        related_name="logs",
        on_delete=fields.CASCADE,
    )
    type = fields.CharEnumField(OrderLogType, max_length=20)
    author: fields.ForeignKeyNullableRelation = fields.ForeignKeyField(
        "models.CompanyUser",
        related_name="order_logs",
        on_delete=fields.SET_NULL,
        null=True,
    )
    data = fields.JSONField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta(BaseModel.Meta):
        table = "order_logs"
        schema = "backend"
        indexes = (("order_id", "created_at"),)
