"""Parser for validating condition JSON syntax."""

from __future__ import annotations

from typing import Any

from src.backend.core.conditions.exceptions import ConditionSyntaxError

# AICODE-NOTE: Logical operators - allowed at top level
LOGICAL_OPERATORS = {
    "$and",
    "$or",
    "$not",
}

# AICODE-NOTE: Custom operators - allowed at top level
CUSTOM_OPERATORS = {
    "$stage_completed",
    "$prev_stage_completed",
    "$any",
    "$customer_silent_seconds",
}

# AICODE-NOTE: Comparison operators - only allowed inside field conditions
COMPARISON_OPERATORS = {
    "$eq",
    "$ne",
    "$gt",
    "$gte",
    "$lt",
    "$lte",
    "$exists",
}

ALL_OPERATORS = LOGICAL_OPERATORS | CUSTOM_OPERATORS | COMPARISON_OPERATORS


def validate_condition(condition: Any, path: str = "") -> None:
    """Validate condition JSON syntax.

    Args:
        condition: Condition to validate (dict, list, or primitive)
        path: Current path in condition tree (for error messages)

    Raises:
        ConditionSyntaxError: If condition has invalid syntax
    """
    if condition is None:
        return

    if isinstance(condition, (str, int, float, bool)):
        return

    if isinstance(condition, list):
        for i, item in enumerate(condition):
            validate_condition(item, f"{path}[{i}]")
        return

    if not isinstance(condition, dict):
        raise ConditionSyntaxError(
            f"Condition must be a dict, list, or primitive value, got {type(condition).__name__}",
            path=path,
        )

    if not condition:
        return

    # AICODE-NOTE: Prevent mixing operators and fields at same level
    operator_keys = [k for k in condition if k.startswith("$")]
    field_keys = [k for k in condition if not k.startswith("$")]

    if operator_keys and field_keys:
        raise ConditionSyntaxError(
            f"Cannot mix operators {operator_keys} and fields {field_keys} at same level. "
            f"Use explicit $and to combine them.",
            path=path,
        )

    for key, value in condition.items():
        current_path = f"{path}.{key}" if path else key

        if key.startswith("$"):
            _validate_operator(key, value, current_path, is_top_level=not path or "." not in path)
        else:
            _validate_field_condition(key, value, current_path)


def _validate_operator(operator: str, value: Any, path: str, is_top_level: bool = False) -> None:
    """Validate operator syntax."""
    if operator not in ALL_OPERATORS:
        raise ConditionSyntaxError(f"Unknown operator: {operator}", path=path)

    # AICODE-NOTE: Comparison operators cannot be used at top level
    if is_top_level and operator in COMPARISON_OPERATORS:
        raise ConditionSyntaxError(
            f"{operator} can only be used inside field conditions, not at top level. "
            f"Use format: {{'field_name': {{'{operator}': value}}}}",
            path=path,
        )

    if operator == "$and":
        if not isinstance(value, list):
            raise ConditionSyntaxError("$and requires a list of conditions", path=path)
        if not value:
            raise ConditionSyntaxError("$and list cannot be empty", path=path)
        for i, item in enumerate(value):
            validate_condition(item, f"{path}[{i}]")
        return

    if operator == "$or":
        if not isinstance(value, list):
            raise ConditionSyntaxError("$or requires a list of conditions", path=path)
        if not value:
            raise ConditionSyntaxError("$or list cannot be empty", path=path)
        for i, item in enumerate(value):
            validate_condition(item, f"{path}[{i}]")
        return

    if operator == "$not":
        if not isinstance(value, dict):
            raise ConditionSyntaxError("$not requires a dict condition", path=path)
        validate_condition(value, path)
        return

    if operator == "$stage_completed":
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ConditionSyntaxError(
                "$stage_completed requires int or string stage_id",
                path=path,
            )
        return

    if operator == "$prev_stage_completed":
        if value is not True:
            raise ConditionSyntaxError(
                "$prev_stage_completed requires boolean true",
                path=path,
            )
        return

    if operator == "$any":
        if value is not True:
            raise ConditionSyntaxError("$any requires boolean true", path=path)
        return

    if operator == "$customer_silent_seconds":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ConditionSyntaxError(
                "$customer_silent_seconds requires a numeric value (seconds)",
                path=path,
            )
        if value <= 0:
            raise ConditionSyntaxError(
                "$customer_silent_seconds must be positive",
                path=path,
            )
        return

    if operator == "$exists":
        if not isinstance(value, bool):
            raise ConditionSyntaxError("$exists requires boolean value", path=path)
        return

    if operator in {"$eq", "$ne", "$gt", "$gte", "$lt", "$lte"}:
        if isinstance(value, (str, int, float, bool, type(None))):
            return
        validate_condition(value, path)
        return


def _validate_field_condition(field_path: str, value: Any, path: str) -> None:
    """Validate field condition (field_path: value or field_path: {operator: value})."""
    if isinstance(value, dict):
        if not value:
            raise ConditionSyntaxError("Empty operator dict", path=path)

        # AICODE-NOTE: All keys in field condition dict must be comparison operators
        for op_key in value:
            if not op_key.startswith("$"):
                raise ConditionSyntaxError(
                    f"Expected operator starting with $, got: {op_key}",
                    path=f"{path}.{op_key}",
                )
            if op_key not in COMPARISON_OPERATORS:
                raise ConditionSyntaxError(
                    f"Invalid field operator: {op_key}. Only comparison operators "
                    f"({', '.join(sorted(COMPARISON_OPERATORS))}) are allowed in field conditions.",
                    path=f"{path}.{op_key}",
                )

        # Validate each operator's value
        for op_key, op_value in value.items():
            _validate_operator(op_key, op_value, f"{path}.{op_key}", is_top_level=False)
    elif isinstance(value, (str, int, float, bool, type(None))):
        return
    else:
        validate_condition(value, path)
