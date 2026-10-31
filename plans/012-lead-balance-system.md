# Lead Balance System Plan

## Objective
Implement a billing system where companies have a Lead Balance (integer ≥ 0) measured in "lead units". The system tracks balance top-ups (manual admin operations), charges for processed leads (new threads), enforces zero-balance restrictions, maintains an audit ledger. Each new thread creation charges exactly 1 lead unit (constant pricing).

## Proposed Steps

### 1. Data Model & Schema (Backend)
- Create `company_balances` table in backend schema:
  - `company_id` (FK to companies, unique)
  - `balance` (integer, default 0, check constraint ≥ 0)
  - `updated_at` (timestamp)
  - Index on `company_id`
- Create `balance_ledger` table for audit trail:
  - `id` (primary key)
  - `company_id` (FK)
  - `operation_type` (enum: `top_up`, `charge`)
  - `amount` (integer: positive for top_up, negative for charge)
  - `timestamp` (timestamp, default now)
  - `initiated_by` (enum: `system`, `operator`, `admin`)
  - `operator_id` (nullable FK to `CompanyUser`, for manual operations)
  - `comment` (text, nullable)
  - `thread_id` (nullable FK to threads, for charge operations)
  - `channel_type` (text, nullable, for charge operations - denormalized for querying)
  - `conversation_id` (text, nullable, for charge operations - denormalized for querying)
  - Indexes on `(company_id, timestamp)`, `(thread_id)` for lookups
  - Idempotency: application-level check before insert (query ledger by thread_id)

**AICODE-NOTE:** No separate `processed_clients` table needed. Charge detection uses:
- Thread uniqueness: `(company_id, channel_type, conversation_id)` already enforced by Thread model
- Ledger query: Check if `thread_id` exists in `balance_ledger` with `operation_type='charge'`
- This keeps data model unified and avoids redundancy

### 2. Charge Detection Logic
- **Charge trigger**: On Thread creation (when `get_or_create_thread` creates a new thread)
- **Uniqueness**: Each thread is charged exactly once (idempotent via application-level check before insert)
- **Charge amount**: Constant 1 lead unit per thread (no per-company pricing in v1)
- **Detection flow**:
  1. Transport module sends message → Backend `/messages/inbound` endpoint receives request
  2. Backend calls `ChatService.get_or_create_thread()` to get/create thread
  3. If thread is newly created (`created=True`), Backend checks balance and charges BEFORE forwarding to sales-agent
  4. Charge service checks ledger: if `thread_id` already has charge entry, return success (idempotent)
  5. If new charge: check balance, decrement if > 0, create ledger entry, update thread `billing_status`
  6. Only if charge succeeds (or thread already charged): Backend forwards message to sales-agent
  7. If balance = 0: Backend does NOT forward to sales-agent, returns appropriate response

**AICODE-NOTE:** Thread-aware charging aligns with future Orders model separation. Each thread represents a distinct lead/order opportunity, making this the natural billing unit.

**AICODE-NOTE:** Sales-agent is completely unaware of billing. All balance checks and charges happen in Backend router layer before forwarding. This keeps concerns separated and sales-agent focused on AI processing only.

### 3. Balance Top-Up API (Backend)
- `POST /api/v1/billing/top-up` (admin/operator auth required):
  - Request: `company_id`, `amount` (integer > 0), `comment` (optional), `operator_id`
  - Validates company exists, amount > 0
  - **Transaction**: Atomically increments `company_balances.balance` and creates `balance_ledger` entry
  - Creates `balance_ledger` entry with `operation_type=top_up`, `amount=+N`, `initiated_by=operator/admin`
  - Returns updated balance and ledger entry ID
- `GET /api/v1/billing/balance/{company_id}`: returns current balance
- `GET /api/v1/billing/ledger/{company_id}` (paginated): returns ledger history

### 4. Charge Logic Integration

