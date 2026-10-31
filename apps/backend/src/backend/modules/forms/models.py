"""Form models for web form capture."""

import uuid

from tortoise import fields

from src.backend.modules.core.base_model import BaseModel


def generate_public_id() -> str:
    """Generate a random public ID for forms."""
    return uuid.uuid4().hex[:12]


class FormTemplate(BaseModel):
    """Form template for web form capture."""

    id = fields.IntField(primary_key=True)
    public_id = fields.CharField(max_length=12, unique=True, default=generate_public_id)
    company: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.Company", related_name="form_templates", on_delete=fields.CASCADE
    )
    name = fields.CharField(max_length=255)
    api_key_hash = fields.CharField(max_length=64, unique=True, null=True)
    contact_field: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.Field", related_name="contact_for_forms", on_delete=fields.RESTRICT
    )
    enabled = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    template_fields: fields.ReverseRelation
    submissions: fields.ReverseRelation

    class Meta(BaseModel.Meta):
        table = "form_templates"
        schema = "backend"


class FormTemplateField(BaseModel):
    """M:N relationship between FormTemplate and Field."""

    id = fields.IntField(primary_key=True)
    form_template: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.FormTemplate", related_name="template_fields", on_delete=fields.CASCADE
    )
    field: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.Field", related_name="form_template_fields", on_delete=fields.CASCADE
    )
    position = fields.IntField(default=0)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta(BaseModel.Meta):
        table = "form_template_fields"
        schema = "backend"
        unique_together = (("form_template", "field"),)


class FormSubmission(BaseModel):
    """Audit table for form submissions."""

    id = fields.IntField(primary_key=True)
    form_template: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.FormTemplate", related_name="submissions", on_delete=fields.CASCADE
    )
    customer: fields.ForeignKeyNullableRelation = fields.ForeignKeyField(
        "models.Customer", related_name="form_submissions", on_delete=fields.SET_NULL, null=True
    )
    order: fields.ForeignKeyNullableRelation = fields.ForeignKeyField(
        "models.Order", related_name="form_submissions", on_delete=fields.SET_NULL, null=True
    )
    raw_fields = fields.JSONField()
    utm_data = fields.JSONField(null=True)
    ip_address = fields.CharField(max_length=45, null=True)
    user_agent = fields.CharField(max_length=512, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta(BaseModel.Meta):
        table = "form_submissions"
        schema = "backend"
        indexes = (("form_template_id", "created_at"),)
