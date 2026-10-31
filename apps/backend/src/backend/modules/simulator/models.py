from __future__ import annotations

from tortoise import fields

from src.backend.modules.core.base_model import BaseModel


class SimulatorSession(BaseModel):
    """Isolated sandbox session for testing AI agent.

    Each company user (admin) has one session per company that stores
    test conversation history without affecting real customers.
    """

    id = fields.IntField(primary_key=True)
    company_user: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.CompanyUser",
        related_name="simulator_sessions",
        on_delete=fields.CASCADE,
    )
    messages = fields.JSONField(default=list)
    context = fields.JSONField(default=dict)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta(BaseModel.Meta):
        table = "simulator_sessions"
        schema = "backend"
        unique_together = (("company_user",),)
