"""Basic MongoDB-like operators for condition evaluation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# Sentinel value to distinguish "key doesn't exist" from "key exists with None value"
_MISSING = object()


def op_and(operands: list[Any], evaluate_fn: Callable[[Any], bool]) -> bool:
    """$and operator - all operands must be true."""
    if not isinstance(operands, list):
        raise ValueError("$and requires a list of conditions")
    if not operands:
        return True
    return all(evaluate_fn(op) for op in operands)


def op_or(operands: list[Any], evaluate_fn: Callable[[Any], bool]) -> bool:
    """$or operator - at least one operand must be true."""
    if not isinstance(operands, list):
        raise ValueError("$or requires a list of conditions")
    if not operands:
        return False
    return any(evaluate_fn(op) for op in operands)


def op_not(operand: Any, evaluate_fn: Callable[[Any], bool]) -> bool:
    """$not operator - negates the operand."""
    return not evaluate_fn(operand)


def op_eq(field_path: str, expected_value: Any, context: dict[str, Any]) -> bool:
    """$eq operator - field equals expected value."""
    actual_value = _get_field_value(field_path, context)
    if actual_value is _MISSING:
        return expected_value is None
    return actual_value == expected_value


def op_ne(field_path: str, expected_value: Any, context: dict[str, Any]) -> bool:
    """$ne operator - field not equals expected value."""
    actual_value = _get_field_value(field_path, context)
    if actual_value is _MISSING:
        return expected_value is not None
    return actual_value != expected_value


def op_gt(field_path: str, threshold: Any, context: dict[str, Any]) -> bool:
    """$gt operator - field greater than threshold."""
    actual_value = _get_field_value(field_path, context)
    if actual_value is _MISSING or actual_value is None:
        return False
    if not isinstance(actual_value, (int, float)) or not isinstance(threshold, (int, float)):
        return False
    return actual_value > threshold


def op_gte(field_path: str, threshold: Any, context: dict[str, Any]) -> bool:
    """$gte operator - field greater than or equal to threshold."""
    actual_value = _get_field_value(field_path, context)
    if actual_value is _MISSING or actual_value is None:
        return False
    if not isinstance(actual_value, (int, float)) or not isinstance(threshold, (int, float)):
        return False
    return actual_value >= threshold


def op_lt(field_path: str, threshold: Any, context: dict[str, Any]) -> bool:
    """$lt operator - field less than threshold."""
    actual_value = _get_field_value(field_path, context)
    if actual_value is _MISSING or actual_value is None:
        return False
    if not isinstance(actual_value, (int, float)) or not isinstance(threshold, (int, float)):
        return False
    return actual_value < threshold


def op_lte(field_path: str, threshold: Any, context: dict[str, Any]) -> bool:
    """$lte operator - field less than or equal to threshold."""
    actual_value = _get_field_value(field_path, context)
    if actual_value is _MISSING or actual_value is None:
        return False
    if not isinstance(actual_value, (int, float)) or not isinstance(threshold, (int, float)):
        return False
    return actual_value <= threshold


def op_exists(field_path: str, context: dict[str, Any]) -> bool:
    """$exists operator - field exists in context (key present and value is not null)."""
    value = _get_field_value(field_path, context)
    if value is _MISSING or value is None:
        return False
    return True


def _get_field_value(field_path: str | Any, context: dict[str, Any]) -> Any:
    """Get field value from context using dot notation.

    Returns _MISSING sentinel if key doesn't exist, otherwise returns the value (which can be None).
    """
    if not isinstance(field_path, str):
        return field_path

    if "." not in field_path:
        return context.get(field_path, _MISSING)

    parts = field_path.split(".")
    if len(parts) != 2:
        raise ValueError(f"Field path must have format 'prefix.field': {field_path}")

    prefix, field_name = parts
    if prefix not in context:
        return _MISSING

    prefix_data = context[prefix]
    if not isinstance(prefix_data, dict):
        return _MISSING

    return prefix_data.get(field_name, _MISSING)