#### 4.1 Charge Service Method
- **Internal method**: `BillingService.charge_for_thread()` (not exposed as HTTP endpoint)
  - Parameters: `company_id`, `thread_id`, `channel_type`, `conversation_id`
  - **Idempotent**: If `thread_id` already charged (exists in ledger), return success with existing entry
  - Returns: `ChargeResult` with `success` (bool), `new_balance` (int), `ledger_entry_id` (nullable), `already_charged` (bool), `billing_status` (enum)

**AICODE-NOTE:** Charge logic is internal to Backend. No HTTP endpoint needed - called directly by message router. Sales-agent never calls billing APIs.

#### 4.2 Transaction Boundaries & Error Handling
**Charge transaction flow** (all-or-nothing):
1. **Start transaction** (database-level isolation)
2. **Check idempotency**: Query ledger for existing charge by `thread_id`
   - If exists: return success, commit transaction
3. **Check balance**: Read `company_balances.balance` with row-level lock
   - If balance = 0: set thread `billing_status='billing_hold'`, create ledger entry with `amount=0` (record attempt), commit, return failure
4. **Execute charge**: 
   - Decrement `company_balances.balance` (atomic update with WHERE balance > 0)
   - Create `balance_ledger` entry (`operation_type=charge`, `amount=-1`, link to thread)
   - Thread `billing_status` remains `active` (default value)
   - Update thread `charged_at` timestamp
5. **Commit transaction**

**Error scenarios**:
- Balance check passes but decrement fails (concurrent charge): Transaction rolls back, retry logic handles
- Ledger entry creation fails: Transaction rolls back, no charge applied
- Thread update fails: Transaction rolls back, no charge applied
- **Critical**: If transaction fails, thread remains in pre-charge state, can be retried

**AICODE-NOTE:** Use database transactions with appropriate isolation level (READ COMMITTED or SERIALIZABLE) to prevent race conditions. Row-level locks on `company_balances` prevent concurrent balance modifications.

#### 4.3 Integration Point
- **Hook location**: `MessagesRouter.inbound_message()` in `/messages/inbound` endpoint
  - Flow:
    1. Validate connector/auth (existing logic)
    2. Call `ChatService.get_or_create_thread()` to get/create thread
    3. Save message to DB (existing logic)
    4. Existing routing checks: historical → manager → assistant_inactive (existing logic)
    5. **Billing check** (after assistant_inactive, before sync check):
       - **If `created=True`**: Call `BillingService.charge_for_thread()`
         - If charge fails (balance=0): Set `billing_status='billing_hold'`, return `202 Accepted`
       - **If `created=False`**: Check `thread.billing_status`
         - If `billing_status='billing_hold'`: Return `202 Accepted`
    6. Sync status check (existing logic)
    7. Forward to sales-agent

**AICODE-NOTE:** Billing check placed after `assistant_inactive` check because historical/manager messages already return early - billing only matters for messages that would otherwise be forwarded.

### 5. Zero Balance Behavior
- When balance = 0 and new thread created:
  - Charge attempt creates ledger entry with `amount=0` (records the attempt)
  - Thread `billing_status` set to `'billing_hold'`
  - **Backend does NOT forward message to sales-agent** (router blocks forwarding)
  - Backend returns `202 Accepted` to transport module (message accepted, but processing blocked)
  - Backend API exposes `billing_status` in thread responses
- UI Warning: `GET /api/v1/billing/balance/{company_id}` returns `balance_warning: true` when balance = 0; frontend displays: "Lead balance = 0, auto-processing stopped"
- **Future hook**: Balance threshold alerts (see §9) - predefined but not implemented in v1

**AICODE-NOTE:** Sales-agent never sees messages for threads with zero balance. Backend router enforces this at the ingress point, keeping sales-agent completely unaware of billing restrictions.

