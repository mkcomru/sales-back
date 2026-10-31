"""Billing models for lead balance tracking."""

from __future__ import annotations

from enum import Enum

from tortoise import fields

from src.backend.modules.core.base_model import BaseModel


class BillingStatus(str, Enum):
    """Order billing status."""

    ACTIVE = "active"
    BILLING_HOLD = "billing_hold"


class OperationType(str, Enum):
    """Balance ledger operation types."""

    TOP_UP = "top_up"
    CHARGE = "charge"


class InitiatedBy(str, Enum):
    """Who initiated the balance operation."""

    SYSTEM = "system"
    OPERATOR = "operator"
    ADMIN = "admin"


class CompanyBalance(BaseModel):
    """Company lead balance. One balance per company (1:1 relationship)."""

    id = fields.IntField(primary_key=True)
    company: fields.OneToOneRelation = fields.OneToOneField(
        "models.Company",
        related_name="balance",
        on_delete=fields.CASCADE,
    )
    balance = fields.IntField(default=0)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta(BaseModel.Meta):
        table = "company_balances"
        schema = "backend"


class BalanceLedger(BaseModel):
    """Audit ledger for balance operations."""

    id = fields.IntField(primary_key=True)
    company: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.Company",
        related_name="ledger_entries",
        on_delete=fields.CASCADE,
    )
    operation_type = fields.CharEnumField(OperationType, max_length=20)
    amount = fields.IntField()
    timestamp = fields.DatetimeField(auto_now_add=True)
    initiated_by = fields.CharEnumField(InitiatedBy, max_length=20)
    operator: fields.ForeignKeyNullableRelation = fields.ForeignKeyField(
        "models.CompanyUser",
        related_name="ledger_operations",
        on_delete=fields.SET_NULL,
        null=True,
    )
    comment = fields.TextField(null=True)
    order: fields.ForeignKeyNullableRelation = fields.ForeignKeyField(
        "models.Order",
        related_name="ledger_charges",
        on_delete=fields.SET_NULL,
        null=True,
    )
    channel_type = fields.CharField(max_length=50, null=True)
    conversation_id = fields.CharField(max_length=255, null=True)

    class Meta(BaseModel.Meta):
        table = "balance_ledger"
        schema = "backend"
        indexes = (
            ("company_id", "timestamp"),
            ("order_id",),
        )
