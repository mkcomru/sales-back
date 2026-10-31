Create manual test scenarios for the plan tagged above using the testing framework.

## Reference Documentation
- **Framework guide**: `scripts/manual_testing/.cursor/rules/manual-testing.mdc`
- **README**: `scripts/manual_testing/README.md`
- **Example**: `scripts/manual_testing/test_tasks.py` (refactored with framework)

## Pre-work
1. Read the plan — understand endpoints, models, validation rules
2. Read the framework rule file for patterns and conventions
3. Check `docker-compose.yml` for required service ports
4. Identify which services are required vs optional

## Output
`scripts/manual_testing/test_{feature}.py`

## Structure (use framework)

```python
from framework import BaseTestClient, Scenario, run_scenarios, console, success, error
from framework.output import print_scenario_header
from framework.scenarios import interactive_menu
from framework.setup import setup_environment

class FeatureClient(BaseTestClient):
    # Only feature-specific methods — common methods inherited
    async def create_feature(self, ...) -> dict:
        return await self.post(f"/companies/{self.company_id}/features", json={...})

async def scenario_1_basic_crud(client: FeatureClient) -> bool:
    print_scenario_header("Scenario 1: Basic CRUD", "Test create, read, update")
    # Test logic...
    return True

SCENARIOS = [
    Scenario("Basic CRUD", scenario_1_basic_crud, "Create, read, update"),
]

UTILITIES = [
    ("l", "List items", util_list),
]
```

## Scenarios (ordered by complexity)
1. **Basic CRUD** — Create, Read, Update operations
2. **Validation Rules** — Required fields, type consistency, 422 errors
3. **Lifecycle** — State transitions (complete, cancel, close)
4. **Filtering** — List endpoints with filters
5. **Edge Cases** — Idempotency, 404s, error handling
6. **Integration** — Cross-service flows (scheduler, workers)
7. **Isolation** — Data scoping (per-order, per-company)

## Mindset
- **Maximum coverage** — Every endpoint, every validation rule
- **Fail gracefully** — Report failures, don't crash
- **Clear output** — Pass/fail obvious at a glance

## After Creation
Update `scripts/manual_testing/README.md` table with the new test script.
