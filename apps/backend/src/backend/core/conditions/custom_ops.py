"""Custom operators for stage transition and ping conditions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def op_stage_completed(stage_id: int | str, context: dict[str, Any]) -> bool:
    """$stage_completed operator - check if order was on this stage.

    Args:
        stage_id: Stage ID to check (can be int or string representation)
        context: Must contain 'completed_stages' list with stage IDs

    Returns:
        True if stage_id is in completed_stages, False otherwise
    """
    completed_stages = context.get("completed_stages", [])
    if not isinstance(completed_stages, list):
        return False

    stage_id_int = int(stage_id) if isinstance(stage_id, str) else stage_id
    return stage_id_int in completed_stages


def op_prev_stage_completed(current_position: int, context: dict[str, Any]) -> bool:
    """$prev_stage_completed operator - check if previous stage was completed.

    Args:
        current_position: Current stage position
        context: Must contain 'completed_stages_by_position' dict mapping position -> stage_id

    Returns:
        True if stage with position-1 was completed, False otherwise
    """
    if current_position <= 0:
        return False

    completed_by_position = context.get("completed_stages_by_position", {})
    if not isinstance(completed_by_position, dict):
        return False

    prev_position = current_position - 1
    return prev_position in completed_by_position


def op_customer_silent_seconds(threshold: int | float, context: dict[str, Any]) -> bool:
    """$customer_silent_seconds operator — check if customer has been silent for >= threshold seconds.

    Args:
        threshold: Minimum silence duration in seconds (compared via >=)
        context: Must contain 'last_customer_message_at' as a datetime

    Returns:
        True if silence >= threshold, False if no last message or threshold not met
    """
    last_msg = context.get("last_customer_message_at")
    if not isinstance(last_msg, datetime):
        return False

    now = datetime.now(UTC)
    if last_msg.tzinfo is None:
        last_msg = last_msg.replace(tzinfo=UTC)
    silence = (now - last_msg).total_seconds()
    return silence >= threshold


def op_any(context: dict[str, Any]) -> bool:
    """$any operator - always returns True (fallback condition for initial stage).

    This operator allows any order to match the condition, useful for
    initial stages that should accept all new orders.
    """
    return True
