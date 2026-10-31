"""Interpreter for evaluating conditions on context data."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.backend.core.conditions.custom_ops import (
    op_any,
    op_customer_silent_seconds,
    op_prev_stage_completed,
    op_stage_completed,
)
from src.backend.core.conditions.exceptions import ConditionEvaluationError
from src.backend.core.conditions.operators import (
    _MISSING,
    _get_field_value,
    op_and,
    op_eq,
    op_exists,
    op_gt,
    op_gte,
    op_lt,
    op_lte,
    op_ne,
    op_not,
    op_or,
)
from src.backend.core.conditions.report import (
    ConditionClause,
    ConditionGroup,
    ConditionNode,
    ConditionReport,
)

# AICODE-NOTE: Registry for logical operators (top-level only)
LOGICAL_OPERATORS: dict[str, Callable] = {
    "$and": lambda value, ctx, pos, eval_fn: op_and(value, eval_fn),
    "$or": lambda value, ctx, pos, eval_fn: op_or(value, eval_fn),
    "$not": lambda value, ctx, pos, eval_fn: op_not(value, eval_fn),
}

# AICODE-NOTE: Registry for custom operators (top-level only)
CUSTOM_OPERATORS: dict[str, Callable] = {
    "$stage_completed": lambda value, ctx, pos: op_stage_completed(value, ctx),
    "$prev_stage_completed": lambda value, ctx, pos: op_prev_stage_completed(pos, ctx),
    "$any": lambda value, ctx, pos: op_any(ctx),
    "$customer_silent_seconds": lambda value, ctx, pos: op_customer_silent_seconds(value, ctx),
}

# AICODE-NOTE: Registry for field comparison operators (inside field conditions only)
FIELD_OPERATORS: dict[str, Callable] = {
    "$eq": op_eq,
    "$ne": op_ne,
    "$gt": op_gt,
    "$gte": op_gte,
    "$lt": op_lt,
    "$lte": op_lte,
    "$exists": lambda field_path, value, ctx: op_exists(field_path, ctx) if value else not op_exists(field_path, ctx),
}


def evaluate_condition(
    condition: dict[str, Any] | None,
    context: dict[str, Any],
    current_stage_position: int | None = None,
) -> bool:
    """Evaluate condition against context.

    Args:
        condition: Condition dict (MongoDB-like syntax) or None
        context: Context dict with keys:
            - order_fields: dict with order field values
            - customer_fields: dict with customer field values
            - completed_stages: list of completed stage IDs
            - completed_stages_by_position: dict mapping position -> stage_id
        current_stage_position: Current stage position (for $prev_stage_completed)

    Returns:
        True if condition matches, False otherwise

    Raises:
        ConditionEvaluationError: If evaluation fails due to missing data
    """
    if condition is None:
        return False

    if not isinstance(condition, dict):
        raise ConditionEvaluationError(f"Condition must be a dict, got {type(condition).__name__}")

    if not condition:
        return True

    normalized_context = _normalize_context(context)

    try:
        return _evaluate_condition_dict(condition, normalized_context, current_stage_position)
    except Exception as e:
        raise ConditionEvaluationError(f"Failed to evaluate condition: {e}") from e


def _normalize_context(context: dict[str, Any]) -> dict[str, Any]:
    """Normalize context to include order_fields and customer_fields at top level."""
    normalized = context.copy()

    order_fields = context.get("order_fields", {})
    customer_fields = context.get("customer_fields", {})

    if isinstance(order_fields, dict):
        for key, value in order_fields.items():
            normalized[f"order_fields.{key}"] = value
        normalized["order_fields"] = order_fields
    elif "order_fields" not in context:
        normalized["order_fields"] = {}

    if isinstance(customer_fields, dict):
        for key, value in customer_fields.items():
            normalized[f"customer_fields.{key}"] = value
        normalized["customer_fields"] = customer_fields
    elif "customer_fields" not in context:
        normalized["customer_fields"] = {}

    return normalized


def _evaluate_condition_dict(
    condition: dict[str, Any],
    context: dict[str, Any],
    current_stage_position: int | None = None,
) -> bool:
    """Evaluate a condition dictionary.

    AICODE-NOTE: Implements implicit AND for multiple keys at same level.
    All conditions must be true for the dict to match.
    """
    if not condition:
        return True

    results: list[bool] = []

    for key, value in condition.items():
        if key.startswith("$"):
            # This is an operator
            result = _evaluate_operator(key, value, context, current_stage_position)
            results.append(result)
        else:
            # This is a field condition
            result = _evaluate_field_condition(key, value, context)
            results.append(result)

    # Implicit AND: all conditions must be true
    return all(results) if results else True


def _evaluate_operator(
    operator: str,
    value: Any,
    context: dict[str, Any],
    current_stage_position: int | None,
) -> bool:
    """Evaluate a top-level operator."""
    # Logical operators
    if operator in LOGICAL_OPERATORS:

        def eval_fn(op: Any) -> bool:
            return _evaluate_operand(op, context, current_stage_position)

        return LOGICAL_OPERATORS[operator](value, context, current_stage_position, eval_fn)

    # Custom operators
    if operator in CUSTOM_OPERATORS:
        # Special handling for $prev_stage_completed
        if operator == "$prev_stage_completed" and current_stage_position is None:
            return False
        return CUSTOM_OPERATORS[operator](value, context, current_stage_position)

    raise ConditionEvaluationError(f"Unknown operator: {operator}")


def _evaluate_field_condition(field_path: str, value: Any, context: dict[str, Any]) -> bool:
    """Evaluate a field condition.

    AICODE-NOTE: If value is a dict with multiple operators, applies implicit AND.
    E.g., {"age": {"$gte": 18, "$lte": 30}} means (age >= 18 AND age <= 30).
    """
    if not isinstance(value, dict):
        # Simple equality check
        return op_eq(field_path, value, context)

    # Multiple operators on same field - implicit AND
    results: list[bool] = []
    for op_key, op_value in value.items():
        if op_key not in FIELD_OPERATORS:
            raise ConditionEvaluationError(f"Unknown field operator: {op_key}")

        operator_fn = FIELD_OPERATORS[op_key]
        if op_key == "$exists":
            # $exists has special signature
            result = operator_fn(field_path, op_value, context)
        else:
            result = operator_fn(field_path, op_value, context)
        results.append(result)

    return all(results) if results else True


def _evaluate_operand(operand: Any, context: dict[str, Any], current_stage_position: int | None) -> bool:
    """Evaluate a single operand (can be a condition dict or a value)."""
    if isinstance(operand, dict):
        return _evaluate_condition_dict(operand, context, current_stage_position)
    return bool(operand)


# ---------------------------------------------------------------------------
# Detailed evaluation (returns tree of results for UI reports)
# ---------------------------------------------------------------------------

_OPERATOR_SYMBOLS: dict[str, str] = {
    "$eq": "=",
    "$ne": "≠",
    "$gt": ">",
    "$gte": "≥",
    "$lt": "<",
    "$lte": "≤",
}


def evaluate_condition_detailed(
    condition: dict[str, Any] | None,
    context: dict[str, Any],
    current_stage_position: int | None = None,
) -> ConditionReport:
    """Evaluate condition and return a detailed tree of per-clause results.

    Same semantics as evaluate_condition but builds a ConditionReport
    instead of a flat bool. Intended for UI/debug requests — NOT for
    the hot recalculation path.
    """
    if condition is None:
        return ConditionReport(
            overall=False,
            root=ConditionGroup(logic="and", children=[], result=False),
        )

    if not isinstance(condition, dict):
        raise ConditionEvaluationError(f"Condition must be a dict, got {type(condition).__name__}")

    if not condition:
        return ConditionReport(
            overall=True,
            root=ConditionGroup(logic="and", children=[], result=True),
        )

    normalized_context = _normalize_context(context)

    try:
        root = _evaluate_dict_detailed(condition, normalized_context, current_stage_position)
        return ConditionReport(overall=root.result, root=root)
    except ConditionEvaluationError:
        raise
    except Exception as e:
        raise ConditionEvaluationError(f"Failed to evaluate condition: {e}") from e


def _evaluate_dict_detailed(
    condition: dict[str, Any],
    context: dict[str, Any],
    position: int | None,
) -> ConditionGroup:
    """Detailed version of _evaluate_condition_dict — returns a ConditionGroup."""
    if not condition:
        return ConditionGroup(logic="and", children=[], result=True)

    children: list[ConditionNode] = []

    for key, value in condition.items():
        if key.startswith("$"):
            children.append(_evaluate_operator_detailed(key, value, context, position))
        else:
            children.append(_evaluate_field_detailed(key, value, context))

    result = all(c.result for c in children) if children else True
    return ConditionGroup(logic="and", children=children, result=result)


def _evaluate_operator_detailed(
    operator: str,
    value: Any,
    context: dict[str, Any],
    position: int | None,
) -> ConditionNode:
    """Detailed version of _evaluate_operator."""
    if operator in {"$and", "$or"}:
        if not isinstance(value, list):
            raise ConditionEvaluationError(f"{operator} requires a list of conditions")
        children = [_evaluate_operand_detailed(op, context, position) for op in value]
        if operator == "$and":
            result = all(c.result for c in children) if children else True
        else:
            result = any(c.result for c in children) if children else False
        return ConditionGroup(logic=operator.lstrip("$"), children=children, result=result)

    if operator == "$not":
        child = _evaluate_operand_detailed(value, context, position)
        return ConditionGroup(logic="not", children=[child], result=not child.result)

    if operator == "$stage_completed":
        from src.backend.core.conditions.custom_ops import op_stage_completed

        result = op_stage_completed(value, context)
        return ConditionClause(
            description=f"Stage {value} completed",
            field=None,
            operator="$stage_completed",
            expected=value,
            actual=value if result else None,
            result=result,
        )

    if operator == "$prev_stage_completed":
        if position is None:
            result = False
        else:
            from src.backend.core.conditions.custom_ops import op_prev_stage_completed

            result = op_prev_stage_completed(position, context)
        return ConditionClause(
            description="Previous stage completed",
            field=None,
            operator="$prev_stage_completed",
            expected=True,
            actual=result,
            result=result,
        )

    if operator == "$any":
        return ConditionClause(
            description="Any order (always true)",
            field=None,
            operator="$any",
            expected=True,
            actual=True,
            result=True,
        )

    if operator == "$customer_silent_seconds":
        result = op_customer_silent_seconds(value, context)
        return ConditionClause(
            description=f"Customer silent ≥ {value}s",
            field=None,
            operator="$customer_silent_seconds",
            expected=value,
            actual=result,
            result=result,
        )

    raise ConditionEvaluationError(f"Unknown operator: {operator}")


def _evaluate_field_detailed(
    field_path: str,
    value: Any,
    context: dict[str, Any],
) -> ConditionNode:
    """Detailed version of _evaluate_field_condition."""
    raw_actual = _get_field_value(field_path, context)
    actual = None if raw_actual is _MISSING else raw_actual

    if not isinstance(value, dict):
        result = op_eq(field_path, value, context)
        return ConditionClause(
            description=f"{field_path} = {value!r}",
            field=field_path,
            operator="$eq",
            expected=value,
            actual=actual,
            result=result,
        )

    clauses: list[ConditionClause] = []
    for op_key, op_value in value.items():
        if op_key not in FIELD_OPERATORS:
            raise ConditionEvaluationError(f"Unknown field operator: {op_key}")

        op_result = FIELD_OPERATORS[op_key](field_path, op_value, context)

        if op_key == "$exists":
            desc = f"{field_path} {'exists' if op_value else 'not exists'}"
        else:
            symbol = _OPERATOR_SYMBOLS.get(op_key, op_key)
            desc = f"{field_path} {symbol} {op_value!r}"

        clauses.append(
            ConditionClause(
                description=desc,
                field=field_path,
                operator=op_key,
                expected=op_value,
                actual=actual,
                result=op_result,
            )
        )

    if len(clauses) == 1:
        return clauses[0]

    overall = all(c.result for c in clauses)
    return ConditionGroup(logic="and", children=clauses, result=overall)


def _evaluate_operand_detailed(
    operand: Any,
    context: dict[str, Any],
    position: int | None,
) -> ConditionNode:
    """Detailed version of _evaluate_operand."""
    if isinstance(operand, dict):
        return _evaluate_dict_detailed(operand, context, position)
    result = bool(operand)
    return ConditionClause(
        description=str(operand),
        field=None,
        operator="$literal",
        expected=True,
        actual=operand,
        result=result,
    )