### 6. Thread Model Updates
- Add `billing_status` field to threads table:
  - Type: non-nullable enum `BillingStatus` with values: `active`, `billing_hold`
  - Default: `active` (all threads start as active)
  - `active` = charged successfully OR legacy thread, processing allowed
  - `billing_hold` = charge failed due to zero balance, processing blocked
- Add `charged_at` timestamp (nullable) linking to charge ledger entry timestamp
- Update thread retrieval endpoints to include `billing_status` and `charged_at`
- Update thread filtering to support `billing_status` filter

**AICODE-NOTE:** Separate `billing_status` enum keeps billing concerns isolated from business `ThreadState`. This allows independent lifecycle management and future extensibility. No NULL values - simpler logic.

### 7. Audit & Reporting
- Ledger entries capture all operations with full context:
  - Top-ups: who (`operator_id`), when (`timestamp`), amount, comment
  - Charges: thread_id, channel_type, conversation_id, timestamp
- `GET /api/v1/billing/ledger/{company_id}` supports filtering by:
  - `operation_type` (top_up/charge)
  - Date range (`from`, `to`)
  - `thread_id` (for charge lookups)
- Response includes pagination metadata
- Ledger is append-only; no deletions or modifications allowed

### 8. Balance Threshold & Alerting Hooks (Future)
**Predefined hook points** (not implemented in v1, reserved for future):
- **Hook location**: `BillingService` after balance update operations
  - After successful top-up: Check if balance crossed threshold (e.g., from below 10 to above 10)
  - After successful charge: Check if balance dropped below threshold (e.g., from above 10 to 10 or below)
- **Hook interface** (to be implemented):
  ```python
  async def on_balance_threshold_crossed(
      company_id: int,
      old_balance: int,
      new_balance: int,
      threshold: int,
      direction: str  # "above" or "below"
  ) -> None:
      """Called when balance crosses predefined threshold.
      
      Future implementation: Send notifications, trigger alerts, etc.
      """
      pass
  ```
- **Configuration**: Threshold values stored in company metadata or config (out of scope v1)
- **AICODE-NOTE:** Hook is defined but not called in v1. Placeholder ensures future extensibility without schema changes.

### 9. Integration Points
- **Backend MessagesRouter** (`/messages/inbound` endpoint):
  - Receives messages from transport modules
  - Calls `ChatService.get_or_create_thread()` to get/create thread
  - Calls `BillingService.charge_for_thread()` if thread newly created
  - **Router logic**: Only forwards to sales-agent if charge succeeds (or thread already charged)
  - Blocks forwarding if `billing_status='billing_hold'` or charge fails
- **Backend ChatService**: 
  - `get_or_create_thread()` unchanged - returns thread and `created` flag
  - Thread queries include `billing_status` filter support
- **Backend BillingService**: 
  - Internal `charge_for_thread()` method (not HTTP endpoint)
  - Exposes balance APIs (`GET /api/v1/billing/balance/{company_id}`, etc.)
  - Maintains ledger, enforces atomicity
  - Handles charge logic with transaction boundaries
- **Sales Agent**: 
  - **No changes required** - completely unaware of billing
  - Receives messages only for threads that passed billing check
  - No billing-related logic in sales-agent codebase
- **Transport modules**: No changes required (balance logic is backend concern only)

### 10. Migration Strategy

#### 10.1 Schema Migration
- Create `company_balances` table with default balance = 0 for all existing companies
- Create `balance_ledger` table (empty initially)
- Add `billing_status` (non-nullable, default `active`) and `charged_at` (nullable) to `threads` table
- All existing threads: `billing_status='active'`, `charged_at=NULL` (grandfathered)

#### 10.2 Data Migration
- **Existing companies**: All start with `balance=0` (no free credits)
- **Existing threads**: 
  - Set `billing_status='active'` (grandfathered - no retroactive charges)
  - Set `charged_at=NULL` (not charged through billing system)
  - **Legal status**: These threads existed before billing system, so no retroactive charges
  - Sales Agent continues processing existing threads normally
- **New threads**: All new threads created after migration go through charge flow

