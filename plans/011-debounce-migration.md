# Plan 011 — Debounce Migration to Backend (Redis-backed)

## Objective
Move debounce logic from Sales Agent to Backend. Use Redis for bucket state. Sales Agent becomes stateless and horizontally scalable.

## Problem Statement
Current state after Plan 010:
```
Connector → Backend (validate, gate) → Sales (debounce, process, deliver)
```

Issues:
1. **Sales is stateful** — in-memory debounce buckets in `DebounceManager`
2. **No horizontal scaling** — multiple Sales instances = split buckets = broken debounce
3. **Restart = data loss** — buckets cleared on redeploy
4. **Sales does too much** — debounce is ingestion concern, not generation concern

## Target Architecture
```
Connector → Backend (validate, gate, debounce) → Sales (generate) → Backend (route)
                        │
                        └── Redis (bucket state)
```

**Backend responsibilities:**
- Receive `InboundEnvelope` from connectors
- Validate auth, apply gating
- Debounce: accumulate messages in Redis, fire after silence window
- Send batch to Sales for generation
- Receive response, route to transport

**Sales Agent responsibilities:**
- Receive pre-debounced message batch
- Generate AI response
- Return response to caller
- **Nothing else**

---

## Contract Changes

### Backend Internal: Debounce Trigger → Sales
```
POST /api/v1/internal/generate
Content-Type: application/json
X-Service-Key: {shared_service_key}

{
  "batch": [
    {
      "text": "message 1",
      "user_id": "123",
      "ts": 1703683200.0,
      "attachments": []
    },
    {
      "text": "message 2", 
      "user_id": "123",
      "ts": 1703683205.0,
      "attachments": []
    }
  ],
  "context": {
    "connector_id": "tg-bot-123",
    "company_id": 1,
    "channel_type": "telegram",
    "conversation_id": "chat_456",
    "thread_id": "thread_789"
  }
}
```

### Sales Response
```json
{
  "text": "Generated response text",
  "stage_id": "QUALIFIED",
  "handoff": {
    "summary": "...",
    "reason": "..."
  }
}
```

Backend receives response and routes to transport.

---

## Redis Data Model

### Debounce Bucket
```
Key: debounce:{connector_id}:{conversation_id}
Type: List (RPUSH messages)
TTL: debounce_window + buffer (e.g., 60s)
```

### Bucket Metadata
```
Key: debounce:meta:{connector_id}:{conversation_id}
Type: Hash
Fields:
  - last_message_ts: float
  - debounce_seconds: int
  - company_id: int
  - channel_type: str
TTL: same as bucket
```

### Timer Coordination
Use Redis keyspace notifications or scheduled task:
- On message arrival: update `last_message_ts`, reset timer
- Timer fires when `now - last_message_ts >= debounce_seconds`
- Worker claims bucket (SETNX lock), processes, deletes

---

## Tasks

### 1. Backend: Redis Debounce Service
- [ ] Create `DebounceService` with Redis storage
- [ ] `add_message(envelope, context)` — RPUSH to bucket, update metadata
- [ ] `claim_and_flush(storage_key)` — atomic claim + get + delete
- [ ] Use `aioredis` with connection pooling

### 2. Backend: Debounce Timer Worker
- [ ] Background task scanning for ready buckets
- [ ] Query: buckets where `now - last_message_ts >= debounce_seconds`
- [ ] Claim bucket (distributed lock), fetch messages, call Sales
- [ ] Handle worker failures gracefully (lock TTL)

### 3. Backend: Sales Client for Generation
- [ ] Create `SalesGenerateClient`
- [ ] POST batch + context to `/api/v1/internal/generate`
- [ ] Parse response, route to transport

### 4. Sales Agent: Stateless Generate Endpoint
- [ ] Create `POST /api/v1/internal/generate`
- [ ] Accept `GenerateRequest(batch, context)`
- [ ] Reuse existing pipeline logic (extract from `message_processor.py`)
- [ ] Return `GenerateResponse(text, stage_id, handoff)`
- [ ] **Delete** `DebounceManager` and related code

### 5. Backend: Response Routing
- [ ] Receive `GenerateResponse` from Sales
- [ ] Look up transport config for connector
- [ ] Forward to appropriate transport module
- [ ] Persist assistant message to chat history

### 6. Cleanup
- [ ] Remove `debounce.py` from Sales Agent
- [ ] Remove debounce-related code from `message_processor.py`
- [ ] Remove `InternalInboundRequest` (replaced by `GenerateRequest`)
- [ ] Update `POST /api/v1/internal/messages/inbound` → `/generate`

---

## Migration Strategy

### Single Deployment (Atomic)
1. Deploy Backend with debounce service + worker
2. Deploy Sales with new `/generate` endpoint
3. Backend starts debouncing; Sales becomes stateless

### Deployment Order
1. `libs/common` — add `GenerateRequest`, `GenerateResponse` schemas
2. `apps/backend` — add debounce service, worker, transport routing
3. `apps/sales-agent` — replace internal endpoint, remove debounce
4. Test with single instance
5. Scale Sales horizontally

---

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Debounce storage | Redis Lists + Hash | Fast, atomic, survives restarts |
| Timer mechanism | Polling worker | Simple, reliable; keyspace notifications are fragile |
| Worker coordination | SETNX lock with TTL | Prevents double-processing across workers |
| Sales endpoint | `/generate` | Clear name, single purpose |
| Response routing | Backend handles | Sales doesn't know about transports |

---

## Risks / Notes
- **Redis unavailable** — debounce fails open (messages processed immediately) or closed (queued for retry)
- **Worker lag** — if worker falls behind, debounce windows may exceed target
- **Message ordering** — Redis Lists preserve order; atomic flush ensures batch integrity

## Rollback
- Revert to Plan 010 state (debounce in Sales)
- Re-enable `DebounceManager` in Sales
- Point Backend to old `/internal/messages/inbound` endpoint

## Dependency
- Depends on Plan 010 (Backend Router Ingress)
