"""Conditions engine for MongoDB-like transition conditions.

This module provides parsing and evaluation of transition conditions
for stage auto-transitions in the sales funnel.
"""

from src.backend.core.conditions.exceptions import (
    ConditionEvaluationError,
    ConditionSyntaxError,
)
from src.backend.core.conditions.interpreter import (
    evaluate_condition,
    evaluate_condition_detailed,
)
from src.backend.core.conditions.parser import validate_condition
from src.backend.core.conditions.report import (
    ConditionClause,
    ConditionGroup,
    ConditionNode,
    ConditionReport,
)

__all__ = [
    "validate_condition",
    "evaluate_condition",
    "evaluate_condition_detailed",
    "ConditionSyntaxError",
    "ConditionEvaluationError",
    "ConditionClause",
    "ConditionGroup",
    "ConditionNode",
    "ConditionReport",
]
