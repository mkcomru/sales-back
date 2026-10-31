"""Base worker abstraction for the Worker Hub.

All workers inherit from BaseWorker, implement create() and tick().
The hub only does shared bootstrap (DB, logging), then delegates
construction and lifecycle to each worker individually.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Self

import structlog

from src.backend.modules.core.settings import Settings

log = structlog.get_logger(__name__)


class BaseWorker(ABC):
    """Abstract base for polling workers.

    Subclasses define name, poll_interval_seconds, and implement:
    - create(settings) — async factory that builds the worker with its own deps
    - tick() — single iteration of the main loop
    - shutdown() — optional cleanup (close HTTP clients, connections, etc.)
    """

    name: str
    poll_interval_seconds: int

    @classmethod
    @abstractmethod
    async def create(cls, settings: Settings) -> Self:
        """Async factory — each worker assembles its own dependency graph."""
        ...

    @abstractmethod
    async def tick(self) -> None:
        """Single iteration of the worker's main loop."""
        ...

    async def shutdown(self) -> None:  # noqa: B027
        """Override to release resources (HTTP clients, connections, etc.)."""

    async def run(self) -> None:
        log.info(f"{self.name}.started", poll_interval=self.poll_interval_seconds)
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception(f"{self.name}.tick.error")
            await asyncio.sleep(self.poll_interval_seconds)
