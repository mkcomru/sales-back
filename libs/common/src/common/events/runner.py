"""Consumer runner for processing events from a single stream."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

from common.events.broker import EventBroker, ReceivedEvent, StreamConfig
from common.events.registry import ConsumerRegistry

log = structlog.get_logger(__name__)


@dataclass
class RunnerDependencies:
    """
    Injected dependencies for consumer runner (DI-first design).

    Allows deterministic testing by injecting clock, sleep, and logger.
    """

    broker: EventBroker
    clock: Callable[[], datetime] = field(default_factory=lambda: lambda: datetime.now(UTC))
    sleep: Callable[[float], Any] = field(default_factory=lambda: asyncio.sleep)
    logger: Any = field(default_factory=lambda: log)


class ConsumerRunner:
    """
    Runs event consumers for a single stream.

    Handles:
    - Consumer group setup
    - Sequential handler execution filtered by event_name
    - ACK-after-success semantics
    - Error handling with backoff
    - Graceful shutdown
    """

    def __init__(
        self,
        registry: ConsumerRegistry,
        config: StreamConfig,
        deps: RunnerDependencies,
        max_retries: int = 3,
        base_backoff_s: float = 1.0,
    ) -> None:
        self._registry = registry
        self._config = config
        self._deps = deps
        self._max_retries = max_retries
        self._base_backoff_s = base_backoff_s
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        """Start consumer task."""
        if self._running:
            raise RuntimeError("Runner already started")

        if not self._registry.has_handlers():
            self._deps.logger.warning("consumer_runner.no_handlers")
            return

        self._running = True
        self._deps.logger.info(
            "consumer_runner.starting",
            stream=self._config.stream_name,
            group=self._config.group,
        )

        await self._deps.broker.ensure_group(self._config)
        self._task = asyncio.create_task(
            self._consume(),
            name=f"consumer_{self._config.stream_name}",
        )

        self._deps.logger.info(
            "consumer_runner.started",
            stream=self._config.stream_name,
        )

    async def stop(self) -> None:
        """Stop consumer task gracefully."""
        if not self._running:
            return

        self._running = False
        self._deps.logger.info("consumer_runner.stopping")

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        self._deps.logger.info("consumer_runner.stopped")

    async def _consume(self) -> None:
        """Consume events from the stream."""
        self._deps.logger.info(
            "consumer_runner.consuming",
            stream=self._config.stream_name,
            handler_count=len(self._registry.get_all_handlers()),
        )

        try:
            async for received in self._deps.broker.subscribe(self._config):
                if not self._running:
                    break

                handlers = self._registry.get_handlers_for_event(received.envelope.event_name)

                if not handlers:
                    await self._deps.broker.ack(self._config, received.message_id)
                    continue

                success = await self._process_event(received, handlers)
                if success:
                    await self._deps.broker.ack(self._config, received.message_id)

        except asyncio.CancelledError:
            self._deps.logger.debug("consumer_runner.cancelled")
            raise

    async def _process_event(
        self,
        received: ReceivedEvent,
        handlers: list,
    ) -> bool:
        """
        Process an event through all matching handlers.

        Returns True if all handlers succeeded (event should be ACKed).
        """
        envelope = received.envelope
        self._deps.logger.debug(
            "consumer_runner.processing",
            event_name=envelope.event_name,
            event_id=str(envelope.event_id),
            dedupe_key=envelope.dedupe_key,
        )

        for handler in handlers:
            retries = 0
            while retries <= self._max_retries:
                try:
                    await handler(envelope)
                    break
                except Exception as exc:
                    retries += 1
                    if retries > self._max_retries:
                        self._deps.logger.error(
                            "consumer_runner.handler_failed",
                            event_name=envelope.event_name,
                            event_id=str(envelope.event_id),
                            handler=handler.__name__,
                            retries=retries,
                            error=str(exc),
                        )
                        return False

                    backoff = self._base_backoff_s * (2 ** (retries - 1))
                    self._deps.logger.warning(
                        "consumer_runner.handler_retry",
                        event_name=envelope.event_name,
                        handler=handler.__name__,
                        retry=retries,
                        backoff_s=backoff,
                        error=str(exc),
                    )
                    await self._deps.sleep(backoff)

        self._deps.logger.debug(
            "consumer_runner.processed",
            event_name=envelope.event_name,
            event_id=str(envelope.event_id),
        )
        return True
