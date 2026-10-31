# Stage Integration Tests

End-to-end integration tests for the complete stage system.

## Structure

- **`test_full_funnel_flow.py`** — Complete flows from company creation to order close
- **`test_complex_conditions.py`** — Complex condition operators in real scenarios

## Test Coverage

### Full Funnel Flow (`test_full_funnel_flow.py`)
- ✅ Company creation → default stages → order → fill fields → auto-close
- ✅ Order rejected flow (lost stage)
- ✅ Multiple orders same customer move independently
- ✅ Customer field updates affect all orders
- ✅ Frozen order isolation
- ✅ Stage deletion nullifies orders

### Complex Conditions (`test_complex_conditions.py`)
- ✅ `$stage_completed` operator
- ✅ `$prev_stage_completed` operator
- ✅ Nested `$and`/`$or` conditions
- ✅ `$not` operator
- ✅ Comparison operators (`$gt`, `$gte`, `$lt`, `$lte`)
- ✅ `$exists` operator with null values
- ✅ `$eq` and `$ne` operators
- ✅ Multiple transitions in sequence
- ✅ Condition evaluation error handling

## Running Tests

```bash
# All integration tests
uv run pytest tests/integration/stages/ -v

# Full flow tests only
uv run pytest tests/integration/stages/test_full_funnel_flow.py -v

# Complex conditions only
uv run pytest tests/integration/stages/test_complex_conditions.py -v

# Specific test
uv run pytest tests/integration/stages/test_full_funnel_flow.py::test_full_funnel_from_company_creation_to_order_close -v
```

## What These Tests Validate

These integration tests ensure:

1. **System Integration** — All components work together (stages, orders, customers, chat)
2. **Real-World Scenarios** — Tests mirror actual user workflows
3. **Data Consistency** — Stage changes propagate correctly through the system
4. **Edge Cases** — Frozen orders, deleted stages, complex conditions all handled
5. **Performance** — Multiple orders, bulk recalculations work efficiently

## Test Data

Tests use real fixtures from `tests/domains/*/conftest.py`:
- `company` — Real company instance
- `test_superuser` — Superuser for company creation
- `stage_templates` — 5-stage funnel (Новый → Квалификация → Предложение → Закрыто/Отказ)

## Coverage Goals

- ✅ All Phase 0-6 features from plan
- ✅ Cross-module interactions (orders ↔ stages ↔ chat)
- ✅ Condition engine in realistic contexts
- ✅ Auto-transition triggers (order fields, customer fields)
- ✅ Manual controls (freeze, recalculate)

