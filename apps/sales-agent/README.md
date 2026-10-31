# Sales Agent

AI-driven conversation service for automated sales assistance.

## Overview
- **FastAPI** HTTP layer for unified inbound messages
- LLM-based conversation pipeline with tool calling
- Tortoise ORM models for persistence
- Debounce manager to batch chat messages

## Unified Inbound Endpoint

All connectors send messages to a single endpoint:

```
POST /api/v1/messages/inbound
```

### InboundEnvelope Schema
```json
{
  "connector_id": "tg-bot-abc123",
  "conversation_id": "12345",
  "user_id": "user-67890",
  "text": "Hello!",
  "audio": null,
  "ts": 1703520000.0
}
```

### Dual-Path Authentication

**Managed connectors** (telegram, wappi):
```
X-Service-Key: <service-key>
X-Connector-Id: <connector-id>
```

**Custom connectors**:
```
Authorization: Bearer sk_xxx
```

## Local development

```bash
# From repository root - install all workspace dependencies
uv sync

# Copy env template if needed
cd apps/sales-agent
cp .env.example .env

# Start API (from module directory)
uv run uvicorn src.sales_agent.main:app --reload
# or use make
make dev

# Run tests
uv run pytest
```

## Connector Sync

Sales Agent periodically fetches connector configuration from backend:
```
GET /transport/connectors
```

Configuration is cached in `SalesAgentSettings.connectors` and refreshed:
- On startup
- Periodically (configurable interval)
- On `transport.connectors.changed` event via Redis Streams

## Transport Delivery

Responses are delivered to Backend for routing:
```
POST /api/v1/internal/messages/outbound
```

Backend routes responses to the appropriate transport module based on `connector.type`:
- `telegram` → telegram-module endpoint
- `wappi` → wappi-module endpoint

Sales Agent no longer calls transport modules directly. All routing is handled by Backend.

## Docker

```bash
# Build from repository root
docker compose build sales-agent

# Run with compose
docker compose up sales-agent
```

Compose loads variables from `.env.shared` and `apps/sales-agent/.env`.
