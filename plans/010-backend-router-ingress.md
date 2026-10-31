# Plan 010 — Backend as Central Router

## Objective
Backend becomes the single routing point for ALL message flow:
- **Inbound:** Connectors → Backend → Sales (for AI processing)
- **Outbound:** Sales returns response → Backend → Transport
- **Manager messages:** Backend handles directly (no Sales involvement)

Full migration — no backward compatibility, no legacy code.

## Prerequisites (Completed in Plan 009)
- ✅ Unified `Connector` model with `type`, `config` JSONB, `managed` flag
- ✅ `ConnectorApiKey` model for custom connector auth
- ✅ `InboundEnvelope` and `ConnectorContext` schemas in `libs/common`
- ✅ `GET /internal/connectors/validate` and `GET /internal/connectors/{id}` endpoints
- ✅ Unified `/transport/connectors` endpoint
- ✅ Event-driven connector sync via Redis Streams

## Current Architecture (Post Plan 009)
```
INBOUND:
  Connector → Sales Agent → [debounce] → LLM → Transport (direct)
                    ↓
               Backend (validation)

OUTBOUND (AI):
  Sales → TransportClient → Transport Module (direct, bypasses Backend)

OUTBOUND (Manager):
  Backend → Sales /api/outbound/manager-message → Transport (unnecessary hop)

CONNECTOR CONFIG:
  telegram-module → /transport/telegram/bots (legacy)
  wappi-module → /transport/wappi/connectors (legacy)
```

## Target Architecture (Plan 010)
```
INBOUND:
  ┌─────────────┐   InboundEnvelope    ┌─────────────┐   InternalInbound     ┌─────────────┐
  │  Connector  │ ──────────────────►  │   Backend   │ ──────────────────►   │ Sales Agent │
  │   Module    │   X-Service-Key +    │  (Router)   │   X-Service-Key       │ (Generator) │
  └─────────────┘   X-Connector-Id     └─────────────┘                       └──────┬──────┘
                                                                                    │
OUTBOUND (AI):                                                                      │
  ┌─────────────┐   TransportDelivery   ┌─────────────┐   AgentResponse            │
  │  Transport  │ ◄──────────────────   │   Backend   │ ◄──────────────────────────┘
  │   Module    │   X-Service-Key       │  (Router)   │   X-Service-Key
  └─────────────┘                       └─────────────┘

OUTBOUND (Manager from CRM UI):
  ┌─────────────┐   TransportDelivery   ┌─────────────┐
  │  Transport  │ ◄──────────────────   │   Backend   │  (direct, no Sales)
  │   Module    │   X-Service-Key       │  (Router)   │
  └─────────────┘                       └─────────────┘

CONNECTOR CONFIG:
  All modules → /transport/connectors (unified)
```

## Scope
- **In scope:**
  - Backend ingress endpoint (inbound routing)
  - Backend egress endpoint (outbound routing to transport)
  - Sales returns response to Backend (not to transport)
  - Manager message routing stays in Backend (no Sales)
  - Connector modules retargeted to Backend
  - Connector config unified to `/transport/connectors`
  - Remove legacy transport code from Sales
- **Out of scope:** Multi-consumer routing (future)
- **No backward compatibility** — full migration

---

## Part 1: Inbound Flow (Connector → Backend → Sales)

### Backend Ingress Endpoint
```
POST /api/v1/messages/inbound
Content-Type: application/json

# Managed connectors:
X-Service-Key: {shared_service_key}
X-Connector-Id: {connector_id}

# Custom connectors:
Authorization: Bearer sk_xxx

Body: InboundEnvelope
```

### Backend → Sales Internal Endpoint
```
POST /api/v1/internal/messages/inbound
Content-Type: application/json
X-Service-Key: {shared_service_key}

{
  "envelope": { ... InboundEnvelope ... },
  "context": { ... ConnectorContext ... }
}
```

### Gating Rules (Backend)
1. **Connector disabled** → `403 Forbidden` with `{"error": "connector_disabled"}`
2. **Rate limit exceeded** → `429 Too Many Requests` (future)

---

## Part 2: Outbound Flow (Sales → Backend → Transport)

### Sales Agent Response
Sales no longer calls transport directly. Instead, returns response to Backend:

