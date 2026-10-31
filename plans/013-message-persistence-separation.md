# Plan 013 — Backend as Intelligent Router + Message Persistence Separation

## Objective
1. **Backend becomes the intelligent router** — decides WHETHER to forward to Sales Agent based on thread state
2. **Backend owns all message persistence** — saves user messages on arrival, saves assistant messages on response
3. **Sales Agent is stateless generator** — only debounces and generates responses, no persistence, no routing decisions

## Problem Statement

Current state (after Plan 010):
```
Connector → Backend (blind forward) → Sales Agent
                                      ├─ Get thread from Backend
                                      ├─ Check assistant_active ❌ (routing decision!)
                                      ├─ If inactive: save user message, return early
                                      ├─ Debounce (in-memory)
                                      ├─ Save user messages to DB ❌
                                      ├─ Generate response
                                      └─ Save assistant messages to DB ❌
```

**Issues:**
1. **Backend is NOT intelligent** — blindly forwards ALL messages to Sales Agent
   - `backend/modules/messages/routers.py:77-78` — just forwards, no routing logic
   - Sales Agent makes the `assistant_active` decision, not Backend
2. **Sales Agent makes routing decisions** — violates separation of concerns
   - `message_processor.py:460-478` — checks `assistant_active`, decides whether to process
   - If `assistant_active=False`, Sales Agent saves message and returns — this is Backend's job!
3. **Sales Agent saves user messages** — should not persist anything
   - `message_processor.py:198-206` — saves in sync mode
   - `message_processor.py:464-471` — saves when assistant inactive
   - `pipeline.py:651-658` — saves before processing
4. **Sales Agent saves assistant messages** — should be Backend's responsibility
   - `message_processor.py:636-643` — saves assistant chunks during delivery
5. **Messages appear debounced in UI** — because Sales Agent saves combined messages
   - User sends 3 messages → Sales Agent combines → saves as 1 message → UI shows 1 message

## Target Architecture

```
Connector → Backend (INTELLIGENT ROUTER)
            ├─ Get/create thread
            ├─ Save user message to DB immediately ✅
            ├─ Check assistant_active
            │   ├─ If inactive → STOP (don't forward to Sales Agent)
            │   └─ If active → Forward to Sales Agent
            └─ Sales Agent (PURE GENERATOR)
               ├─ Debounce (in-memory)
               ├─ Generate response (NO persistence, NO routing decisions)
               └─ Return response to Backend
            └─ Backend
               ├─ Save assistant response to DB ✅
               └─ Route to transport
```

**Backend responsibilities:**
- Receive `InboundEnvelope` from connectors
- Get/create thread (owns thread management)
- **Save user message to DB immediately** (before any forwarding)
- **Check `assistant_active` — routing decision**
  - If `assistant_active=False` → done, don't forward to Sales Agent
  - If `assistant_active=True` → forward to Sales Agent
- Receive response from Sales Agent
- **Save assistant response to DB**
- Route response to transport

**Sales Agent responsibilities:**
- Receive message from Backend (only when assistant is active)
- Debounce messages (in-memory)
- Generate AI response
- Return response to Backend
- **DO NOT save any messages** (neither user nor assistant)
- **DO NOT check `assistant_active`** — Backend already decided to send it
- **DO NOT make routing decisions** — just process and return

---

## Contract Changes

### Backend → Sales Agent (CHANGED)
```
POST /api/v1/internal/messages/inbound
Content-Type: application/json
X-Service-Key: {shared_service_key}

{
  "envelope": { ... InboundEnvelope ... },
  "context": { ... ConnectorContext ... },
  "thread_id": "telegram_12345_abc12345"  // NEW: Backend passes thread_id
}
```

**Key changes:**
1. Backend only calls this when `assistant_active=True`
2. **NEW: `thread_id` field** — Backend creates thread, passes ID to Sales Agent
3. Sales Agent uses `thread_id` for history lookup (not for saving)

### Sales Agent → Backend Response (CHANGED)
```
POST /api/v1/internal/messages/outbound
{
  "connector_id": "...",
  "conversation_id": "...",
  "thread_id": "telegram_12345_abc12345",  // NEW: Echo thread_id back
  "replies": ["..."],
  "metadata": {...},
  "stage_id": "...",
  "handoff": {...}
}
```

**Key changes:**
1. **NEW: `thread_id` field** — Sales Agent echoes it back so Backend can save without lookup
2. Backend saves assistant messages using `thread_id`

