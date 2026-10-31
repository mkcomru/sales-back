from __future__ import annotations

from tortoise import fields

from src.backend.modules.core.base_model import BaseModel


class PromptAddon(BaseModel):
    """Prompt addon model."""

    id = fields.IntField(primary_key=True)
    company: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.Company",
        related_name="prompt_addons",
        on_delete=fields.CASCADE,
    )
    name = fields.CharField(max_length=255)
    qualification_workflow = fields.TextField()
    qualification_examples = fields.TextField()

    connectors: fields.ReverseRelation

    class Meta(BaseModel.Meta):
        table = "prompt_addons"
        schema = "backend"
