# Plan 018 — Order Model Extraction from Thread

## Objective

Extract order-related data (stage, order_fields) from the `Thread` model into a proper `Order` entity. This establishes the foundation for order-centric CRM where one Customer can have multiple Orders (deal history).

---

## Problem Statement

### Current State

Thread model conflates two concerns:
1. **Communication channel** — messages, channel_type, conversation_id
2. **Deal/order state** — stage, custom_fields (in metadata), assignee

```
Thread:
  ├─ id, thread_id, customer, company      # Thread identity
  ├─ channel_type, conversation_id         # Channel binding
  ├─ connector_id                          # Transport binding
  ├─ state, assistant_active               # Conversation state ✓
  ├─ messages                              # Message history ✓
  ├─ assignee                              # ❌ ORDER concept (who handles this deal)
  ├─ stage                                 # ❌ ORDER concept
  └─ metadata.custom_fields                # ❌ Mixed customer/order data
```

### Current Customer Model (Important Context)

Today's architecture:
- **Same connector + same user_id = same Customer** — returning customer is recognized
- **Cross-channel = separate Customers** — Telegram user and WhatsApp user are different records
- **Deal history is possible** — within one connector, customer identity is stable

This means: within a single connector, we CAN track deal history per customer. The Order model enables this by separating "deal state" from "conversation channel".

### Why This Is A Problem

1. **Stage is on Thread, not a proper Order entity**
   - Stage conceptually belongs to the DEAL, not the conversation
   - Thread = communication channel, Order = business transaction
   - Currently mixed: Thread handles both messaging AND deal state

2. **No deal history tracking**
   - Same customer (same connector, same user_id) returns for second deal
   - Current: stage on Thread, no separation between deals
   - Cannot query: "Customer had 3 deals, 2 won, 1 lost"
   - Cannot see: deal #1 was "Closed Won", deal #2 is "Qualification"

### Where Stage Lives Now

| Component | File | What |
|-----------|------|------|
| Model | `backend/modules/chat/models.py:16-24` | `ThreadStage` enum (→ rename to `OrderStage`) |
| Model | `backend/modules/chat/models.py:119` | `Thread.stage` field |
| Repo | `backend/modules/chat/repository.py:404-425` | `update_stage()` |
| Service | `backend/modules/chat/service.py:929-978` | `update_thread_stage()` method |
| API | `backend/modules/chat/routers.py:839-892` | `PATCH /threads/{id}/stage` (public) |
| API | `backend/modules/chat/routers.py:1798-1834` | `PATCH /internal/chat/threads/{id}/stage` |
| Sales-Agent | `sales_agent/agents/tools.py:627-648` | `update_stage()` tool |
| Sales-Agent | `sales_agent/agents/stage.py` | Stage definitions |
| Sales-Agent | `sales_agent/agents/pipeline.py:416-420` | `_snapshot_stage()` |
| Sales-Agent | `sales_agent/services/message_processor.py` | Stage propagation in delivery |
| Sales-Agent | `sales_agent/core/tools/registry.py:105-118,293-312` | Tool schema + handler |
| Sales-Agent | `sales_agent/services/backend_client.py:420-440` | `update_thread_stage()` client |
| Sales-Agent | `sales_agent/services/crm_adapter.py` | CRM stage ID resolution |

### Additional Contract Points (need updates)

| Component | File | What |
|-----------|------|------|
| Contract | `libs/common/models/outbound.py:35-41` | `InternalInboundRequest` (add `order_id`) |
| Contract | `libs/common/models/outbound.py:43-50` | `OutboundDeliveryRequest.stage_id` |
| Schema | `backend/modules/chat/schemas.py` | `ThreadGetOrCreateResponse.stage` (remove) |
| Schema | `backend/modules/chat/schemas.py` | `ThreadStageUpdateRequest/Response` (remove) |
| Schema | `backend/modules/chat/schemas.py` | `ThreadAssigneeUpdateRequest/Response` (remove) |
| Schema | `backend/modules/chat/routers.py:895-982` | `update_thread_assignee` endpoint (remove) |
| Client | `sales_agent/services/backend_client.py:417` | Returns `stage` in `get_or_create_thread()` |

> **Important distinction:**
> - `OrderStage` (enum: new, qualification, offer, negotiation, closed) — internal order state
> - `stage_id` in `OutboundDeliveryRequest` — external CRM stage ID (e.g., Bitrix deal stage)
> - These are separate concepts: CRM adapter maps `OrderStage` → external `stage_id` via `crm_adapter.py`

---

## Target Architecture

