"""PingRule model — stage-based automated follow-up rules."""

from __future__ import annotations

from tortoise import fields

from src.backend.modules.core.base_model import BaseModel
from src.backend.modules.pings.enums import PingContentType

MAX_PINGS_PER_STAGE = 5


class PingRule(BaseModel):
    """Automated follow-up rule tied to a sales funnel stage.

    Each rule defines when and how to ping a silent customer.
    Multiple rules per stage form a chain (ordered by position).
    """

    id = fields.IntField(primary_key=True)
    company: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.Company",
        related_name="ping_rules",
        on_delete=fields.CASCADE,
    )
    stage: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.StageTemplate",
        related_name="ping_rules",
        on_delete=fields.CASCADE,
    )

    position = fields.IntField()
    delay_seconds = fields.IntField()

    condition = fields.JSONField(null=True)

    content_type = fields.CharEnumField(PingContentType, max_length=20)
    static_content = fields.TextField(null=True)
    prompt_override = fields.TextField(null=True)

    is_active = fields.BooleanField(default=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta(BaseModel.Meta):
        table = "ping_rules"
        schema = "backend"
        unique_together = (("stage", "position"),)
        indexes = (("company_id", "stage_id"),)
