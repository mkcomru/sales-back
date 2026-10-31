# Backend Workers

Workers are **backend execution modes**, not separate services.

---

## Architectural Boundary

```
┌─────────────────────────────────────────────────────────────────┐
│                         BACKEND                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │
│  │   FastAPI   │    │   Workers   │    │  Services / Repos   │  │
│  │  (uvicorn)  │───▶│ (scheduler) │───▶│   (business logic)  │  │
│  └─────────────┘    └─────────────┘    └──────────┬──────────┘  │
│         │                                         │             │
│         └────────────────────────────────────────▶│             │
│                                                   ▼             │
│                                            ┌──────────┐         │
│                                            │    DB    │         │
│                                            └──────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ HTTP API only
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────┴───────┐   ┌─────────┴─────────┐   ┌───────┴─────┐
│  sales-agent  │   │  telegram-module  │   │ wappi-module│
└───────────────┘   └───────────────────┘   └─────────────┘
```

**Rules:**

1. **Workers ARE backend** — same codebase, same services, same repos
2. **External apps talk to backend via HTTP API ONLY** — never import backend code, never access DB
3. **No shortcuts** — sales-agent, telegram-module, etc. MUST use backend's REST/internal endpoints

---

## Worker Guidelines

### ✅ Workers MUST

- Live in `backend/workers/` directory
- Import and use backend's service layer (`TaskService`, `OrderService`, etc.)
- Be thin orchestration — poll, delegate to service, done
- Share the same DB connection config as backend API

### ❌ Workers MUST NOT

- Define their own models or repositories
- Execute raw DB queries (`Task.filter(...)`, `await Task.create(...)`)
- Contain business logic — that belongs in services
- Be imported by external apps

---

## Why This Matters

Backend is the **single source of truth** for all business logic and data access:

- **Consistency** — one place for validation, one place for business rules
- **No race conditions** — services handle concurrency, not scattered code
- **Maintainability** — change logic in one place, all entry points get it
- **Testability** — test services once, workers are just thin wrappers

If a worker needs new functionality, add it to the appropriate service first, then call that service from the worker.

---

## Current Workers

| Worker | Purpose | Entry Point |
|--------|---------|-------------|
| `task_scheduler` | Polls for due tasks, executes AI-scheduled tasks | `python -m backend.workers.task_scheduler` |
