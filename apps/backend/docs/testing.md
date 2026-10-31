# Backend Testing Playbook

## Objective
- Freeze current behaviour before refactoring routers by domain.
- Guarantee SQLite-only test data with zero production correlation.
- Surface contract regressions instantly (status codes, payload shape, auth guard).

## Core Principles
- **Fail fast**: prefer explicit assertions over permissive matching.
- **Deterministic fixtures**: reuse `fastapi_app`, `api_client`, `service_headers`, payload factories.
- **Layer awareness**: cover both API routers and persistence layer (models/repositories) so contract breaks surface immediately.
- **Single responsibility per test**: each test defends one observable behaviour.

## Fixture Pattern
| Fixture | Purpose |
| --- | --- |
| `settings` (session) | Provides test-scoped config; ensures in-memory SQLite URL + service key. |
| `fastapi_app` (session) | Boots FastAPI once, runs migrations against SQLite, keeps lifespan hooks. |
| `api_client` (function) | HTTPX client with ASGI transport; always pass `service_headers`. |
| Payload factories | `company_payload`, `category_payload`, `product_payload` to avoid brittle inline dicts. |

### Usage
- Build data via services or repositories when bypassing HTTP is faster.
- Wrap helper creators for composite objects (e.g., `create_company(api_client, payload)`) inside `tests/helpers/`.
- Never share state across tests; rely on new transactions per test (`sqlite://:memory:?cache=shared` already resets DB when schemas re-run).

## Coverage Map
### Routers vs. Models
- Every router test must assert HTTP status, response schema, and side effects (new rows, cascading deletes).
- Every model/repository test must validate constraints: defaults, enum choices, cascades, unique indexes.
- When a router delegates to a service, pair an API test (contract) with a lower-level test (business rule) so failures pinpoint the layer.
- Examples mention specific domains (companies, categories, tools) purely illustratively—apply the same rigor to every router.

### Routers
1. **Companies (example)**
   - `POST /companies`: happy path + validation errors.
   - `GET /companies/{id}` and listing with pagination/sorting (if implemented).
   - `PATCH /companies/{id}` ensures partial updates respect required fields.
   - `DELETE /companies/{id}` returns 204 + cascades to dependent records.
2. **Categories & Products (example)**
   - CRUD endpoints plus linkage constraints (category-company ownership, product-category optionality).
   - Ensure category deletion rejects when products exist (current behaviour) or removes them if cascade set.
3. **Fields & Field Options (example)**
   - Create/update field types, enforce required `answer_type`, ensure ENUM fields block missing options.
   - Option ordering uniqueness.
4. **Prompts, FAQs, Tools (example)**
   - Unique constraints (agent_type, tool name).
   - Attach/detach tools to companies/categories.
5. **Transport APIs**
   - `GET /transport/connectors`, Telegram bots CRUD, Wappi connectors CRUD.
   - Header authentication: missing/invalid `X-Service-Key` gives 401; missing config returns 503.
6. **Health**
   - `/health` returns 200 without auth.

### Services & Repositories
- Repository methods that perform multi-step operations (e.g., `CompaniesRepository.update_with_relations`).
- Services that orchestrate HTTP calls (e.g., `ConnectorsService.create_connector`) using `httpx.AsyncClient` mocks.
- Validation utilities or helpers living outside routers.

### Models
- Directly instantiate Tortoise models for constraint checks (unique, nullability, reverse relations).
- Use database transactions inside tests to verify cascades (`await Company.all()` is empty after delete).
- Cover enumerations (`AnswerType`, `AgentType`, `ConnectorType`) to ensure invalid values raise `ValidationError`.

### Error Cases
- Schema validation: send malformed payloads to assert FastAPI 422 responses match expected body.
- Database constraints: duplicate names, missing foreign keys.
- Authorization: every transport endpoint must assert header enforcement (401 vs 503).

## Test Structure (forces future packet layout)
- Mirror the target domain packages:
  - `tests/domains/companies/test_routers.py`
  - `tests/domains/companies/test_models.py`
  - `tests/domains/categories/test_routers.py`, etc.
- Shared helpers live in `tests/common/`.
- Within each module:
  - Router tests grouped by HTTP verb (without classes; prefer plain functions).
  - Model tests grouped by entity using function prefixes (`def test_company_default_stage(): ...`).
- Use FastAPI’s `from fastapi.testclient import TestClient` or `from fastapi.encoders import jsonable_encoder` to avoid extra HTTP stacks; stick to built-in clients unless a specific feature requires httpx.
- Use Pydantic response models (`src.backend.api.schema`) for parsing nested payloads.

### Domain Package Scaffold (authoritative list)
All backend tests live under `tests/domains/<package>/` with four files per package unless explicitly noted:

| Package | Scope | Files |
| --- | --- | --- |
| `companies` | CRUD, CRM metadata, tool relations | `test_routers.py`, `test_models.py`, `test_services.py`, `test_repositories.py` |
| `categories` | Category CRUD, workflows | same |
| `products` | Product CRUD, category linkage | same |
| `fields` | Field CRUD, validation | same |
| `field_options` | Option ordering, uniqueness | same |
| `faqs` | FAQ CRUD, search helpers | same |
| `prompts` | Prompt CRUD + agent types | same |
| `tools` | Tool registry + bindings | same |
| `transport` | Unified connector CRUD, API keys, sync commands, auth guards | same |
| `health` | `/health` endpoint + readiness | only `test_routers.py` |

Each file begins with an `AICODE-TODO` anchor describing the first batch of tests to implement. When a package lacks a particular layer (e.g., `health` has no models), omit the unused file.

## Tooling & Commands
- Run module tests only: `uv run --directory apps/backend pytest`.
- Lint tests after substantial additions: `uv run ruff check tests`.
- Keep `pytest -k` subsets per domain when iterating (document command snippets in PRs if non-obvious).

## Future Enhancements
- Introduce factory module (e.g., `tests/factories.py`) to compose complex objects.
- Add contract snapshot tests (e.g., storing JSON Schema) once endpoints stabilize.

## Best Practices
- Reset state per test via fixtures; never rely on ordering.
- Assert both JSON payload and persisted rows.
- Prefer FastAPI’s `TestClient` for synchronous router hits; only use `httpx.AsyncClient` when the endpoint itself is async-only and needs ASGI transport.
- Mock external HTTP calls with `respx` or `pytest-httpx` instead of patching internals.
- Keep fixtures pure functions; push side effects into helper factories.
- Use descriptive test names (`test_delete_company_cascades_categories`) to highlight business rule.

## Avoid
- No implicit asserts (e.g., just calling endpoint without checking status/payload).
- No global mutable state shared across tests.
- No blanket mocking of repositories when testing routers—only mock edges (external HTTP, time).
- No skipping authorization checks; every transport handler must test 401/503 branches.
- No reliance on production database URLs or environment files beyond `.env.shared.test`.
- No test classes or inheritance hierarchies; pytest functions keep intent clear and avoid shared state.

