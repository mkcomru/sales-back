# Sales Platform Monorepo — Claude Guide

> **Start here.** Read `AGENTS.md` for the full agent playbook. This file is the condensed reference.

---

## Project Overview

AI-driven sales automation platform. Monorepo (uv workspace) with multiple Python FastAPI services.

**Modules:**

| Module | Role | Port |
|--------|------|------|
| `apps/backend` | **CRM core** — companies, orders, billing, message routing, config API | 8081 |
| `apps/sales-agent` | Stateless LLM executor — receives context, runs tool loop, returns response | 8080 |
| `apps/telegram-module` | Transport: Telegram Bot API delivery | 8082 |
| `apps/wappi-module` | Transport: Wappi API (WhatsApp/Telegram user-proxy) | 8083 |
| `libs/common` | Shared config models, logging, IO schemas | — |

---

## Current Architecture

### Single-Agent Pipeline

Sales-agent is a **stateless LLM executor** — it receives all context in the envelope and does not fetch anything from backend on its own.

```
Transport → Backend → Sales Agent → Backend → Transport
```

**Backend** assembles:
- `prompt_template` — raw Jinja2 template from DB
- `company` — full company spec (fields, categories, tools, stages)
- `customer_answers` — current customer field values
- `history` — recent messages (capped at 20)
- `enabled_tools` — `[{name, description}, ...]`
- `langfuse_session_id`, `form_data`, `qualification_workflow`, `qualification_examples`

**Sales-agent** only:
- Renders prompt via `PromptFormatter` (Jinja2)
- Builds tool specs from `enabled_tools` (handlers are local)
- Runs `run_tool_loop`
- Executes write-only tool side-effects (calls to backend)
- Returns response

**Key files:**
- Pipeline: `apps/sales-agent/src/sales_agent/agents/pipeline.py`
- Tool registry: `apps/sales-agent/src/sales_agent/core/tools/registry.py`
- Tool implementations: `apps/sales-agent/src/sales_agent/agents/tools.py`
- Backend client (write-only): `apps/sales-agent/src/sales_agent/services/backend_client.py`

### Message Flow

**Inbound (transport → backend [→ sales-agent]):**
1. Transport normalizes to `InboundEnvelope` → `POST /api/v1/messages/inbound` (Backend)
2. Backend validates auth, assembles context; роутит в Sales Agent (`POST /api/v1/internal/messages/inbound`) или не вызывает его
3. Sales-agent (если вызван) runs LLM pipeline

**Outbound (sales-agent → backend → transport):**
1. Sales-agent sends `OutboundDeliveryRequest` → `POST /api/v1/internal/messages/outbound`
2. Backend routes to transport based on `connector.type`
3. Transport delivers via `POST /transport/delivery`

**Auth:**
- Managed connectors (telegram, wappi): `X-Service-Key` + `X-Connector-Id`
- Custom connectors: `Authorization: Bearer sk_xxx`

### Tasks & Reminders

Backend has a `tasks` module (`apps/backend/src/backend/modules/tasks/`). Scheduled AI tasks are executed via:
- Scheduler worker: `python -m src.backend.workers.task_scheduler` (from repo root or Docker), or `python -m backend.workers.task_scheduler` (from `apps/backend`)
- Sales-agent internal endpoint: `POST /api/v1/internal/tasks/execute` (`TaskExecutionRequest`)
- AI tool: `schedule_reminder` in `core/tools/registry.py`

### Event Bus

Redis Streams (`backend.events`). Backend publishes, consumers subscribe with unique group names. Events are **signals only** — consumers fetch fresh state from backend API. Config: `EVENTING__ENABLED=true`, `REDIS__URL`.

---

## Critical Patterns

### Data Encapsulation (Repository Pattern)

Operations that affect multiple fields/tables MUST go through encapsulated repository/service methods. Never update fields directly when dependent data must change atomically.

