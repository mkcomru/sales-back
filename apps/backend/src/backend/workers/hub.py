"""Worker Hub — unified entry point for all backend workers.

Reads WORKERS env var to determine which workers to run.
Handles shared bootstrap (DB, logging) only. Each worker
assembles its own dependencies via create(settings).

Usage:
    WORKERS=all python -m src.backend.workers.hub
    WORKERS=task_scheduler python -m src.backend.workers.hub
    WORKERS=task_scheduler,ping_evaluator python -m src.backend.workers.hub
"""

from __future__ import annotations

import asyncio
import os

import structlog

from common import setup_logging

from src.backend import db
from src.backend.modules.core.settings import get_settings
from src.backend.workers.base import BaseWorker
from src.backend.workers.ping_evaluator import PingEvaluatorWorker
from src.backend.workers.task_scheduler import TaskSchedulerWorker

log = structlog.get_logger(__name__)

WORKER_REGISTRY: dict[str, type[BaseWorker]] = {
    "task_scheduler": TaskSchedulerWorker,
    "ping_evaluator": PingEvaluatorWorker,
}


def parse_workers_env() -> list[str]:
    """Parse WORKERS env var into a list of worker names.

    Returns all registered workers for "all" or empty value.
    Raises ValueError for unknown worker names.
    """
    raw = os.environ.get("WORKERS", "all").strip()
    if not raw or raw == "all":
        return list(WORKER_REGISTRY.keys())

    names = [n.strip() for n in raw.split(",") if n.strip()]
    unknown = set(names) - set(WORKER_REGISTRY.keys())
    if unknown:
        available = ", ".join(sorted(WORKER_REGISTRY.keys()))
        raise ValueError(f"Unknown workers: {', '.join(sorted(unknown))}. Available: {available}")
    return names


async def main() -> None:
    settings = get_settings()
    setup_logging(environment=settings.app.environment, debug=settings.app.debug)
    await db.init()

    worker_names = parse_workers_env()
    log.info("hub.starting", workers=worker_names)

    workers = [await WORKER_REGISTRY[name].create(settings) for name in worker_names]
    log.info("hub.workers_ready", count=len(workers), names=[w.name for w in workers])

    try:
        await asyncio.gather(*(w.run() for w in workers))
    finally:
        for w in workers:
            await w.shutdown()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
