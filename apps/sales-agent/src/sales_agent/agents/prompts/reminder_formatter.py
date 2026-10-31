"""Reminder prompt formatter."""

from pathlib import Path
from typing import Any

from jinja2 import Template

REMINDER_TEMPLATE_PATH = Path(__file__).parent / "reminder.md"


def format_reminder_prompt(
    title: str,
    description: str | None = None,
    order_context: dict[str, Any] | None = None,
    recent_summary: str | None = None,
) -> str:
    """Format reminder prompt with full context.

    Easy to extend: add new parameters here and update template.
    """
    template = Template(REMINDER_TEMPLATE_PATH.read_text())
    return template.render(
        title=title,
        description=description,
        order_context=order_context,
        recent_summary=recent_summary,
    )
