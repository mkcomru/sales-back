from __future__ import annotations

from tortoise import fields

from src.backend.modules.core.base_model import BaseModel


class RefreshToken(BaseModel):
    id = fields.IntField(primary_key=True)
    user: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.User", related_name="refresh_tokens", on_delete=fields.CASCADE
    )
    jti = fields.CharField(max_length=64, unique=True, index=True)
    expires_at = fields.DatetimeField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "refresh_tokens"
        schema = "backend"