#### 10.3 Backward Compatibility
- **Backend router logic**: Only blocks forwarding if `billing_status='billing_hold'`
- Existing threads have `billing_status='active'` → forwarding allowed
- **Sales-agent**: No changes required - continues processing all messages it receives
- This ensures existing threads continue working without modification

**AICODE-NOTE:** Migration sets existing threads to `active` status. No NULL handling needed - simpler logic. Sales-agent remains unchanged - it only processes messages that Backend router forwards to it.

## Risks / Open Questions

- **Charge retry logic**: If charge transaction fails (network, deadlock), retry with exponential backoff (max 3 attempts).
- **Partial unique index** (deferred): Ledger constraint `(thread_id) WHERE operation_type='charge'` would require raw SQL. For now, idempotency is handled in application code (check ledger before insert). Can add partial index later if needed for performance.

## Out of Scope (v1)

- Self-serve payment/top-up (admin-only in v1)
- Returns/refunds for disputed charges
- Exceptions/waivers (manual work only - admin can top-up to compensate)
- Per-company pricing (constant 1 lead unit per thread)
- Balance threshold alerts/notifications (hook defined but not implemented)
- Auto-message to clients when balance = 0 (optional policy, defer to v2)
- Re-processing of `billing_hold` threads after top-up (defer to v2)
- Historical thread retroactive charging (grandfathered as `active` status)

---

## Implementation Notes

### Codebase Integration Points

- **Thread creation**: `ChatService.get_or_create_thread()` in `chat/service.py` returns `tuple[Thread, bool]`
- **Message router**: `inbound_message()` in `messages/routers.py` calls `get_or_create_thread()` then forwards via `sales_agent_client.forward_inbound()`
- **Auth**: Use `CompanyAdminDep` for top-up endpoint
- **operator_id**: FK to `CompanyUser`

### Transaction & Locking

```python
from tortoise.transactions import in_transaction

async with in_transaction() as connection:
    balance_row = await CompanyBalance.filter(company_id=company_id).select_for_update().using_db(connection).first()
    # ... atomic operations
```

### billing_hold Check Placement in Router

Add after `assistant_active` check, before sync check. This ensures billing_hold only affects messages that would otherwise be forwarded:

```python
# After: if not thread.assistant_active check
# Before: sync status check

if thread.billing_status == BillingStatus.BILLING_HOLD:
    log.info("ingress.routing.skipped", reason="billing_hold", thread_id=thread.thread_id)
    return {"status": "accepted"}
```

### Migration Notes

- Schema prefix: Aerich does NOT auto-add schema qualifiers. Manually prefix all table references with `"backend"` in migration files.
- CompanyBalance initialization for existing companies handled in migration.

### Files to Create/Modify

**New files:**
- `apps/backend/src/backend/modules/billing/__init__.py`
- `apps/backend/src/backend/modules/billing/models.py` (CompanyBalance, BalanceLedger, BillingStatus, OperationType, InitiatedBy enums)
- `apps/backend/src/backend/modules/billing/repository.py`
- `apps/backend/src/backend/modules/billing/service.py` (BillingService with charge_for_thread)
- `apps/backend/src/backend/modules/billing/routers.py` (top-up, balance, ledger endpoints)
- `apps/backend/src/backend/modules/billing/schemas.py` (request/response models)
- `apps/backend/src/backend/modules/billing/dependencies.py`
- `apps/backend/migrations/models/XX_YYYYMMDDHHMMSS_add_billing_tables.py`

**Modified files:**
- `apps/backend/src/backend/modules/chat/models.py` (add BillingStatus enum, billing_status + charged_at fields to Thread)
- `apps/backend/src/backend/modules/messages/routers.py` (add billing check in inbound_message)
- `apps/backend/src/backend/modules/__init__.py` (register billing router)
- `apps/backend/src/backend/modules/core/models.py` (import billing models for Tortoise discovery)