```
Customer (1) ←───────┬───────→ (N) Order
                     │              ├─ stage (OrderStage enum)
                     │              ├─ order_fields: JSON
                     │              ├─ order_number (per company)
                     │              ├─ assignee → CompanyUser  # moved from Thread
                     │              ├─ result (WON/LOST)
                     │              └─ closed_at
                     │
                     └───────→ (N) Thread
                                   ├─ active_order → Order (nullable)
                                   ├─ channel_type
                                   ├─ state, assistant_active
                                   └─ messages
```

**Key invariants:**
- One Customer can have many Orders (deal history)
- One Customer can have only ONE active Order at a time
- Thread.active_order links conversation to current deal
- Thread remains the communication channel (messages, channel binding)
- Order represents the deal/sale being worked on, including who handles it

**Why assignee moves to Order:**
- Assignee answers "who handles this deal/sale" — a business concern, not a channel concern
- Same deal can be discussed across multiple channels (Telegram, WhatsApp) — assignee stays with the deal
- When customer returns for a new order, assignee may be different (new deal, new assignment)

---

## Migration Strategy

### Phase 0: Analysis & Preparation

**Goal:** Understand all touchpoints, prepare test coverage.

- [ ] Audit all `Thread.stage` usages across codebase
- [ ] Audit `Thread.metadata.custom_fields` usages  
- [ ] Document frontend dependencies on Thread.stage
- [ ] Create integration tests for current behavior (golden master)

### Phase 1: Order Model Creation

**Goal:** Create Order model without breaking existing code.

**1.1 Create new orders module:**

New module structure:
```
backend/modules/orders/
├── __init__.py
├── models.py       # Order, OrderStage, OrderResult
├── service.py      # OrderService
├── repository.py   # OrdersRepository
├── routers.py      # Public + internal endpoints
├── schemas.py      # Pydantic schemas
└── dependencies.py # OrderServiceDep for FastAPI injection
```

> **Implementation note:** Create `OrderServiceDep` following the same pattern as `ChatServiceDep` in `backend/modules/chat/dependencies.py`. The message router already uses typed deps (e.g., `chat_service: ChatServiceDep`).

```python
# backend/modules/orders/models.py

class OrderStage(str, Enum):
    NEW = "new"
    QUALIFICATION = "qualification"
    OFFER = "offer"
    NEGOTIATION = "negotiation"
    CLOSED = "closed"

class OrderResult(str, Enum):
    WON = "won"
    LOST = "lost"
```

**1.2 Order model:**

```python
# backend/modules/orders/models.py

class Order(BaseModel):
    id = fields.IntField(primary_key=True)
    order_number = fields.IntField()
    name = fields.CharField(max_length=255, null=True)
    
    customer: ForeignKeyRelation = fields.ForeignKeyField(
        "models.Customer",
        related_name="orders",
        on_delete=fields.CASCADE,
    )
    company: ForeignKeyRelation = fields.ForeignKeyField(
        "models.Company",
        related_name="orders",
        on_delete=fields.CASCADE,
    )
    assignee: ForeignKeyNullableRelation = fields.ForeignKeyField(
        "models.CompanyUser",
        related_name="assigned_orders",  # note: Thread had "assigned_threads"
        on_delete=fields.SET_NULL,
        null=True,
    )
    stage = fields.CharEnumField(OrderStage, max_length=30, default=OrderStage.NEW)
    
    order_fields = fields.JSONField(default=dict)
    initial_channel = fields.CharField(max_length=50, null=True)
    result = fields.CharEnumField(OrderResult, max_length=10, null=True)
    
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    closed_at = fields.DatetimeField(null=True)

    class Meta(BaseModel.Meta):
        table = "orders"
        schema = "backend"
        unique_together = (("company", "order_number"),)
        indexes = (("customer_id", "closed_at"),)
```

**1.3 Thread → Order relation:**

```python
# backend/modules/chat/models.py

class Thread(BaseModel):
    # ... existing fields ...
    
    active_order: ForeignKeyNullableRelation = fields.ForeignKeyField(
        "models.Order",
        related_name="threads",
        on_delete=fields.SET_NULL,
        null=True,
    )
    
    # Thread.stage REMOVED — stage now lives on Order
    # Thread.assignee REMOVED — assignee now lives on Order
```

---

## ⚠️ CRITICAL: Pre-Deployment Data Check