### Schema Changes Required

**`InboundEnvelope` (libs/common/src/common/models/inbound.py) — NORMALIZE:**
```python
class MessageRole(StrEnum):
    USER = "user"
    MANAGER = "manager"

class InboundEnvelope(BaseModel):
    conversation_id: str
    user_id: str
    text: str | None = None
    ts: float
    audio: AudioData | None = None
    
    # NEW: standardized fields (connectors normalize to these)
    role: MessageRole = MessageRole.USER  # Who sent the message
    is_historical: bool = False  # Is this a sync/backfill message?
    sender_name: str | None = None  # Normalized sender display name
    sender_username: str | None = None  # Normalized sender username/handle
    
    # DEPRECATED: extra dict (move connector-specific logic to connectors)
    extra: dict[str, Any] = Field(default_factory=dict)
```

**`InternalInboundRequest` (libs/common/src/common/models/outbound.py):**
```python
class InternalInboundRequest(BaseModel):
    envelope: InboundEnvelope
    context: ConnectorContext
    thread_id: str  # Backend passes thread_id for history lookup
```

**`OutboundDeliveryRequest` (libs/common/src/common/models/outbound.py):**
```python
class OutboundDeliveryRequest(BaseModel):
    connector_id: str
    conversation_id: str
    thread_id: str  # Echo back for Backend to save assistant messages
    correlation_id: str
    replies: list[str]  # AI-generated text content to persist as new messages
    metadata: dict[str, Any] = Field(default_factory=dict)
    stage_id: str | None = None
    handoff: dict[str, Any] | None = None
```

### Connector Normalization Responsibility

Connectors map their provider-specific logic to standard fields:

**wappi-module:**
```python
# Before: extra["_manager_outgoing"] = True
# After:
envelope.role = MessageRole.MANAGER if is_manager_outgoing else MessageRole.USER
envelope.is_historical = message.get("_sync_mode", False)
envelope.sender_name = message.get("pushName") or message.get("senderName")
```

**telegram-module:**
```python
envelope.role = MessageRole.USER  # Telegram bots only receive user messages
envelope.is_historical = False
envelope.sender_name = f"{message.from_user.first_name} {message.from_user.last_name or ''}".strip()
envelope.sender_username = message.from_user.username
```

### Backend Routing Logic (connector-agnostic)

```python
# Backend decides based on standardized fields, NOT extra dict
if envelope.is_historical:
    # Historical sync: save but don't forward to Sales Agent
    await chat_service.create_message(thread_id, role=envelope.role, ...)
    return {"status": "accepted"}

if envelope.role == MessageRole.MANAGER:
    # Manager message: save, set manager_handling flag, don't forward
    await chat_service.create_message(thread_id, role=ChatMessageRole.MANAGER, ...)
    await chat_service.set_manager_handling(thread_id, handling=True)
    return {"status": "accepted"}

# Regular user message: save and forward if assistant active
await chat_service.create_message(thread_id, role=ChatMessageRole.USER, ...)
if thread.assistant_active:
    await sales_agent_client.forward_inbound(...)
```

---

## Tasks

### 0. Schema Normalization (libs/common) — DO FIRST
- [ ] Add `MessageRole` enum to `libs/common/src/common/models/inbound.py`
  - Values: `USER`, `MANAGER`
- [ ] Extend `InboundEnvelope` with standardized fields:
  - `role: MessageRole = MessageRole.USER`
  - `is_historical: bool = False`
  - `sender_name: str | None = None`
  - `sender_username: str | None = None`
- [ ] Add `thread_id: str` field to `InternalInboundRequest`
- [ ] Add `thread_id: str` field to `OutboundDeliveryRequest`
- [ ] Update tests in `libs/common/tests/models/`
- [ ] Export new types: `from common.models import MessageRole, ...`

### 0.1. Connector Normalization (wappi-module, telegram-module)
- [ ] **wappi-module:** Map `_manager_outgoing` → `envelope.role = MessageRole.MANAGER`
- [ ] **wappi-module:** Map `_sync_mode` → `envelope.is_historical = True`
- [ ] **wappi-module:** Normalize sender name from `pushName`/`senderName`
- [ ] **telegram-module:** Set `envelope.sender_name` from `message.from_user`
- [ ] **telegram-module:** Set `envelope.sender_username` from `message.from_user.username`
- [ ] Remove reliance on `extra` dict for business logic (deprecate gradually)