```python
# Wrong
order.assignee_id = manager_id
await order.save()

# Correct
await orders_repo.update_assignee(order, manager_id)
```

Current encapsulated operations: `update_assignee`, `create` (with assignee), `handle_handoff`, `update_stage`.

### Imports

All imports at module top-level only. Standard library → third-party → local. No imports inside functions, methods, classes, try/except, or if blocks. No exceptions.

### No Silent Fallbacks

Fail fast. Prefer strong typing (Pydantic, enums, dataclasses). Do not make values optional when they are required. Do not use `hasattr`.

### Aerich Migrations (PostgreSQL schemas)

After `aerich migrate --name <name>`, **manually** add schema prefix to all table/index references in the generated file:

```sql
-- Generated (wrong)
CREATE TABLE "tasks" (...)
-- Fixed (correct)
CREATE TABLE "backend"."tasks" (...)
```

Applies to: `backend` schema (sales-agent has no migrations).

---

## Development Commands

```bash
# Install all workspace deps (from repo root)
uv sync

# Run services (from repo root)
just dev all
just dev backend,sales-agent

# Run commands from repo root against a specific module
uv run --package backend pytest
uv run --package sales-bot pytest
uv run --package sales-bot ruff format .
uv run --package sales-bot ruff check --fix

# Migrations (from module dir)
uv run aerich init-db        # first time only
uv run aerich migrate --name <name>
uv run aerich upgrade

# Docker
docker compose build
docker compose build sales-agent
docker compose up
```

**Startup order:** Redis → Backend (migrations + service) → Sales Agent → Transports

---

## Code Style

- **Python 3.12**, FastAPI, Tortoise ORM, Aerich, Structlog, HTTPX, Pydantic v2
- **uv** for package management (not pip, not poetry)
- `ruff format` + `ruff check` for formatting/linting
- `pyright` for type checking when config exists
- `snake_case` functions/variables, `PascalCase` classes, `UPPER_CASE` constants
- Max line length: 120 characters
- Use `|` union operator (not `Optional[T]`)
- Use f-strings, not `.format()` or `%`
- Use guard clauses (early returns) to reduce nesting
- Use `logger.exception("msg")` to capture stack traces (not `logger.error(str(e))`)
- Loggers: `log = structlog.get_logger()` (structlog, not stdlib logging)

---

## Key Configuration

Env vars use double-underscore as nested separator: `DATABASE__URL` → `database.url`.

- `.env.shared` (repo root) — shared: DB, Redis, LLM keys, service URLs, `SERVICE__API_KEY`
- `apps/<module>/.env` — module-specific overrides

**Required for transports:** `BACKEND__URL` + `SERVICE__API_KEY` in `.env.shared`.

---

## Documentation Map

| File | Contents |
|------|----------|
| `AGENTS.md` | Full coding agent playbook (read this for task execution protocol) |
| `docs/structure.md` | Module descriptions, dependency graph, message flows |
| `docs/tech.md` | Full tech stack, transport contract, observability |
| `docs/product.md` | Product overview and user scenarios |
| `docs/testing.md` | Test commands per module |
| `docs/eventing.md` | Redis Streams event bus — how to publish and consume |
| `docs/configuration.md` | Full env var reference |
| `apps/sales-agent/docs/llm-architecture.md` | LLM client, tool loop, tool specs |
| `apps/sales-agent/docs/schema.md` | Dialogue pipeline schema |
| `apps/wappi-module/docs/` | Wappi-specific docs |

**Priority:** module `docs/` > root `docs/` > README > inline `AICODE-*` anchors.

---

## Prompts

Agent prompts are stored as Markdown files under `apps/sales-agent/src/sales_agent/agents/prompts/`. Single agent type `AGENT` (not the old ROUTER/QUALIFIER/CATEGORY_EXPERT split). Loaded from DB, rendered via Jinja2 in `prompt_formatter.py`.