```
POST /api/v1/internal/messages/outbound  (Backend endpoint)
Content-Type: application/json
X-Service-Key: {shared_service_key}

{
  "connector_id": "tg-bot-123",
  "conversation_id": "123456",
  "replies": ["Hello!", "How can I help?"],
  "correlation_id": "sa12345678",
  "metadata": { ... },
  "stage_id": "QUALIFIED",
  "handoff": { "summary": "...", "reason": "..." }
}
```

### Backend Routes to Transport
Backend receives response from Sales, routes to appropriate transport module based on connector type:

```python
# Backend settings
TRANSPORT__TELEGRAM__URL=http://telegram-module:8001
TRANSPORT__WAPPI__URL=http://wappi-module:8002

# Routing logic
match connector.type:
    case "telegram":
        endpoint = settings.transport.telegram.url
    case "wappi":
        endpoint = settings.transport.wappi.url
```

```
POST {endpoint}/transport/delivery
Content-Type: application/json
X-Service-Key: {shared_service_key}
X-Connector-Id: {connector_id}

Body: TransportDelivery
```

### Manager Messages (CRM UI)
Manager messages from CRM UI stay entirely in Backend — **never go to Sales**:

1. Backend receives manager message (existing flow)
2. Backend disables assistant for thread (`assistant_active = false`)
3. Backend saves message to history
4. Backend routes directly to transport

Sales only sees "assistant is disabled" on next inbound — treats it as context.

---

## Part 3: Connector Config Unification

### Current (Legacy)
```
telegram-module → GET /transport/telegram/bots
wappi-module → GET /transport/wappi/connectors
```

### Target (Unified)
```
All modules → GET /transport/connectors?type={telegram|wappi}
```

Remove legacy endpoints after migration.

---

## Part 4: Legacy Cleanup

### Remove from Sales Agent
- `apps/sales-agent/src/sales_agent/api/inbound.py` — delete entirely
- `apps/sales-agent/src/sales_agent/api/outbound.py` — delete entirely
- `apps/sales-agent/src/sales_agent/services/transport.py`:
  - Delete `TransportClient` class
  - Delete `LegacyTransportDispatcher` class
  - Delete all Bitrix-specific transport logic
- Remove transport client initialization from lifespan

### Remove from Backend
- Delete `/transport/telegram/bots` endpoint (legacy)
- Delete `/transport/wappi/connectors` endpoint (legacy)

---

## Tasks

### 1. Shared Library (`libs/common`)
- [ ] Add `InternalInboundRequest` schema (envelope + context)
- [ ] Add `AgentResponse` schema (replies, metadata, stage_id, handoff)
- [ ] Add `OutboundDeliveryRequest` schema (for Sales → Backend)
- [ ] Refactor `SalesAgentInboundClient` → `BackendInboundClient`

### 2. Backend: Inbound Router
- [ ] Create `POST /api/v1/messages/inbound`
  - Dual-auth: `X-Service-Key` + `X-Connector-Id` OR `Bearer sk_xxx`
  - Reuse `ConnectorsService.validate_api_key()` and `get_context_by_connector_id()`
  - Apply gating (`connector.enabled`)
- [ ] Create `SalesAgentInternalClient` for forwarding to Sales
- [ ] Forward `InternalInboundRequest` to Sales

### 3. Backend: Outbound Router
- [ ] Create `POST /api/v1/internal/messages/outbound`
  - Service key auth
  - Accept `OutboundDeliveryRequest` from Sales
- [ ] Add transport settings to `BackendModuleSettings`:
  ```python
  class BackendTransportSettings(BaseModel):
      telegram: TransportEndpointSettings  # url: AnyHttpUrl
      wappi: TransportEndpointSettings     # url: AnyHttpUrl
  ```
- [ ] Create `TransportClient` in Backend
  - Resolve endpoint from settings based on `connector.type`
  - POST to `{endpoint}/transport/delivery`
  - Include `X-Service-Key` and `X-Connector-Id`

### 4. Backend: Manager Messages
- [ ] Refactor existing manager message flow
  - Remove call to Sales `/api/outbound/manager-message`
  - Route directly to transport via Backend's `TransportClient`
- [ ] Keep: disable assistant, save to history

### 5. Sales Agent: Pure Generator
- [ ] Create `POST /api/v1/internal/messages/inbound`
  - Service key auth
  - Accept `InternalInboundRequest`
  - Return `AgentResponse` (sync) or POST to Backend outbound endpoint
