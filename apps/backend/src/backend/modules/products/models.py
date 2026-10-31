from __future__ import annotations

from tortoise import fields

from src.backend.modules.core.base_model import BaseModel


class Product(BaseModel):
    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=255)
    description = fields.TextField()
    attributes = fields.JSONField(default=dict)

    category: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.Category",
        related_name="products",
        on_delete=fields.CASCADE,
        null=True,
    )

    fields: fields.ReverseRelation

    class Meta(BaseModel.Meta):
        table = "products"
        schema = "backend"
