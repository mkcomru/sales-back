from __future__ import annotations

from enum import Enum

from tortoise import fields

from src.backend.modules.core.base_model import BaseModel


class AnswerType(str, Enum):
    """Answer types."""

    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ENUM = "enum"


class FieldLevel(str, Enum):
    """Field level - determines where values are stored."""

    CUSTOMER = "customer"
    ORDER = "order"


class Field(BaseModel):
    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=255)
    question = fields.TextField()
    answer_type = fields.CharEnumField(AnswerType, max_length=255)
    required = fields.BooleanField(default=False)
    display_name = fields.CharField(max_length=255, null=True)
    level = fields.CharEnumField(FieldLevel, max_length=20, default=FieldLevel.CUSTOMER)
    is_system = fields.BooleanField(default=False)

    company: fields.ForeignKeyRelation = fields.ForeignKeyField("models.Company", related_name="fields")
    category: fields.ForeignKeyRelation = fields.ForeignKeyField("models.Category", related_name="fields", null=True)
    product: fields.ForeignKeyRelation = fields.ForeignKeyField("models.Product", related_name="fields", null=True)

    options: fields.ReverseRelation

    class Meta(BaseModel.Meta):
        table = "fields"
        schema = "backend"


class FieldOption(BaseModel):
    # AICODE-NOTE: Options for ENUM fields. `order` controls UI order
    # independent of `value` and supports reordering.
    id = fields.IntField(primary_key=True)
    field: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.Field",
        related_name="options",
        on_delete=fields.CASCADE,
    )
    value = fields.CharField(max_length=255)
    order = fields.IntField(default=0)

    class Meta(BaseModel.Meta):
        table = "field_options"
        unique_together = (("field", "value"), ("field", "order"))
        schema = "backend"
