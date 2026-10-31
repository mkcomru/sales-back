from __future__ import annotations

from enum import Enum

from tortoise import fields

from src.backend.modules.core.base_model import BaseModel


class AgentType(str, Enum):
    """Agent types for prompts."""

    AGENT = "agent"


class Prompt(BaseModel):
    id = fields.IntField(primary_key=True)
    agent_type = fields.CharEnumField(AgentType, max_length=50, unique=True)
    content = fields.TextField()

    class Meta:
        table = "prompts"
        schema = "backend"
