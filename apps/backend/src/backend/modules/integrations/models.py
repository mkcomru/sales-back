from __future__ import annotations

from tortoise import fields

from src.backend.modules.core.base_model import BaseModel


class Integration(BaseModel):
    id = fields.IntField(primary_key=True)
    company = fields.ForeignKeyField("models.Company", related_name="integrations")
    provider_type = fields.CharField(max_length=64)
    credentials_encrypted = fields.TextField(default="")
    credentials_dek = fields.TextField(default="")
    config = fields.JSONField(default=dict)
    enabled_capabilities = fields.JSONField(default=list)
    enabled = fields.BooleanField(default=True)

    class Meta(BaseModel.Meta):
        table = "integrations"
        schema = "backend"
        unique_together = [("company", "provider_type")]
