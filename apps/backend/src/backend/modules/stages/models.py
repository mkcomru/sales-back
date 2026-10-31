"""Stage template models."""

from __future__ import annotations

from tortoise import fields

from src.backend.modules.core.base_model import BaseModel
from src.backend.modules.orders.models import OrderResult


class StageTemplate(BaseModel):
    """Stage template for custom sales funnel stages."""

    id = fields.IntField(primary_key=True)
    company: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.Company",
        related_name="stage_templates",
        on_delete=fields.CASCADE,
    )

    name = fields.CharField(max_length=255)
    color = fields.CharField(max_length=7, null=True)
    position = fields.IntField()

    is_final = fields.BooleanField(default=False)
    result = fields.CharEnumField(OrderResult, max_length=10, null=True)
    auto_close = fields.BooleanField(default=False)

    transition_condition = fields.JSONField(null=True)

    is_system = fields.BooleanField(default=False)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    orders: fields.ReverseRelation

    class Meta(BaseModel.Meta):
        table = "stage_templates"
        schema = "backend"
        unique_together = (("company", "position"),)
        indexes = (("company_id", "position"),)
