# Stages Tests

Tests for the custom stages & auto-transitions system.

## Structure

- **`conftest.py`** — Test fixtures for stages (stage_template, stage_templates, stages_service)
- **`test_routers.py`** — CRUD endpoints tests (create, update, delete, reorder stages)
- **`test_services.py`** — Service layer tests (validation, default stages creation, business logic)

## Test Coverage

### Routers (`test_routers.py`)
- ✅ List stages (empty and with data)
- ✅ Create stage with validation
- ✅ Position assignment (max + 1)
- ✅ Invalid condition validation
- ✅ Final stage constraints (requires result)
- ✅ Auto-close constraints (requires is_final)
- ✅ Update stage
- ✅ Delete stage (sets Order.stage to NULL)
- ✅ Reorder stages
- ✅ Get stage by ID

### Services (`test_services.py`)
- ✅ Create default stages (5 stages with fallback)
- ✅ Default stages on company creation
- ✅ Condition validation (valid/invalid)
- ✅ Create/update with validation
- ✅ Business rule validation (is_final, auto_close)
- ✅ List by company (sorted)
- ✅ Reorder stages
- ✅ Recalculate company orders

## Running Tests

```bash
# All stages tests
uv run pytest tests/domains/stages/ -v

# Specific test file
uv run pytest tests/domains/stages/test_routers.py -v

# Single test
uv run pytest tests/domains/stages/test_services.py::test_create_default_stages -v
```

## Fixtures Available

- `stages_repo` — StagesRepository instance
- `stages_service` — StagesService instance
- `stage_template` — Single stage template (position 0)
- `stage_templates` — Full funnel with 5 stages:
  - Новый (position 0, $any: True)
  - Квалификация (position 1, budget >= 1000)
  - Предложение (position 2, budget + city)
  - Закрыто (успешно) (position 3, deal_closed=True, is_final, auto_close)
  - Отказ (position 4, rejected=True, is_final, auto_close)