- [ ] Delete `apps/sales-agent/src/sales_agent/api/inbound.py`
- [ ] Delete `apps/sales-agent/src/sales_agent/api/outbound.py`
- [ ] Delete transport client code:
  - `TransportClient` class
  - `LegacyTransportDispatcher` class
  - All Bitrix-specific transport logic
- [ ] Remove transport client from lifespan/dependencies

### 6. Connector Modules Retargeting
- [ ] **telegram-module**:
  - Inbound: `SALES_AGENT__URL` → `BACKEND__URL`
  - Config: `/transport/telegram/bots` → `/transport/connectors?type=telegram`
- [ ] **wappi-module**:
  - Inbound: `SALES_AGENT__URL` → `BACKEND__URL`
  - Config: `/transport/wappi/connectors` → `/transport/connectors?type=wappi`
- [ ] Rename client classes to `BackendInboundClient`

### 7. Backend: Legacy Endpoint Cleanup
- [ ] Delete `/transport/telegram/bots` endpoint
- [ ] Delete `/transport/wappi/connectors` endpoint
- [ ] Ensure `/transport/connectors` supports `type` filter

### 8. Observability
- [ ] Backend logs: `ingress.accepted`, `ingress.gated`, `egress.routed`
- [ ] Sales logs: `internal.inbound.processed`, `internal.response.sent`

---

## Schemas

### InternalInboundRequest (Backend → Sales)
```python
class InternalInboundRequest(BaseModel):
    envelope: InboundEnvelope
    context: ConnectorContext
```

### AgentResponse (Sales → Backend)
```python
class AgentResponse(BaseModel):
    connector_id: str
    conversation_id: str
    correlation_id: str
    replies: list[str]
    metadata: dict[str, Any] = {}
    stage_id: str | None = None
    handoff: HandoffPayload | None = None

class HandoffPayload(BaseModel):
    summary: str
    reason: str
    stage: str | None = None
```

### OutboundDeliveryRequest (Backend internal)
```python
class OutboundDeliveryRequest(BaseModel):
    connector_id: str
    conversation_id: str
    correlation_id: str
    replies: list[str]
    metadata: dict[str, Any] = {}
    stage_id: str | None = None
    handoff: dict[str, Any] | None = None
```

---

## Configuration

### Backend Environment Variables (new)
```bash
# Transport module endpoints
TRANSPORT__TELEGRAM__URL=http://telegram-module:8001
TRANSPORT__WAPPI__URL=http://wappi-module:8002
```

---

## Migration Strategy

### Single Deployment (Atomic)
1. Deploy all changes together — no parallel operation
2. Backend: inbound + outbound routing active
3. Sales: pure generator, no transport
4. Connectors: retargeted to Backend
5. Legacy endpoints removed

### Deployment Order
1. `libs/common` — new schemas
2. `apps/backend` — inbound router + outbound router + transport client
3. `apps/sales-agent` — pure generator, remove transport
4. `apps/telegram-module` — retarget to Backend
5. `apps/wappi-module` — retarget to Backend

All services must be deployed together.

---

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Connector target URL | `BACKEND__URL` | Single routing point |
| Transport endpoints | Backend settings (`TRANSPORT__TELEGRAM__URL`, etc.) | Simple, one module per type per deployment |
| Manager messages | Backend only | No AI processing needed |
| Sales transport | Remove entirely | Backend handles all routing |
| Connector config | Unified endpoint | Remove fragmentation |
| Legacy Bitrix transport | Delete | Moving to legacy folder |
| Error propagation | Backend returns as-is | Transparent routing |

---

## Risks / Notes
- **Backend becomes critical path** — all messages route through Backend
- **Latency** — extra hop for AI responses (Sales → Backend → Transport)
- **Atomic deployment** — partial deploy = broken routing

## Rollback
Full rollback requires reverting all services:
- Sales: restore direct transport calls
- Backend: remove routing endpoints
- Connectors: retarget to Sales

No partial rollback.

## Dependency
- Depends on Plan 009 (completed)
- Plan 011 (Debounce Migration) depends on this plan

---

## Implementation Guide

### Key Clarifications

**1. The response flow is ASYNC, not sync**

Backend → Sales returns `202 Accepted` immediately (message queued in debounce).
Later, when debounce fires and LLM generates response, Sales POSTs to Backend outbound endpoint.
Do NOT try to make Backend wait for the LLM response — it won't come for 45+ seconds.

**2. Where to find existing code to copy/adapt**