> **As of plan creation: production has no valuable data, migration skipped.**
>
> **BEFORE DEPLOYMENT YOU MUST:**
> 1. **Take a full database dump** — guarantees 100% safe rollback to previous state
> 2. Query production: `SELECT COUNT(*) FROM threads WHERE stage != 'new'`
> 3. Query production: `SELECT COUNT(*) FROM threads WHERE metadata->>'custom_fields' != '{}'`
> 4. Query production: `SELECT COUNT(*) FROM threads WHERE assignee_id IS NOT NULL`
> 5. If ANY rows exist — DATA MIGRATION IS REQUIRED (see Appendix A)
> 6. Get explicit confirmation from stakeholder that data loss is acceptable
>
> **SKIPPING THIS CHECK WILL RESULT IN DATA LOSS.**

---

### Phase 2: API Updates (Backend)

**Goal:** Order-centric API while maintaining backward compatibility.

**2.1 New Order endpoints:**

```
POST   /api/v1/companies/{company_id}/orders              # Create order
GET    /api/v1/companies/{company_id}/orders              # List orders  
GET    /api/v1/companies/{company_id}/orders/{id}         # Get order
PATCH  /api/v1/companies/{company_id}/orders/{id}         # Update order (stage, name)
PUT    /api/v1/companies/{company_id}/orders/{id}/assignee  # Update order assignee
POST   /api/v1/companies/{company_id}/orders/{id}/close   # Close order

GET    /api/v1/companies/{company_id}/customers/{id}/orders  # Customer order history
```

**2.2 Remove Thread stage and assignee endpoints:**

- Delete `PATCH /threads/{id}/stage` — moved to Order
- Delete `PUT /threads/{id}/assignee` — moved to Order

**2.3 Internal API for Sales-Agent (new orders module):**

```
PATCH  /internal/orders/{order_id}/stage      # AI updates stage
PATCH  /internal/orders/{order_id}/fields     # AI updates order_fields
GET    /internal/orders/by-thread/{thread_id} # Returns order context for thread
```

**2.4 Order context endpoint (for Sales-Agent):**

```python
# backend/modules/orders/routers.py

@internal_router.get("/by-thread/{thread_id}")
async def get_order_by_thread(thread_id: str) -> OrderContext:
    """Get order context for a thread."""
    thread = await Thread.get_or_none(thread_id=thread_id).select_related("active_order")
    if not thread or not thread.active_order:
        raise HTTPException(404, "No active order for thread")
    order = thread.active_order
    return OrderContext(
        order_id=order.id,
        order_stage=order.stage.value,
        order_fields=order.order_fields,
    )
```

### Phase 3: Sales-Agent Updates

**Goal:** AI tools work with Orders instead of Threads.

**3.1 Replace `update_stage` tool:**

```python
# OLD: apps/sales-agent/src/sales_agent/agents/tools.py

async def update_stage(thread_id: str, stage: str) -> UpdateStageResponse:
    backend = get_backend_client()
    result = await backend.update_thread_stage(thread_id=thread_id, stage=stage)
    return UpdateStageResponse(...)

# NEW:

async def update_order_stage(order_id: str, stage: str) -> UpdateOrderStageResponse:
    """Update current order stage.
    
    Args:
        order_id: Order identifier (AI receives this in context, passes explicitly)
        stage: New stage name
    """
    backend = get_backend_client()
    result = await backend.update_order_stage(order_id=order_id, stage=stage)
    return UpdateOrderStageResponse(...)
```

**3.2 New `update_order_fields` tool:**

```python
async def update_order_fields(
    order_id: str,
    fields: dict[str, Any],
) -> UpdateOrderFieldsResponse:
    """Update order-level fields (deal details).
    
    Args:
        order_id: Order identifier
        fields: Dictionary of field_name -> value
    """
    backend = get_backend_client()
    result = await backend.update_order_fields(order_id=order_id, fields=fields)
    return UpdateOrderFieldsResponse(...)
```

**3.3 Pipeline changes:**

```python
# apps/sales-agent/src/sales_agent/agents/pipeline.py

# OLD:
thread_id_from_meta = message.metadata.get("thread_id")
stage_name, stage_id = _snapshot_stage(customer_answers)

# NEW:
context = message.metadata.get("context", {})
order_id = context.get("order_id")
order_stage = context.get("order_stage")
```

**Note:** Backend must inject `order_id` into message metadata when forwarding to Sales-Agent. Currently only `thread_id` is passed.

**3.4 Tool registry changes:**

```python
# apps/sales-agent/src/sales_agent/core/tools/registry.py

TOOL_SCHEMAS = {
    # ...
    "update_order_stage": {
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "Order ID (from context)"},
            "stage": {"type": "string", "description": "New stage name"},
        },
        "required": ["order_id", "stage"],
    },
    "update_order_fields": {
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "Order ID (from context)"},
            "fields": {"type": "object", "description": "Order fields to update"},
        },
        "required": ["order_id", "fields"],
    },
}
```

