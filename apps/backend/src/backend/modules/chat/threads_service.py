"""Service for thread operations with cross-system side effects.

Encapsulates operations that affect thread state and external systems (e.g. debounce).
Part of the decomposition from ChatService into dedicated thread/message domain services.
"""

from __future__ import annotations

import structlog

from src.backend.modules.chat.models import AssistantMode, Thread
from src.backend.modules.chat.repository import ThreadsRepository
from src.backend.modules.messages.sales_agent_client import SalesAgentClient

log = structlog.get_logger(__name__)


class ThreadsService:
    """Service for thread lifecycle operations with dependent side effects."""

    def __init__(
        self,
        *,
        threads_repo: ThreadsRepository | None = None,
        sales_agent_client: SalesAgentClient | None = None,
    ):
        self._threads_repo = threads_repo or ThreadsRepository()
        self._sales_agent_client = sales_agent_client

    async def set_assistant_mode(
        self,
        thread: Thread,
        mode: AssistantMode,
        reason: str,
        *,
        cancel_debounce_on_deactivate: bool = True,
    ) -> Thread:
        """Set assistant mode. On INACTIVE, cancels debounce bucket.

        Side effects when mode=INACTIVE:
        - Persists thread.assistant_mode=inactive
        - Calls Sales Agent to cancel debounce for the thread

        Use this method for all assistant control; do not bypass via ThreadsRepository.
        """
        thread = await self._threads_repo.set_assistant_mode(thread, mode, reason)
        if mode == AssistantMode.INACTIVE and self._sales_agent_client and cancel_debounce_on_deactivate:
            try:
                await self._sales_agent_client.cancel_debounce(thread.thread_id)
            except Exception:
                log.exception("threads.debounce_cancel_failed", thread_id=thread.thread_id)
        return thread
