# Event Bus Framework

Signal-only, API-first event propagation for the Sales Bot monorepo.

## Overview

The event bus provides a way for `apps/backend` to notify other services (like `apps/sales-agent`) about configuration changes without those services having to poll. Events are **signals only** — they indicate that something changed, not what the new state is. Consumers must fetch current state from backend APIs.

## Key Principles

1. **API-first**: Events do not replace HTTP APIs. They trigger refreshes.
2. **Backend-only publishing**: Only `apps/backend` produces events.
3. **Signal-only payloads**: Minimal data (IDs, change type), not full state.
4. **At-least-once delivery**: Consumers must be idempotent.
5. **Single-stream**: All events flow through one stream; handlers filter by `event_name`.
6. **Fail-fast**: Misconfiguration when `eventing.enabled=true` prevents startup.

## Architecture

```
┌─────────────┐     publish     ┌─────────────────┐
│   Backend   │ ───────────────►│  Redis Streams  │
│  (producer) │                 │ backend.events  │
└─────────────┘                 └────────┬────────┘
                                         │
                            ┌────────────┼────────────┐
                            │            │            │
                       ┌────▼────┐  ┌────▼────┐  ┌────▼────┐
                       │ Sales   │  │Telegram │  │ Future  │
                       │ Agent   │  │ Module  │  │ Apps    │
                       └────┬────┘  └────┬────┘  └────┬────┘
                            │            │            │
                       ┌────▼────────────▼────────────▼────┐
                       │       GET /transport/connectors   │
                       │           (backend API)           │
                       └───────────────────────────────────┘
```

## Stream

All events use a single stream: `backend.events`

Each consumer app connects with its own **consumer group**, receiving all events
and filtering by `event_name` to determine which handlers to invoke.

**Important**: Each module must have a unique `group` name:
- `sales-agent` → group: `sales-agent`
- `telegram-module` → group: `telegram-module`
- `wappi-module` → group: `wappi-module`

Same group = load balancing (one consumer gets each message).
Different groups = broadcast (all consumers get each message).

## Configuration

### Enabling Eventing

Add to your `.env.shared`:

```env
# Required: Redis URL for broker
REDIS__URL=redis://localhost:6379

# Enable eventing
EVENTING__ENABLED=true
EVENTING__BROKER=redis_streams

# Stream configuration
EVENTING__STREAM__NAME=backend.events
EVENTING__STREAM__GROUP=sales-agent
# EVENTING__STREAM__CONSUMER_NAME defaults to hostname (scales automatically)
```

### Configuration Model

```python
class EventStreamSettings(BaseModel):
    name: str = "backend.events"  # Redis stream name
    group: str                    # Consumer group name (required)
    consumer_name: str            # Defaults to hostname (auto-scales)
    block_ms: int = 5000
    count: int = 10

class EventingSettings(BaseModel):
    enabled: bool = False
    broker: EventBrokerType = EventBrokerType.REDIS_STREAMS
    stream: EventStreamSettings
```

## Event Contracts

All event payloads are defined in `libs/common/src/common/events/contracts/`.

### TransportConnectorsChangedPayloadV1

```python
class TransportConnectorsChangedPayloadV1(BaseEventPayload):
    change_type: ChangeType  # upsert, delete, bulk
    resource: ResourceType   # connectors_aggregate (unified model)
    company_id: int | None = None
    connector_id: str | None = None
```

**Note**: All connector changes use `resource=connectors_aggregate`.

## Quick Start: Connect a New Module

### 1. Add environment variables

```env
# In docker-compose.yml or .env
REDIS__URL=redis://redis:6379
EVENTING__ENABLED=True
EVENTING__STREAM__NAME=backend.events
EVENTING__STREAM__GROUP=your-module-name  # unique per module!
# EVENTING__STREAM__CONSUMER_NAME auto-generates from hostname
```

### 2. Create eventing lifespan

Create `your_module/lifespan/eventing.py`:

```python
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from common import YourModuleSettings  # or appropriate settings class
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
    """Build event handler registry."""
    registry = ConsumerRegistry()

    async def handle_connectors_changed(envelope: EventEnvelope) -> None:
        log.info("event.received", event_name=envelope.event_name)
        # Your refresh logic here
        # e.g., await app.state.some_service.refresh()

    registry.register(
        handler=handle_connectors_changed,
        event_filter={EventName.TRANSPORT_CONNECTORS_CHANGED},
    )

    return registry


@asynccontextmanager
async def eventing_lifespan(app: FastAPI):
    settings: YourModuleSettings = app.state.settings

    if not settings.eventing.enabled:
        log.info("eventing.disabled")
        yield
        return

    if not settings.redis.url:
        log.warning("eventing.skipped", reason="redis_url_not_configured")
        yield
        return

    registry = build_registry(app)
    broker = RedisStreamsBroker(settings.redis.url)

    stream_config = StreamConfig(
        stream_name=settings.eventing.stream.name,
        group=settings.eventing.stream.group,
        consumer_name=settings.eventing.stream.consumer_name,
    )

    await start_event_consumers(
        app=app,
        broker=broker,
        registry=registry,
        stream_config=stream_config,
    )

    yield

    await stop_event_consumers(app)
```

