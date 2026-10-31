"""Event consumer wiring for Wazzup module."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from common.events import (
    ConsumerRegistry,
    EventEnvelope,
    EventName,
    StreamConfig,
    start_event_consumers,
    stop_event_consumers,
)
from common.events.adapters import RedisStreamsBroker

log = structlog.get_logger(__name__)


def build_registry(app: FastAPI) -> ConsumerRegistry:
    registry = ConsumerRegistry()

    async def handle_connectors_changed(envelope: EventEnvelope) -> None:
        connector_manager = getattr(app.state, "connector_manager", None)
        if connector_manager is None:
            log.warning("event.handler.connector_manager_not_available")
            return
        log.info(
            "event.received",
            event_name=envelope.event_name,
            dedupe_key=envelope.dedupe_key,
            payload=envelope.payload,
        )
        await connector_manager.reload()
        log.info(
            "event.handler.connectors_reloaded",
            event_id=str(envelope.event_id),
        )

    registry.register(
        handler=handle_connectors_changed,
        event_filter={EventName.TRANSPORT_CONNECTORS_CHANGED},
    )
    return registry


@asynccontextmanager
async def eventing_lifespan(app: FastAPI):
    settings = app.state.settings
    log.info(
        "eventing.config",
        enabled=settings.eventing.enabled,
        redis_url=bool(settings.redis.url),
        stream_name=settings.eventing.stream.name,
        stream_group=settings.eventing.stream.group,
    )

    if not settings.eventing.enabled or not settings.redis.url:
        yield
        return

    registry = build_registry(app)
    broker = RedisStreamsBroker(settings.redis.url)
    stream_config = StreamConfig(
        stream_name=settings.eventing.stream.name,
        group=settings.eventing.stream.group,
        consumer_name=settings.eventing.stream.consumer_name,
        block_ms=settings.eventing.stream.block_ms,
        count=settings.eventing.stream.count,
    )

    await start_event_consumers(
        app=app,
        broker=broker,
        registry=registry,
        stream_config=stream_config,
        enabled=settings.eventing.enabled,
    )
    try:
        yield
    finally:
        await stop_event_consumers(app)