### Phase 4: Cleanup

**Goal:** Final cleanup pass.

- [ ] Remove old `update_stage` tool from Sales-Agent (replaced in Phase 3)
- [ ] Verify frontend uses Order APIs
- [ ] Remove any leftover Thread.stage references

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Data loss on deploy** | Existing threads lose stage/custom_fields/assignee | Pre-deployment check (see warning above) |
| Frontend coupling | UI uses Thread.stage and Thread.assignee | Frontend updated in sync with backend |
| Multi-order edge cases | Customer writes after order closed | Create new Order automatically on new message |
| Sales-Agent context | Needs order_id, has thread_id | Backend provides order_id in context endpoint |
| Concurrent order_number | Race condition | Use DB sequence or application-level locking (see note below) |

> **Note on order_number generation:** Tortoise ORM doesn't support `SELECT ... FOR UPDATE` in aggregations. Options:
> 1. Use PostgreSQL sequence: `CREATE SEQUENCE order_number_seq_{company_id}`
> 2. Use Redis-based distributed lock before insert
> 3. Handle `IntegrityError` on unique constraint violation and retry

---

## Order Lifecycle Rules

### When Order is Created

1. **New message arrives** — `OrderService.ensure_active_order(thread)` checks/creates Order
2. **Customer returns** — Thread exists but `active_order.closed_at` is set → create new Order
3. **Manual creation** — Manager creates Order via UI

**Implementation: Dedicated OrderService**

```python
# backend/modules/orders/service.py

class OrderService:
    async def ensure_active_order(self, thread: Thread) -> Order:
        """Ensure thread has an active order, creating one if needed.
        
        Called from message router AFTER get_or_create_thread().
        Keeps thread logic and order logic separated.
        """
        if thread.active_order_id:
            order = await Order.get(id=thread.active_order_id)
            if order.closed_at is None:
                return order  # Active order exists
            # Order is closed, create new one
        
        # Create new order
        order = await self._create_order(thread)
        thread.active_order = order
        await thread.save(update_fields=["active_order_id"])
        return order
    
    async def _create_order(self, thread: Thread) -> Order:
        order_number = await self._next_order_number(thread.company_id)
        return await Order.create(
            order_number=order_number,
            customer_id=thread.customer_id,
            company_id=thread.company_id,
            initial_channel=thread.channel_type,
        )
```

**Call site: Message router (not get_or_create_thread)**

```python
# backend/modules/messages/routers.py

thread, created = await chat_service.get_or_create_thread(...)  # unchanged
order = await order_service.ensure_active_order(thread)  # NEW

internal_request = InternalInboundRequest(
    envelope=envelope,
    context=context,
    thread_id=thread.thread_id,
    order_id=order.id,  # NEW
)
```

**Contract change:** `InternalInboundRequest` (libs/common) must add `order_id` field.

### When Order is Closed

1. **Manual close** — Manager calls `POST /orders/{id}/close`
2. **Closed stage** — Order moves to `OrderStage.CLOSED`
3. **Result set** — Order.result set to WON or LOST

### Active Order Query

```python
async def get_active_order(customer_id: int) -> Order | None:
    return await Order.filter(
        customer_id=customer_id,
        closed_at__isnull=True,
    ).first()
```

---

## Acceptance Criteria

### Phase 1
- [ ] `backend/modules/orders/` module with Order model and OrderService
- [ ] Thread has `active_order_id` column
- [ ] Thread.stage column removed
- [ ] Thread.assignee column removed (moved to Order)
- [ ] Order.assignee_id column added
- [ ] `OrderService.ensure_active_order()` implemented
- [ ] Message router calls `ensure_active_order()` after `get_or_create_thread()`
- [ ] `InternalInboundRequest` extended with `order_id` field
- [ ] Existing tests updated and pass

### Phase 2
- [ ] Order CRUD endpoints work (including assignee management)
- [ ] Thread stage endpoint removed
- [ ] Thread assignee endpoint moved to Order (`PUT /orders/{id}/assignee`)
- [ ] Order context endpoint works (`/internal/orders/by-thread/{thread_id}`)

### Phase 3
- [ ] `update_order_stage` tool works
- [ ] `update_order_fields` tool works
- [ ] Sales-Agent receives order context
- [ ] Tests updated (see list below)

### Test Files Requiring Updates

