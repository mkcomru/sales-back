"""Correlation ID generation for outbound message tracing."""

from uuid import uuid4


def make_correlation_id(source: str, key: str) -> str:
    """Build a deterministic, greppable correlation ID.

    Format: ``{source}-{key}-{short_uuid}``

    Examples::

        make_correlation_id("reminder", thread_id)   # reminder-abc123-e7f2a3b1
        make_correlation_id("ping", str(task_id))     # ping-42-d4c1ef09
        make_correlation_id("mgr", message_id)        # mgr-msg_001-a9b8c7d6
    """
    return f"{source}-{key}-{uuid4().hex[:8]}"