### 3. Wire into main lifespan

```python
# In your main lifespan/__init__.py
from your_module.lifespan.eventing import eventing_lifespan

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(settings_lifespan(app))
        # ... other lifespans ...
        await stack.enter_async_context(eventing_lifespan(app))
        yield
```

### 4. Test it

```bash
# Watch your module logs
docker compose logs -f your-module

# Trigger an event (create a connector in backend)
curl -X POST http://localhost:8081/api/v1/transport/connectors \
  -H "Content-Type: application/json" \
  -H "X-Service-Key: your-key" \
  -d '{
    "connector_id": "test-bot",
    "company_id": 1,
    "type": "telegram",
    "channel_type": "telegram",
    "display_name": "Test Bot",
    "managed": true,
    "config": {"bot_token": "123:ABC", "mode": "polling"}
  }'

# You should see: event.received event_name=transport.connectors.changed
```

---

## Usage

### Publishing Events (Backend Only)

Events are published automatically from transport CRUD operations in `apps/backend`. The `BackendEventPublisher` is initialized in the backend lifespan and emits events after successful DB writes.

```python
# Automatic: called from transport CRUD
await publish_transport_connectors_changed(
    change_type=ChangeType.UPSERT,
    resource=ResourceType.CONNECTORS_AGGREGATE,
    company_id=payload.company_id,
    connector_id=payload.connector_id,
)
```

### Consuming Events

1. Create a registry with handlers:

```python
from common.events import ConsumerRegistry, EventEnvelope, EventName

def build_my_app_registry(app: FastAPI) -> ConsumerRegistry:
    registry = ConsumerRegistry()

    async def handle_connectors_changed(envelope: EventEnvelope) -> None:
        # Fetch current state from backend API
        await app.state.backend_client.refresh_connectors()

    registry.register(
        handler=handle_connectors_changed,
        event_filter={EventName.TRANSPORT_CONNECTORS_CHANGED},
    )

    return registry
```

2. Wire into FastAPI lifespan:

```python
from common.events import StreamConfig, start_event_consumers, stop_event_consumers
from common.events.adapters import RedisStreamsBroker

@asynccontextmanager
async def eventing_lifespan(app: FastAPI):
    settings = app.state.settings

    if not settings.eventing.enabled:
        yield
        return

    registry = build_my_app_registry(app)
    broker = RedisStreamsBroker(settings.redis.url)

    stream_config = StreamConfig(
        stream_name=settings.eventing.stream.name,
        group=settings.eventing.stream.group,
        consumer_name=settings.eventing.stream.consumer_name,
    )

    await start_event_consumers(
        app=app,
        broker=broker,
        registry=registry,
        stream_config=stream_config,
        enabled=True,
    )

    yield

    await stop_event_consumers(app)
```

## Testing

Use the test harness in `common.events.testing`:

```python
from common.events.testing import InMemoryBroker, create_test_runner_deps

async def test_event_handler():
    broker = InMemoryBroker()
    deps = create_test_runner_deps(broker=broker)

    # Create registry, runner, publish events...

    # Assert handler was called, messages were acked
    assert len(broker.get_unacked_messages("stream", "group")) == 0
```

## Error Handling

- **Publishing**: Non-blocking; failures are logged but don't affect CRUD operations.
- **Consuming**: Handlers that fail are retried with exponential backoff. After max retries, the message is NOT acked (will be redelivered).
- **Startup**: If `eventing.enabled=true` and configuration is invalid, the app refuses to start.

## Adding New Events

1. Add event name to `EventName` enum in `common/events/envelope.py`
2. Create payload model in `common/events/contracts/`
3. Register payload in `common/events/contracts/registry.py`
4. Add publishing call in backend service
5. Add handler in consumer app

## Redis Streams Operations

Under the hood, the broker uses:

- `XADD stream * {"data": <json>}` — publish
- `XREADGROUP GROUP g CONSUMER c BLOCK ms COUNT n STREAMS s >` — consume
- `XACK stream group id` — acknowledge
- `XGROUP CREATE stream group 0 MKSTREAM` — create consumer group

