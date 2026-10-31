from __future__ import annotations

from tortoise import fields

from src.backend.modules.core.base_model import BaseModel


class Company(BaseModel):
    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=255)
    description = fields.TextField()
    rules = fields.TextField()
    tone_of_voice = fields.TextField()
    assistant_name = fields.CharField(max_length=255)

    qualification_workflow = fields.TextField()
    qualification_examples = fields.TextField()

    collection_name = fields.CharField(
        max_length=255,
        description="The name of the collection in qdrant",
    )

    stages_config = fields.JSONField(default=list)
    category_rules = fields.JSONField(default=list)
    enabled_tools = fields.JSONField(default=list, description="List of enabled tool names")
    crm_forward_metadata_keys = fields.JSONField(default=list)
    crm_default_stage_id = fields.CharField(max_length=50, default="PROCESSED")
    crm_manager_attention_stage_id = fields.CharField(max_length=50, null=True, default=None)

    fields: fields.ReverseRelation
    categories: fields.ReverseRelation
    faqs: fields.ReverseRelation
    connectors: fields.ReverseRelation
    customers: fields.ReverseRelation
    threads: fields.ReverseRelation
    stage_templates: fields.ReverseRelation
    prompt_addons: fields.ReverseRelation
    integrations: fields.ReverseRelation

    class Meta(BaseModel.Meta):
        table = "companies"
        schema = "backend"


class FAQ(BaseModel):
    id = fields.IntField(primary_key=True)
    company: fields.ForeignKeyRelation = fields.ForeignKeyField("models.Company", related_name="faqs")
    category = fields.CharField(max_length=255)
    question = fields.TextField()
    answer = fields.TextField()
    keywords = fields.JSONField(default=list)

    class Meta(BaseModel.Meta):
        table = "faqs"
        schema = "backend"
