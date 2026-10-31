"""Event consumer wiring for Sales Agent.

Subscribes to the backend event stream and handles refresh signals.
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from common import SalesAgentSettings
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


def build_sales_agent_registry(app: FastAPI) -> ConsumerRegistry:
    """Build event handler registry for Sales Agent."""
    registry = ConsumerRegistry()

    async def handle_transport_connectors_changed(envelope: EventEnvelope) -> None:
        """Trigger connector config refresh from backend."""
        log.info(
            "event.received",
            event_name=envelope.event_name,
            dedupe_key=envelope.dedupe_key,
            payload=envelope.payload,
        )

        connector_sync = getattr(app.state, "connector_sync", None)
        if connector_sync is None:
            log.warning("event.handler.connector_sync_not_available")
            return

        try:
            await connector_sync.refresh(reason="event")
            log.info(
                "event.handler.connectors_refreshed",
                event_id=str(envelope.event_id),
            )
        except Exception as exc:
            log.error(
                "event.handler.refresh_failed",
                event_id=str(envelope.event_id),
                error=str(exc),
            )
            raise

    async def handle_prompt_changed(envelope: EventEnvelope) -> None:
        """No-op: sales-agent is stateless, prompt comes in each envelope."""
        log.info("event.prompt_changed.ack", event_id=str(envelope.event_id))

    async def handle_company_spec_changed(envelope: EventEnvelope) -> None:
        """No-op: sales-agent is stateless, company spec comes in each envelope."""
        log.info("event.company_spec_changed.ack", event_id=str(envelope.event_id))

    registry.register(
        handler=handle_transport_connectors_changed,
        event_filter={EventName.TRANSPORT_CONNECTORS_CHANGED},
    )
    registry.register(
        handler=handle_prompt_changed,
        event_filter={EventName.PROMPT_CHANGED},
    )
    registry.register(
        handler=handle_company_spec_changed,
        event_filter={EventName.COMPANY_SPECIFICATION_CHANGED},
    )

    return registry


@asynccontextmanager
async def eventing_lifespan(app: FastAPI):
    """Start and stop event consumers for Sales Agent."""
    settings: SalesAgentSettings = app.state.settings

    log.info(
        "eventing.config",
        enabled=settings.eventing.enabled,
        redis_url=bool(settings.redis.url),
        stream_name=settings.eventing.stream.name,
        stream_group=settings.eventing.stream.group,
        consumer_name=settings.eventing.stream.consumer_name,
    )

    if not settings.eventing.enabled:
        log.info("eventing.disabled")
        yield
        return

    if not settings.redis.url:
        log.warning("eventing.skipped", reason="redis_url_not_configured")
        yield
        return

    registry = build_sales_agent_registry(app)
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

    yield

    await stop_event_consumers(app)