| New Code | Copy Pattern From |
|----------|-------------------|
| Backend ingress auth | `apps/sales-agent/src/sales_agent/api/inbound.py` (dual-auth logic) |
| Backend `TransportClient` | `apps/sales-agent/src/sales_agent/services/transport.py` (same concept, simpler) |
| `require_service_api_key` | `apps/backend/src/backend/modules/core/dependencies.py` (already exists) |
| `ConnectorsService` methods | `apps/backend/src/backend/modules/transport/service.py` (reuse directly) |

**3. Sales Agent changes — what stays, what goes**

KEEP:
- `services/debounce.py` — untouched
- `services/message_processor.py` — modify to POST to Backend instead of calling transport
- `agents/` — untouched (LLM pipeline)
- `handlers/dependencies.py` — remove transport-related deps

DELETE ENTIRELY:
- `api/inbound.py`
- `api/outbound.py`
- `services/transport.py`

**4. The `message_processor.py` change is the critical one**

Currently it calls `transport_client.deliver()`. Change to POST to Backend's `/api/v1/internal/messages/outbound`.
Look for where `TransportDelivery` is built — that's where you create `OutboundDeliveryRequest` instead.

**5. Connector modules — minimal change**

Only change the URL they POST to. The envelope format stays identical.
- Find `self._base_url` or `settings.sales_agent_url`
- Change to `settings.backend.url`
- The `/api/v1/messages/inbound` path stays the same

**6. Backend transport settings — extend existing**

`BackendTransportSettings` already exists in `libs/common/src/common/config.py` (line ~162).
It has `telegram: BackendTransportTelegramSettings` with `reload_url`.
Add `url: AnyHttpUrl` to it, and create similar for wappi.

---

### Sanity Checkpoints

After each task group, verify:

**After Task 1 (libs/common):**
- [ ] `from common.models import InternalInboundRequest, AgentResponse` works
- [ ] Schemas have all required fields, no Optional where not intended

**After Task 2 (Backend inbound):**
- [ ] `POST /api/v1/messages/inbound` with `X-Service-Key` + `X-Connector-Id` returns 202
- [ ] Same endpoint with `Authorization: Bearer sk_xxx` returns 202 (if valid key exists)
- [ ] Missing/invalid auth returns 401
- [ ] Disabled connector returns 403 with `{"error": "connector_disabled"}`

**After Task 3 (Backend outbound):**
- [ ] `POST /api/v1/internal/messages/outbound` with valid payload logs `egress.routed`
- [ ] Backend resolves correct transport URL based on connector type
- [ ] If connector type unknown, returns 400 (not 500)

**After Task 5 (Sales pure generator):**
- [ ] Sales has NO imports from `services/transport.py`
- [ ] `grep -r "TransportClient" apps/sales-agent/` returns nothing
- [ ] `grep -r "LegacyTransportDispatcher" apps/sales-agent/` returns nothing
- [ ] Sales `POST /api/v1/internal/messages/inbound` accepts `InternalInboundRequest`

**After Task 6 (Connector retargeting):**
- [ ] `grep -r "sales_agent_url" apps/telegram-module/` returns nothing (except maybe tests)
- [ ] `grep -r "sales_agent_url" apps/wappi-module/` returns nothing (except maybe tests)
- [ ] Modules use `settings.backend.url` for inbound

**After Task 7 (Legacy cleanup):**
- [ ] `GET /transport/telegram/bots` returns 404
- [ ] `GET /transport/wappi/connectors` returns 404
- [ ] `GET /transport/connectors?type=telegram` returns connectors

---

### Common Pitfalls

1. **Don't forget `X-Connector-Id` header in Backend → Transport**
   Transport modules expect this header for routing.

2. **Backend outbound endpoint is INTERNAL, not public**
   Use `/api/v1/internal/messages/outbound` — the `/internal/` prefix matters for auth.

3. **Sales still needs `BackendClient` for other calls**
   Only remove transport-related code. Sales still calls Backend for threads, history, etc.

4. **Connector type comes from `Connector.type` (enum)**
   Not from `channel_type`. The routing match is on `connector.type` which is `telegram`, `wappi`, or `custom`.

5. **`AgentResponse.replies` is a list, not a string**
   Even for single message, wrap in list: `["Hello"]`

6. **Manager messages — don't touch the trigger, only the routing**
   Backend already receives manager messages from CRM. Just change WHERE it routes them (directly to transport, not through Sales).
