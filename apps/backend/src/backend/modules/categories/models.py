from __future__ import annotations

from tortoise import fields

from src.backend.modules.core.base_model import BaseModel


class Category(BaseModel):
    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=255)
    description = fields.TextField()
    rules = fields.TextField()
    examples = fields.TextField(default="")

    workflow = fields.TextField()
    enabled_tools = fields.JSONField(default=list, description="List of enabled tool names")

    company: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.Company", related_name="categories", on_delete=fields.CASCADE
    )

    fields: fields.ReverseRelation
    products: fields.ReverseRelation

    class Meta:
        table = "categories"
        schema = "backend"
