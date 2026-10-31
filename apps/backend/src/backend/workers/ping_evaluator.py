"""Ping evaluator worker — polls for silent threads and schedules auto-pings."""

from __future__ import annotations

from typing import Self

import structlog

from src.backend.modules.core.settings import Settings
from src.backend.modules.pings.evaluator import evaluate_pings
from src.backend.modules.tasks.repository import TaskRepository
from src.backend.workers.base import BaseWorker

log = structlog.get_logger(__name__)


class PingEvaluatorWorker(BaseWorker):
    """Evaluates ping rules against active threads and creates due tasks."""

    name = "ping_evaluator"
    poll_interval_seconds = 60

    def __init__(self, task_repo: TaskRepository):
        self.task_repo = task_repo

    @classmethod
    async def create(cls, settings: Settings) -> Self:
        return cls(task_repo=TaskRepository())

    async def tick(self) -> None:
        created = await evaluate_pings(self.task_repo)
        if created > 0:
            log.info("ping_evaluator.tick.done", pings_scheduled=created)