| File | What to update |
|------|----------------|
| `backend/tests/domains/chat/test_thread_stage_update.py` | Rename to order stage tests |
| `backend/tests/domains/chat/test_handoff.py` | Update order context |
| `sales-agent/tests/domains/agents/test_update_stage_tool.py` | → `test_update_order_stage_tool.py` |
| `sales-agent/tests/domains/services/test_backend_client_stage.py` | Order endpoints |
| `sales-agent/tests/domains/services/test_backend_client_handoff.py` | Order context |
| `sales-agent/tests/domains/services/test_backend_client.py` | General client tests |
| `libs/common/tests/models/test_outbound.py` | `InternalInboundRequest.order_id` |
| `scripts/manual_testing/test_assignee.py` | Update for Order.assignee |

### Phase 4
- [ ] No Thread.stage references remain
- [ ] No Thread.assignee references remain
- [ ] Frontend uses Order APIs (stage + assignee)
- [ ] Old Sales-Agent tools removed

---

## Dependencies

- **Blocked by:** Nothing — can start immediately
- **Parallel:** Frontend Order UI work can start after Phase 2

---

## Manual Test Scenarios

Create a test script similar to `scripts/manual_testing/` to automate these.

### Scenario 1: New Customer Flow
**Goal:** First message creates Thread + Order

1. `POST /inbound` — new user_id, new conversation
2. Verify: Thread created with `active_order_id` set
3. Verify: Order exists with `stage=new`, `closed_at=null`
4. `GET /internal/orders/by-thread/{thread_id}` — returns order context

### Scenario 2: Returning Customer (Active Order)
**Goal:** Same customer, same order continues

1. `POST /inbound` — same user_id as Scenario 1
2. Verify: Same Thread, same Order (no new records)
3. `PATCH /internal/orders/{order_id}/stage` — change to `qualification`
4. Verify: Order.stage updated

### Scenario 3: Returning Customer (Closed Order)
**Goal:** Customer with closed order gets new order

1. `POST /orders/{order_id}/close` — close the order from Scenario 2
2. Verify: Order.closed_at is set
3. `POST /inbound` — same user_id sends new message
4. Verify: NEW Order created, Thread.active_order_id updated
5. Verify: Old Order still exists (deal history preserved)

### Scenario 4: Sales-Agent Tool Flow
**Goal:** AI can update order stage/fields

1. `GET /internal/orders/by-thread/{thread_id}` — get order_id
2. `PATCH /internal/orders/{order_id}/stage` — set to `offer`
3. `PATCH /internal/orders/{order_id}/fields` — set arbitrary fields
4. `GET /orders/{order_id}` — verify changes persisted

### Scenario 5: Order CRUD
**Goal:** Basic order management works

1. `GET /companies/{id}/orders` — list orders (should include test orders)
2. `GET /companies/{id}/customers/{id}/orders` — customer deal history
3. `PATCH /orders/{order_id}` — update name
4. `POST /orders/{order_id}/close` — close with result=won

### Scenario 6: Edge Cases

| Case | Test |
|------|------|
| Thread without order | `GET /internal/orders/by-thread/{id}` returns 404 |
| Invalid stage value | `PATCH /orders/{id}/stage` with garbage → 400 |
| Close already closed | `POST /orders/{id}/close` on closed order → 400 or idempotent 200 |
| Concurrent order_number | Spam `POST /inbound` for same company → no duplicate order_numbers |

### Pre-Deploy Smoke Test

Run in this order on staging:
1. Scenarios 1-5 pass
2. `SELECT COUNT(*) FROM orders` matches expected
3. `SELECT COUNT(*) FROM threads WHERE active_order_id IS NULL` = 0 (if data migrated)
4. Sales-Agent processes message end-to-end with new tools

---

## Appendix A: Data Migration (If Needed)

If pre-deployment check reveals existing data, run this before schema changes:

```python
async def migrate_threads_to_orders():
    """Create Order for each Thread, copying stage, custom_fields, and assignee."""
    threads = await Thread.all().select_related("customer", "customer__company")
    
    for thread in threads:
        order_number = await get_next_order_number(thread.customer.company_id)
        order = await Order.create(
            order_number=order_number,
            customer=thread.customer,
            company=thread.customer.company,
            assignee_id=thread.assignee_id,  # migrate assignee to order
            stage=thread.stage,
            order_fields=thread.metadata.get("custom_fields", {}),
            initial_channel=thread.channel_type,
            created_at=thread.created_at,
        )
        thread.active_order = order
        await thread.save(update_fields=["active_order_id"])

async def get_next_order_number(company_id: int) -> int:
    result = await Order.filter(company_id=company_id).annotate(
        max_num=Max("order_number")
    ).values("max_num")
    current_max = result[0]["max_num"] if result and result[0]["max_num"] else 0
    return current_max + 1
```
