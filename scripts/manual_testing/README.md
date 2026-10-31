# Manual Testing Scripts

Interactive scripts for manual API testing and feature verification.

## Quick Start

```bash
cd scripts/manual_testing
python test_tasks.py      # Tasks & Reminders
python test_orders.py     # Order Model
python test_connectors.py # Unified Connectors
```

## Prerequisites

1. **Backend running:**
   ```bash
   docker-compose up -d backend redis postgres
   ```

2. **Superuser created:**
   ```bash
   cd apps/backend && uv run python scripts/create_superuser.py \
       --email user@example.com \
       --password YOUR_PASSWORD \
       --superuser
   ```
   *(Replace placeholders with your actual credentials)*

3. **Environment (optional):**
   ```bash
   export BACKEND_URL="http://localhost:8081"
   export TEST_EMAIL="your-email@example.com"
   export TEST_PASSWORD="your-password"
   export SERVICE_API_KEY="your-api-key"
   ```

## Available Tests

| Script | Feature | Plan |
|--------|---------|------|
| `test_tasks.py` | Tasks & Reminders | Plan 027 |
| `test_orders.py` | Order Model Extraction | Plan 018 |
| `test_forms_capture.py` | Web Form Capture | Plan 024 |
| `test_connectors.py` | Unified Connector Model | Plan 009 |
| `test_assignee.py` | Thread Assignee | - |
| `test_field_level_separation.py` | Field Levels | - |
| `test_pagination_sanity.py` | Pagination Endpoints | - |
| `test_stage_transitions.py` | Stage Transitions & Condition Engine | Plan 037 |
| `test_auto_pings.py` | Stage-Based Auto-Pings | Plan 039 |

## Framework

New tests should use the framework in `framework/`:

```python
from framework import BaseTestClient, Scenario, run_scenarios, success, error

class MyClient(BaseTestClient):
    async def my_method(self) -> dict:
        return await self.post(f"/companies/{self.company_id}/endpoint", json={...})

async def scenario_1(client: MyClient) -> bool:
    result = await client.my_method()
    if result["status"] == "ok":
        success("Method works")
        return True
    error("Method failed")
    return False

if __name__ == "__main__":
    run_scenarios(
        MyClient,
        [Scenario("Test Name", scenario_1)],
        title="My Test",
        description="Tests for Feature X",
        company_name="Test Company",
    )
```

See `.cursor/rules/manual-testing.mdc` for detailed guidelines.

## Framework Components

| Module | Purpose |
|--------|---------|
| `framework/client.py` | `BaseTestClient` with auth, company, thread methods |
| `framework/config.py` | Centralized configuration from environment |
| `framework/output.py` | Rich console helpers: `success()`, `error()`, `print_table()` |
| `framework/scenarios.py` | `Scenario`, `run_scenarios()`, `interactive_menu()` |
| `framework/setup.py` | `setup_environment()` for common setup |

## Service Ports

| Service | Port |
|---------|------|
| Backend | 8081 |
| Sales-agent | 8080 |
| Redis | 6379 |
| Postgres | 5432 |
