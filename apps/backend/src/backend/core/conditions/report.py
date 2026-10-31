"""Pydantic models for detailed condition evaluation reports."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ConditionClause(BaseModel):
    """Leaf node — single field check or custom operator result."""

    type: Literal["clause"] = "clause"
    description: str
    field: str | None
    operator: str
    expected: Any
    actual: Any | None
    result: bool


class ConditionGroup(BaseModel):
    """Logical group — $and / $or / $not with nested children."""

    type: Literal["group"] = "group"
    logic: str
    children: list[ConditionClause | ConditionGroup]
    result: bool


ConditionNode = ConditionClause | ConditionGroup


class ConditionReport(BaseModel):
    """Full evaluation report — root is always a group (implicit AND)."""

    overall: bool
    root: ConditionGroup
