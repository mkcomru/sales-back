# Plan 019 — Billing Migration: Thread → Order

## Objective

Migrate billing logic from Thread to Order entity. Billing should be tied to deals/orders (business transactions), not communication channels. This aligns with order-centric architecture where one Customer can have multiple Orders, each requiring separate billing.

---

## Problem Statement

### Current State

Billing is tied to Thread (communication channel):
- `BalanceLedger.thread_id` — links charges to threads
- `Thread.billing_status` — billing status per thread
- `Thread.charged_at` — charge timestamp per thread
- `BillingService.charge_for_thread()` — charges per thread creation

**Issues:**
1. **Conceptual mismatch** — billing should be for deals/orders, not channels
2. **Multiple threads, one order** — customer can communicate via Telegram and WhatsApp for the same order, but billing is per-thread
3. **Order-centric architecture** — according to Plan 014 (yoolo-requirements-product-v4.md), Order is the central business entity

### Target State

Billing tied to Order:
- `BalanceLedger.order_id` — links charges to orders
- `Order.billing_status` — billing status per order
- `Order.charged_at` — charge timestamp per order
- `BillingService.charge_for_order()` — charges per order creation

**Benefits:**
- One charge per order, regardless of communication channels
- Aligns with order-centric CRM architecture
- Clearer billing semantics: "charge for new deal" vs "charge for new thread"

---

## Migration Steps

### Phase 1: Schema Changes

**1.1 Add order_id to BalanceLedger:**
```python
# backend/modules/billing/models.py

class BalanceLedger(BaseModel):
    # ... existing fields ...
    order: fields.ForeignKeyNullableRelation = fields.ForeignKeyField(
        "models.Order",
        related_name="ledger_charges",
        on_delete=fields.SET_NULL,
        null=True,
    )
    # ... rest of fields ...
    
    class Meta(BaseModel.Meta):
        indexes = (
            ("company_id", "timestamp"),
            ("order_id",),
        )
```

**1.2 Add billing fields to Order model:**
```python
# backend/modules/orders/models.py

class Order(BaseModel):
    # ... existing fields ...
    billing_status = fields.CharEnumField(BillingStatus, max_length=20, default=BillingStatus.ACTIVE)
    charged_at = fields.DatetimeField(null=True)
    # ... rest of fields ...
```

**1.3 Create migration:**
- Add `order_id` column to `balance_ledger` table
- Remove `thread_id` column from `balance_ledger` table (no production data)
- Add `billing_status` and `charged_at` columns to `orders` table
- Remove `billing_status` and `charged_at` columns from `threads` table
- Add index on `balance_ledger.order_id`

---

### Phase 2: Service Layer Updates

**2.1 Update BillingService:**

```python
# backend/modules/billing/service.py

class BillingService:
    # ... existing methods ...
    
    async def charge_for_order(
        self,
        company_id: int,
        order_id: int,
        channel_type: str,
        conversation_id: str | None = None,
    ) -> ChargeResult:
        """Charge company for order creation.
        
        Idempotent: if order already charged, returns success with existing entry.
        
        Args:
            company_id: Company ID
            order_id: Order database ID
            channel_type: Channel type (denormalized for querying)
            conversation_id: Conversation ID (denormalized for querying)
        
        Returns:
            ChargeResult with success status, balance, and billing_status
        """
        async with in_transaction() as connection:
            existing_charge = await self.ledger_repo.find_charge_by_order_id(order_id, connection)
            if existing_charge:
                # ... idempotency logic similar to charge_for_thread ...
            
            # ... charge logic similar to charge_for_thread, but update Order instead of Thread ...
            
            order = await Order.filter(id=order_id).using_db(connection).first()
            if order:
                order.billing_status = BillingStatus.ACTIVE
                order.charged_at = ledger_entry.timestamp
                await order.save(using_db=connection, update_fields=["billing_status", "charged_at"])
```

**2.2 Update LedgerRepository:**

