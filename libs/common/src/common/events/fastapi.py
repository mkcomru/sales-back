"""FastAPI integration helpers for event consumers."""

from typing import TYPE_CHECKING

import structlog

from common.events.broker import EventBroker, StreamConfig
from common.events.registry import ConsumerRegistry
from common.events.runner import ConsumerRunner, RunnerDependencies

if TYPE_CHECKING:
    from fastapi import FastAPI

log = structlog.get_logger(__name__)


class EventingConfigError(Exception):
    """Raised when eventing configuration is invalid."""


async def start_event_consumers(
    app: "FastAPI",
    broker: EventBroker,
    registry: ConsumerRegistry,
    stream_config: StreamConfig,
    enabled: bool = True,
) -> None:
    """
    Start event consumers as a background task.

    Validates configuration and fails fast if invalid.
    Stores runner in app.state for shutdown handling.

    Args:
        app: FastAPI application instance
        broker: Event broker implementation
        registry: Consumer registry with handlers
        stream_config: Stream configuration from settings
        enabled: Whether eventing is enabled (skips if False)

    Raises:
        EventingConfigError: If configuration is invalid and enabled=True
    """
    if not enabled:
        log.info("eventing.disabled", reason="enabled=False")
        return

    if not registry.has_handlers():
        log.info("eventing.no_handlers", reason="no handlers registered")
        return

    if not stream_config.stream_name:
        raise EventingConfigError("stream_config.stream_name is required")
    if not stream_config.group:
        raise EventingConfigError("stream_config.group is required")
    if not stream_config.consumer_name:
        raise EventingConfigError("stream_config.consumer_name is required")

    deps = RunnerDependencies(broker=broker)
    runner = ConsumerRunner(registry, stream_config, deps)

    await runner.start()

    app.state.event_runner = runner
    app.state.event_broker = broker

    log.info(
        "eventing.started",
        stream=stream_config.stream_name,
        group=stream_config.group,
    )


async def stop_event_consumers(app: "FastAPI") -> None:
    """
    Stop event consumers and clean up resources.

    Safe to call even if consumers were not started.
    """
    runner: ConsumerRunner | None = getattr(app.state, "event_runner", None)
    broker: EventBroker | None = getattr(app.state, "event_broker", None)

    if runner:
        await runner.stop()

    if broker:
        await broker.close()

    log.info("eventing.stopped")
