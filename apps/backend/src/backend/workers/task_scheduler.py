"""Task scheduler worker — polls for due tasks and dispatches execution.

Deployment: Runs inside Worker Hub or standalone.
Guarantee: At-least-once delivery — tasks must be idempotent.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Self

import structlog

from common import setup_logging

from src.backend import db
from src.backend.modules.chat.service import ChatService
from src.backend.modules.companies.service import CompaniesService
from src.backend.modules.core.settings import Settings, get_settings
from src.backend.modules.messages.context_assembly import AgentContextAssembler
from src.backend.modules.messages.outbound_service import OutboundService
from src.backend.modules.messages.sales_agent_client import SalesAgentClient
from src.backend.modules.messages.transport_client import TransportClient
from src.backend.modules.orders.service import OrderService
from src.backend.modules.prompts.service import PromptsService
from src.backend.modules.tasks.models import TaskType
from src.backend.modules.tasks.repository import TaskRepository
from src.backend.workers.base import BaseWorker
from src.backend.workers.task_executor import TaskExecutor

log = structlog.get_logger(__name__)


class TaskSchedulerWorker(BaseWorker):
    """Polls for due tasks and dispatches execution."""

    name = "task_scheduler"
    poll_interval_seconds = 10

    def __init__(
        self,
        task_repo: TaskRepository,
        executor: TaskExecutor,
        sales_agent_client: SalesAgentClient,
    ):
        self.task_repo = task_repo
        self.executor = executor
        self._sales_agent_client = sales_agent_client

    @classmethod
    async def create(cls, settings: Settings) -> Self:
        task_repo = TaskRepository()
        order_service = OrderService()
        sales_agent_client = SalesAgentClient(settings)
        chat_service = ChatService(order_service=order_service)
        transport_client = TransportClient(settings)
        context_assembler = AgentContextAssembler(
            companies_service=CompaniesService(),
            prompts_service=PromptsService(),
            chat_service=chat_service,
        )
        outbound_service = OutboundService(transport_client)
        executor = TaskExecutor(
            task_repo=task_repo,
            sales_agent_client=sales_agent_client,
            order_service=order_service,
            context_assembler=context_assembler,
            chat_service=chat_service,
            outbound_service=outbound_service,
        )
        return cls(
            task_repo=task_repo,
            executor=executor,
            sales_agent_client=sales_agent_client,
        )

    async def shutdown(self) -> None:
        await self._sales_agent_client.close()

    async def tick(self) -> None:
        now = datetime.now(UTC)
        tasks = await self.task_repo.get_due_tasks(before=now, limit=100)

        for task in tasks:
            fresh_task = await self.task_repo.get_by_id(task.id)
            if fresh_task.completed or fresh_task.cancelled_at:
                continue

            if task.type == TaskType.AI_SCHEDULED and task.auto_action:
                await self.executor.execute_ai_task(fresh_task)


async def main() -> None:
    """Standalone entry point (backward-compatible)."""
    settings = get_settings()
    setup_logging(environment=settings.app.environment, debug=settings.app.debug)
    await db.init()

    worker = await TaskSchedulerWorker.create(settings)

    try:
        await worker.run()
    finally:
        await worker.shutdown()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
