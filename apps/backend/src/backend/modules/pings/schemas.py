"""Pydantic schemas for PingRule API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.backend.core.conditions import ConditionSyntaxError, validate_condition
from src.backend.modules.pings.enums import PingContentType
from src.backend.modules.pings.models import MAX_PINGS_PER_STAGE, PingRule


class PingRuleCreateRequest(BaseModel):
    position: int = Field(..., ge=1, le=MAX_PINGS_PER_STAGE)
    delay_seconds: int = Field(..., gt=0, description="Seconds of customer silence before ping")
    condition: dict[str, Any] | None = None
    content_type: PingContentType
    static_content: str | None = None
    prompt_override: str | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def validate_content(self):
        if self.content_type == PingContentType.STATIC and not self.static_content:
            raise ValueError("static_content is required when content_type is 'static'")
        return self

    @model_validator(mode="after")
    def validate_condition_syntax(self):
        if self.condition:
            try:
                validate_condition(self.condition)
            except ConditionSyntaxError as e:
                raise ValueError(f"Invalid condition syntax: {e}") from e
        return self


class PingRuleUpdateRequest(BaseModel):
    delay_seconds: int | None = Field(None, gt=0)
    condition: dict[str, Any] | None = None
    content_type: PingContentType | None = None
    static_content: str | None = None
    prompt_override: str | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_content(self):
        if self.content_type == PingContentType.STATIC and self.static_content is None:
            raise ValueError("static_content is required when content_type is 'static'")
        return self

    @model_validator(mode="after")
    def validate_condition_syntax(self):
        if self.condition:
            try:
                validate_condition(self.condition)
            except ConditionSyntaxError as e:
                raise ValueError(f"Invalid condition syntax: {e}") from e
        return self


class PingRuleReorderRequest(BaseModel):
    ping_rule_ids: list[int] = Field(..., description="Ping rule IDs in desired order", min_length=1)


class PingRuleResponse(BaseModel):
    id: int
    company_id: int
    stage_id: int
    position: int
    delay_seconds: int
    condition: dict[str, Any] | None
    content_type: PingContentType
    static_content: str | None
    prompt_override: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, rule: PingRule) -> PingRuleResponse:
        return cls(
            id=rule.id,
            company_id=rule.company_id,
            stage_id=rule.stage_id,
            position=rule.position,
            delay_seconds=rule.delay_seconds,
            condition=rule.condition,
            content_type=PingContentType(rule.content_type),
            static_content=rule.static_content,
            prompt_override=rule.prompt_override,
            is_active=rule.is_active,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )
