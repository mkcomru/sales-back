"""Pydantic schemas for StageTemplate API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.backend.core.conditions import ConditionSyntaxError, validate_condition
from src.backend.modules.stages.models import StageTemplate


class StageTemplateBase(BaseModel):
    """Base stage template schema."""

    name: str = Field(..., description="Stage name", max_length=255)
    color: str | None = Field(None, description="HEX color code", max_length=7, pattern=r"^#[0-9a-fA-F]{6}$")
    is_final: bool = Field(default=False, description="Is this a final stage")
    auto_close: bool = Field(default=False, description="Auto-close order when transitioning to this stage")
    transition_condition: dict[str, Any] | None = Field(None, description="MongoDB-like condition for auto-transition")

    @model_validator(mode="after")
    def validate_auto_close(self):
        if self.auto_close and not self.is_final:
            raise ValueError("Non-final stages cannot have 'auto_close' set to True.")
        return self

    @model_validator(mode="after")
    def validate_transition_condition_syntax(self):
        if self.transition_condition:
            try:
                validate_condition(self.transition_condition)
            except ConditionSyntaxError as e:
                raise ValueError(f"Invalid transition_condition syntax: {e}") from e
        return self


class StageTemplateCreateRequest(StageTemplateBase):
    """Request to create a new stage template."""

    position: int | None = Field(None, description="Position in funnel (auto-assigned if not provided)")


class StageTemplateUpdateRequest(BaseModel):
    """Request to update stage template."""

    name: str | None = Field(None, max_length=255)
    color: str | None = Field(None, max_length=7, pattern=r"^#[0-9a-fA-F]{6}$")
    is_final: bool | None = None
    auto_close: bool | None = None
    transition_condition: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_auto_close(self):
        if self.is_final is False and self.auto_close is True:
            raise ValueError("Non-final stages cannot have 'auto_close' set to True.")
        return self

    @model_validator(mode="after")
    def validate_transition_condition_syntax(self):
        if self.transition_condition:
            try:
                validate_condition(self.transition_condition)
            except ConditionSyntaxError as e:
                raise ValueError(f"Invalid transition_condition syntax: {e}") from e
        return self


class StageTemplateResponse(BaseModel):
    """Stage template response schema."""

    id: int
    company_id: int
    name: str
    color: str | None
    position: int
    is_final: bool
    auto_close: bool
    transition_condition: dict[str, Any] | None
    is_system: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, stage: StageTemplate) -> StageTemplateResponse:
        """Convert StageTemplate model to StageTemplateResponse schema."""
        return cls(
            id=stage.id,
            company_id=stage.company_id,
            name=stage.name,
            color=stage.color,
            position=stage.position,
            is_final=stage.is_final,
            auto_close=stage.auto_close,
            transition_condition=stage.transition_condition,
            is_system=stage.is_system,
            created_at=stage.created_at,
            updated_at=stage.updated_at,
        )


class StageInfo(BaseModel):
    """Stage information for order responses."""

    id: int
    name: str
    color: str | None
    position: int

    @classmethod
    def from_model(cls, stage: StageTemplate | None) -> StageInfo | None:
        """Convert StageTemplate model to StageInfo schema."""
        if stage is None:
            return None
        return cls(
            id=stage.id,
            name=stage.name,
            color=stage.color,
            position=stage.position,
        )


class StageReorderRequest(BaseModel):
    """Request to reorder stages."""

    stage_ids: list[int] = Field(..., description="Stage IDs in desired order")


class RecalculateCompanyOrdersStagesResponse(BaseModel):
    """Response for company orders stages recalculation."""

    processed: int = Field(..., description="Number of orders processed")
    transitions: int = Field(..., description="Number of stage transitions")
    errors: int = Field(..., description="Number of errors encountered")


class RecalculateOrderStageResponse(BaseModel):
    """Response for single order stage recalculation."""

    success: bool = Field(..., description="Whether recalculation was successful")
    message: str = Field(..., description="Result message")
    order_id: int = Field(..., description="Order ID")
    stage_id: int | None = Field(None, description="New stage ID (if successful)")