```python
# backend/modules/billing/repository.py

class LedgerRepository:
    async def create_entry(
        self,
        company_id: int,
        operation_type: OperationType,
        amount: int,
        initiated_by: InitiatedBy,
        operator_id: int | None = None,
        comment: str | None = None,
        order_id: int | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        connection=None,
    ) -> BalanceLedger:
        # ... update to include order_id ...
    
    async def find_charge_by_order_id(self, order_id: int, connection=None) -> BalanceLedger | None:
        """Find existing charge entry for order (idempotency check)."""
        query = BalanceLedger.filter(order_id=order_id, operation_type=OperationType.CHARGE)
        if connection:
            return await query.using_db(connection).first()
        return await query.first()
```

---

### Phase 3: Integration Points

**3.1 Update message router:**

```python
# backend/modules/messages/routers.py

# OLD:
if created:
    charge_result = await billing_service.charge_for_thread(
        company_id=context.company_id,
        thread_id=thread.id,
        channel_type=context.channel_type,
        conversation_id=envelope.conversation_id,
    )

# NEW:
if created:
    order = await order_service.ensure_active_order(thread)
    charge_result = await billing_service.charge_for_order(
        company_id=context.company_id,
        order_id=order.id,
        channel_type=context.channel_type,
        conversation_id=envelope.conversation_id,
    )
```

**3.2 Update billing status checks:**

```python
# backend/modules/messages/routers.py

# OLD:
if thread.billing_status == BillingStatus.BILLING_HOLD:
    # ... skip processing ...

# NEW:
order = await order_service.ensure_active_order(thread)
if order.billing_status == BillingStatus.BILLING_HOLD:
    # ... skip processing ...
```

---

### Phase 4: Cleanup

**4.1 Remove deprecated code:**
- Remove `BillingService.charge_for_thread()` method
- Remove `LedgerRepository.find_charge_by_thread_id()` method

**4.2 Update tests:**
- Update `test_inbound_billing_charge_new_thread` → `test_inbound_billing_charge_new_order`
- Update all billing integration tests to use Order instead of Thread
- Update test fixtures to create Orders instead of relying on Thread billing

---

## Acceptance Criteria

### Phase 1
- [ ] `BalanceLedger.order_id` column added
- [ ] `BalanceLedger.thread` field removed
- [ ] `Order.billing_status` and `Order.charged_at` columns added
- [ ] `Thread.billing_status` and `Thread.charged_at` columns removed

### Phase 2
- [ ] `BillingService.charge_for_order()` implemented
- [ ] `LedgerRepository.find_charge_by_order_id()` implemented
- [ ] Idempotency works correctly

### Phase 3
- [ ] Message router uses `charge_for_order()` instead of `charge_for_thread()`
- [ ] Billing status checks use Order instead of Thread
- [ ] All integration points updated

### Phase 4
- [ ] Old `charge_for_thread()` removed
- [ ] `find_charge_by_thread_id()` removed
- [ ] All tests updated and passing

---

## Dependencies

- **Blocked by:** Plan 018 (Order Model Extraction) — Order model must exist first
- **Can proceed:** After Order model is created and `ensure_active_order()` is implemented

---

## Manual Test Scenarios

### Scenario 1: New Order Billing
1. Send inbound message → Order created
2. Verify: `BalanceLedger` entry created with `order_id` set
3. Verify: `Order.billing_status = ACTIVE`, `Order.charged_at` set
4. Verify: Company balance decremented

### Scenario 2: Idempotency
1. Send same message again (same order)
2. Verify: No duplicate charge, existing ledger entry returned
3. Verify: Balance unchanged

### Scenario 3: Insufficient Balance
1. Set company balance to 0
2. Send inbound message → Order created
3. Verify: `Order.billing_status = BILLING_HOLD`
4. Verify: Ledger entry created with `amount = 0`
5. Verify: Message processing skipped

### Scenario 4: Multiple Threads, One Order
1. Customer writes via Telegram → Order created, charged
2. Same customer writes via WhatsApp → Same Order, no new charge
3. Verify: Only one ledger entry for this order