### 1. Backend: Add ChatService Dependency to Messages Router
- [ ] Import `ChatServiceDep` from `src.backend.modules.chat.dependencies`
  - Location: `apps/backend/src/backend/modules/messages/routers.py`
- [ ] Add `ChatServiceDep` to both endpoints:
  - `inbound_message()` — for thread creation and user message saving
  - `outbound_message()` — for assistant message saving
- [ ] Import `ChatMessageRole`, `ChatMessageStatus` from chat module

### 2. Backend: Intelligent Routing (assistant_active check)
- [ ] Modify `POST /api/v1/messages/inbound` endpoint:
  - After validation, call `ChatService.get_or_create_thread()`
  - **ALWAYS save user message** via `ChatService.create_message()`
  - Check `thread.assistant_active`
  - **If `assistant_active=False`:**
    - Log: `ingress.routing.skipped`, `reason=assistant_inactive`
    - Return `{"status": "accepted"}` — **DO NOT forward**
  - **If `assistant_active=True`:**
    - Build `InternalInboundRequest` with `thread_id`
    - Forward to Sales Agent
    - Log: `ingress.routing.forwarded`

### 3. Backend: Save User Messages on Arrival
- [ ] In `/messages/inbound` endpoint (part of Task 2):
  - Use `role=ChatMessageRole.USER`, `status=ChatMessageStatus.SENT`
  - `delivered_at = datetime.fromtimestamp(envelope.ts, tz=UTC)`
  - `content = envelope.text or ""`
  - `metadata = envelope.extra or {}`
- [ ] Handle empty text (audio-only messages) — save with empty content or placeholder

### 4. Backend: Save Assistant Messages on Response
- [ ] Modify `POST /api/v1/internal/messages/outbound` endpoint:
  - Extract `thread_id` from request (NEW field)
  - For each reply in `replies`:
    - Call `ChatService.create_message(thread_id, ...)`
    - Use `role=ChatMessageRole.ASSISTANT`, `status=ChatMessageStatus.SENT`
    - `delivered_at = datetime.now(UTC)`
  - Log: `egress.assistant.saved`, `replies_count=len(replies)`
  - Then route to transport (existing logic)

