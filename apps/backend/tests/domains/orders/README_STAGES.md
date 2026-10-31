# Order Stage Tests

Tests for auto-transitions, frozen orders, and stage management.

## Structure

- **`test_auto_transitions.py`** — Automatic stage transitions based on field updates
- **`test_frozen_orders.py`** — Frozen flag blocking auto-transitions
- **`test_stage_requirements.py`** — Stage requirements endpoint (what's needed for next stage)
- **`test_recalculate_stage.py`** — Manual stage recalculation

## Test Coverage

### Auto-Transitions (`test_auto_transitions.py`)
- ✅ New order gets initial stage
- ✅ Order transitions when condition met
- ✅ Order can skip stages (multiple conditions met)
- ✅ Order never moves backwards
- ✅ Logs auto-transition with trigger=auto
- ✅ Final stage with auto_close closes order
- ✅ Customer fields change triggers recalculation for all orders
- ✅ Closed orders don't recalculate
- ✅ Order without matching stage stays put
- ✅ Order via thread gets initial stage

### Frozen Orders (`test_frozen_orders.py`)
- ✅ Frozen order blocks auto-transitions
- ✅ Unfrozen order resumes transitions
- ✅ Freeze/unfreeze endpoints
- ✅ Frozen order skipped in customer_fields recalc
- ✅ Frozen at creation stays without stage
- ✅ Manual stage change works on frozen order

### Stage Requirements (`test_stage_requirements.py`)
- ✅ Shows missing fields for next stages
- ✅ Shows "met" when conditions satisfied
- ✅ Endpoint returns proper format
- ✅ Handles final stages (no next stages)
- ✅ Includes condition_status (met/partial/blocked)
- ✅ Handles complex nested conditions

### Recalculate Stage (`test_recalculate_stage.py`)
- ✅ Manual recalculate_stage() works
- ✅ Recalculate endpoint
- ✅ Company-wide recalculate endpoint
- ✅ Skips frozen orders
- ✅ Skips closed orders
- ✅ Handles no stages gracefully
- ✅ Moves to furthest matching stage
- ✅ Uses completed_stages context
- ✅ Error handling for non-existent order

## Running Tests

```bash
# All order stage tests
uv run pytest tests/domains/orders/test_auto_transitions.py tests/domains/orders/test_frozen_orders.py tests/domains/orders/test_stage_requirements.py tests/domains/orders/test_recalculate_stage.py -v

# Specific category
uv run pytest tests/domains/orders/test_auto_transitions.py -v

# Single test
uv run pytest tests/domains/orders/test_auto_transitions.py::test_new_order_gets_initial_stage -v
```

## Integration with Existing Tests

These tests complement existing:
- `test_order_logs.py` — Stage changes are logged
- `test_routers.py` — Order creation now assigns initial stage
- `conftest.py` — Fixtures work with new stage system