### 5. Sales Agent: Update Internal Endpoint to Use thread_id
- [ ] Modify `POST /api/v1/internal/messages/inbound` handler:
  - Extract `thread_id` from `InternalInboundRequest`
  - Pass `thread_id` to debouncer metadata (so it's available in batch callback)
- [ ] Modify `map_to_incoming_message()` in `api/internal_utils.py`:
  - Include `thread_id` in `IncomingMessage.metadata`
- [ ] Modify `handle_agent_batch()` in `message_processor.py`:
  - Extract `thread_id` from metadata
  - Use `thread_id` for `get_recent_history()` calls (LLM context)
  - Include `thread_id` in `OutboundDeliveryRequest`

### 6. Sales Agent: Remove Routing Logic (assistant_active check)
- [ ] Remove from `message_processor.py` `handle_agent_batch()`:
  - Remove `thread_data = await backend_client.get_or_create_thread(...)` call
  - Remove `assistant_active = thread_data.get("assistant_active", True)` check
  - Remove entire `if not assistant_active: ... return` block (lines 463-478)
- [ ] Sales Agent can now assume: if it received the message, assistant is active
- [ ] Log: `agent.processing` (no longer `agent.suppressed.assistant_inactive`)

### 7. Sales Agent: Remove User Message Saving
- [ ] Remove from `message_processor.py`:
  - `handle_sync_batch()` — remove `append_history_batch()` calls (lines 198-206, 228-236)
  - `handle_agent_batch()` — remove `append_history_batch()` for assistant inactive (REMOVED in Task 6)
  - `handle_manager_outgoing()` — remove `append_history_batch()` call (lines 315-322)
- [ ] Remove from `pipeline.py`:
  - `process_user_message_agents()` — remove `append_history_batch()` call (lines 651-658)
  - Remove `append_history_batch` import

### 8. Sales Agent: Remove Assistant Message Saving
- [ ] Remove from `message_processor.py`:
  - `handle_agent_batch()` — remove `append_history_batch()` calls for assistant chunks (lines 636-643)
- [ ] Comment: "Backend saves assistant messages when receiving OutboundDeliveryRequest"

### 9. Sales Agent: Update BackendClient Usage
- [ ] **Keep** methods for READ operations:
  - `get_recent_history(thread_id)` — needed for LLM context
  - `get_customer_profile()`, `get_customer_answers()` — needed for customer state
  - `update_customer_fields()` — needed for quiz answers
  - `get_manager_handling()`, `set_manager_handling()` — needed for handoff
- [ ] **Remove** `get_or_create_thread()` calls in message_processor (use `thread_id` from request)
- [ ] **Deprecate/Remove** `append_history_batch()` method

### 10. Testing & Validation
- [ ] Test: Assistant inactive → message saved, NOT forwarded to Sales Agent
- [ ] Test: Assistant active → message saved AND forwarded (with thread_id)
- [ ] Test: User message arrives → immediately visible in UI (not debounced)
- [ ] Test: Multiple rapid messages → all saved individually
- [ ] Test: Sales Agent receives thread_id, uses it for history
- [ ] Test: Sales Agent echoes thread_id in OutboundDeliveryRequest
- [ ] Test: Backend saves assistant messages using thread_id
- [ ] Test: Sales Agent does NOT check assistant_active (verify logs)
- [ ] Test: Sales Agent does NOT save any messages (verify logs)

### 11. Cleanup
- [ ] Remove `append_history_batch` from Sales Agent imports
- [ ] Remove assistant_active check from Sales Agent
- [ ] Remove unused `get_or_create_thread()` calls in Sales Agent
- [ ] Update tests to pass thread_id in requests
- [ ] Update docs/comments about message persistence flow

---

## Implementation Details

### Backend: Intelligent Routing + Save Message (connector-agnostic)
```python
# apps/backend/src/backend/modules/messages/routers.py

from datetime import UTC, datetime
from common.models.inbound import MessageRole
from src.backend.modules.chat.dependencies import ChatServiceDep
from src.backend.modules.chat.models import ChatMessageRole, ChatMessageStatus

# Map schema role to DB role
ROLE_MAP = {
    MessageRole.USER: ChatMessageRole.USER,
    MessageRole.MANAGER: ChatMessageRole.MANAGER,
}

@router.post("/inbound")
async def inbound_message(
    envelope: InboundEnvelope,
    ...,
    chat_service: ChatServiceDep,
    sales_agent_client: SalesAgentClientDep,
):
    # ... validation (existing) ...
    
    # 1. Get or create thread with normalized metadata
    meta = {
        "name": envelope.sender_name,
        "username": envelope.sender_username,
    }
    thread, created = await chat_service.get_or_create_thread(
        user_id=envelope.user_id,
        company_id=context.company_id,
        channel_type=context.channel_type,
        connector_id=context.connector_id,
        conversation_id=envelope.conversation_id,
        meta={k: v for k, v in meta.items() if v},  # filter None
    )
    
    # 2. ALWAYS save message (using standardized role field)
    db_role = ROLE_MAP[envelope.role]
    await chat_service.create_message(
        thread_id=thread.thread_id,
        role=db_role,
        content=envelope.text or "",
        status=ChatMessageStatus.SENT,
        delivered_at=datetime.fromtimestamp(envelope.ts, tz=UTC),
    )
    
    log.info("ingress.message.saved", thread_id=thread.thread_id, role=envelope.role.value)
    
    # 3. ROUTING DECISION (connector-agnostic, based on schema fields)
    
    # Historical messages: save only, no AI processing
    if envelope.is_historical:
        log.info("ingress.routing.skipped", reason="historical", thread_id=thread.thread_id)
        return {"status": "accepted"}
    
    # Manager messages: set flag, no AI processing
    if envelope.role == MessageRole.MANAGER:
        await chat_service.set_manager_handling(thread.thread_id, handling=True)
        log.info("ingress.routing.skipped", reason="manager_message", thread_id=thread.thread_id)
        return {"status": "accepted"}
    
    # Assistant inactive: save only
    if not thread.assistant_active:
        log.info("ingress.routing.skipped", reason="assistant_inactive", thread_id=thread.thread_id)
        return {"status": "accepted"}
    
    # 4. Forward to Sales Agent (regular user message, assistant active)
    internal_request = InternalInboundRequest(
        envelope=envelope,
        context=context,
        thread_id=thread.thread_id,
    )
    await sales_agent_client.forward_inbound(internal_request)
    
    log.info("ingress.routing.forwarded", thread_id=thread.thread_id)
    return {"status": "accepted"}
```

### Backend: Save Assistant Message on Response
```python
# apps/backend/src/backend/modules/messages/routers.py

@internal_router.post("/outbound")
async def outbound_message(
    request: OutboundDeliveryRequest,
    ...,
    chat_service: ChatServiceDep,  # NEW dependency
    transport_client: TransportClientDep,
):
    # ... validation (existing) ...
    
    # 1. Use thread_id from request (no lookup needed!)
    thread_id = request.thread_id
    
    # 2. Save each assistant reply
    for reply_text in request.replies:
        await chat_service.create_message(
            thread_id=thread_id,
            role=ChatMessageRole.ASSISTANT,
            content=reply_text,
            status=ChatMessageStatus.SENT,
            delivered_at=datetime.now(UTC),
            metadata=request.metadata or {},
        )
    
    log.info(
        "egress.assistant.saved",
        thread_id=thread_id,
        replies_count=len(request.replies),
    )
    
    # 3. Route to transport (existing logic)
    await transport_client.deliver(...)
    
    return {"status": "accepted"}
```

### Sales Agent: Receive thread_id, Use for Context, Echo Back
```python
# apps/sales-agent/src/sales_agent/api/internal_utils.py

def map_to_incoming_message(request: InternalInboundRequest) -> IncomingMessage:
    context = request.context
    envelope = request.envelope
    
    # Include thread_id in metadata so it's available in batch callback
    metadata = {
        "company_id": context.company_id,
        "connector_id": context.connector_id,
        "channel_type": context.channel_type,
        "thread_id": request.thread_id,  # NEW: pass through
        # ... other fields ...
    }
    
    return IncomingMessage(...)
```

```python
# apps/sales-agent/src/sales_agent/services/message_processor.py

async def handle_agent_batch(batch, merged_meta, combined_text, ...):
    # REMOVED: thread_data = await backend_client.get_or_create_thread(...)
    # REMOVED: assistant_active check — Backend already did this
    
    # Get thread_id from metadata (passed by Backend)
    thread_id = merged_meta.get("thread_id")
    if not thread_id:
        log.error("agent.missing_thread_id", conversation_id=conversation_id)
        return
    
    # Use thread_id for history lookup (LLM context)
    history = await backend_client.get_recent_history(thread_id, limit=20)
    
    # ... existing LLM processing ...
    
    # REMOVED: await append_history_batch(...) for user messages
    # REMOVED: await append_history_batch(...) for assistant chunks
    
    # Return response to Backend with thread_id
    outbound_request = OutboundDeliveryRequest(
        connector_id=resolved_connector_id,
        conversation_id=conversation_value,
        thread_id=thread_id,  # NEW: echo back
        correlation_id=chunk_correlation_id,
        replies=[cleared_chunk],
        metadata=delivery_metadata,
        stage_id=chunk_stage_id,
        handoff=chunk_handoff,
    )
    await backend_client.send_outbound_message(outbound_request)
```

```python
# apps/sales-agent/src/sales_agent/agents/pipeline.py

async def process_user_message_agents(...):
    # ... existing LLM processing ...
    
    # REMOVED: await append_history_batch(...) for user message
    # Backend already saved user message before forwarding
    
    return AgentsPipelineResult(text=reply, stage_id=final_stage_id)
```

---

## Migration Strategy

### Single Deployment (Atomic)
1. Deploy Backend with routing logic + message persistence
2. Deploy Sales Agent with routing/persistence removed
3. Verify: messages appear immediately in UI (not debounced)
4. Verify: assistant_inactive threads don't trigger Sales Agent
5. Verify: Sales Agent generates responses correctly

### Deployment Order
1. `apps/backend` — add routing logic + message saving to inbound/outbound endpoints
2. `apps/sales-agent` — remove routing logic + message saving
3. Test end-to-end flows:
   - Assistant active: message saved → forwarded → response saved
   - Assistant inactive: message saved → NOT forwarded
4. Monitor logs to ensure proper routing decisions

---

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Routing decision (assistant_active) | Backend | Backend is the intelligent router |
| User message saving | Backend on arrival, before routing | Messages visible immediately |
| Assistant message saving | Backend on response | Backend controls all persistence |
| Sales Agent persistence | None | Single responsibility: debounce + generate |
| Sales Agent routing | None | Assumes Backend already decided to forward |
| Thread lookup for routing | Backend | Backend owns thread state |
| Thread lookup in Sales Agent | Removed or minimized | Only for LLM context, not routing |

---

## Edge Cases & Clarifications

### Q: What about historical/sync messages?
- **Schema field:** `envelope.is_historical: bool`
- **Connector responsibility:** wappi-module sets `is_historical=True` for sync messages
- **Backend handling:** If `is_historical` → save message, DON'T forward to Sales Agent

### Q: What about manager messages?
- **Schema field:** `envelope.role: MessageRole`
- **Connector responsibility:** wappi-module sets `role=MANAGER` when detecting manager messages
- **Backend handling:** If `role=MANAGER` → save as manager message, set `manager_handling=True`, DON'T forward

### Q: How does Sales Agent get history?
Sales Agent uses `thread_id` passed by Backend:
```python
history = await backend_client.get_recent_history(thread_id, limit=20)
```

### Q: What if envelope.text is empty (audio-only)?
Backend saves the message with empty content. Sales Agent receives full envelope including audio for transcription.

### Q: What about customer metadata (name, username)?
- **Schema fields:** `envelope.sender_name`, `envelope.sender_username`
- **Connector responsibility:** Connectors normalize their provider-specific fields to these
- **Backend handling:**
```python
meta = {
    "name": envelope.sender_name,
    "username": envelope.sender_username,
}
thread, _ = await chat_service.get_or_create_thread(..., meta=meta)
```
Backend is connector-agnostic — it uses standardized fields only.

---

## Risks / Notes

- **Message ordering** — user message saved before Sales Agent processes them ✓
- **Duplicate messages** — Backend should deduplicate if same message arrives twice (optional)
- **Sales Agent failures** — Backend already saved user message, so no data loss
- **Response saving failures** — if Backend fails to save assistant message, transport still receives it
- **Thread state changes during debounce** — if assistant becomes inactive during debounce, response still generated (acceptable)
- **Schema migration** — connectors need to update to use new schema fields before Backend can stop checking `extra` dict
- **Backward compatibility** — during transition, Backend may need to check both schema fields AND `extra` dict

## Rollback

- Revert Backend changes (remove routing logic, remove message saving)
- Revert Sales Agent changes (restore `assistant_active` check, restore `append_history_batch` calls)
- Messages will again be saved after debouncing with routing in Sales Agent

## Dependency

- Depends on Plan 010 (Backend Router Ingress) — Backend must be the routing point
- Supersedes part of Plan 011 (Debounce Migration) — routing logic moves to Backend before debounce migration
- Plan 011 can build on this: when debounce moves to Backend, routing stays in Backend

---

## Success Criteria

### Routing (connector-agnostic)
- [ ] Backend routes based on `envelope.role` and `envelope.is_historical`, NOT `extra` dict
- [ ] `is_historical=True` → message saved, NOT forwarded
- [ ] `role=MANAGER` → message saved, manager_handling set, NOT forwarded
- [ ] `assistant_active=False` → message saved, NOT forwarded
- [ ] Regular user message + assistant active → saved AND forwarded

### Persistence
- [ ] User messages appear in UI immediately (not after debounce window)
- [ ] Multiple rapid messages saved individually, not combined
- [ ] Backend saves all messages (user, manager, assistant)

### Sales Agent (stateless generator)
- [ ] Receives `thread_id` in request
- [ ] Echoes `thread_id` in response
- [ ] Does NOT check `assistant_active`
- [ ] Does NOT check `_sync_mode` or `_manager_outgoing`
- [ ] Does NOT save any messages

### Schema normalization
- [ ] Connectors set `envelope.role` instead of `extra._manager_outgoing`
- [ ] Connectors set `envelope.is_historical` instead of `extra._sync_mode`
- [ ] Connectors set `envelope.sender_name/sender_username` instead of connector-specific fields

---

## Verification Checklist

After implementation, verify with grep:

```bash
# Sales Agent should NOT have these patterns:
grep -r "assistant_active" apps/sales-agent/src/  # Should return nothing
grep -r "append_history_batch" apps/sales-agent/src/  # Should return nothing
grep -r "get_or_create_thread" apps/sales-agent/src/sales_agent/services/message_processor.py  # Should return nothing

# Backend should have these patterns:
grep -r "assistant_active" apps/backend/src/backend/modules/messages/  # Should find routing check
grep -r "create_message" apps/backend/src/backend/modules/messages/  # Should find save calls
```

---

## Key Insight

**Backend is the brain, Sales Agent is the mouth.**

Backend decides:
- Whether to speak (assistant_active check)
- What to remember (message persistence)
- Where to send (transport routing)

Sales Agent only:
- Thinks about what to say (LLM generation)
- Groups thoughts (debouncing)

This separation makes Sales Agent stateless and horizontally scalable.
