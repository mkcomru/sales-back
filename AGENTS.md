# AGENTS.MD — Sales Bot Coding-Agent Playbook

This playbook is the **single source of truth** for any autonomous or semi-autonomous coding agent ("Agent") contributing to the sales-bot monorepo. Follow it end-to-end to keep contributions predictable, reviewable, and aligned with the documentation under `docs/` and any module-level guides.

---

## 1. Core Principles

1. **Documentation-Driven Development** – Every run starts by reading the relevant documentation.
   - Always read the root docs: `docs/structure.md`, `docs/tech.md`, `docs/product.md`, `docs/testing.md`.
   - If the target module exposes its own `docs/` or README, those files take precedence; read them immediately after the root docs.
2. **Instruction-First, Best Practices** – For straightforward work, follow the human request precisely while writing clean, maintainable code.
3. **Conditional Planning & Verification** – Produce a plan (see §3) for complex tasks or when explicitly asked. Skip plan mode for simple, contained edits.
4. **Greppable Inline Memory** – Use `AICODE-*:` anchors (§5) to leave durable breadcrumbs for other agents.
5. **Small, Safe, Reversible Commits** – Keep diffs focused. Prefer multiple tight commits over a single sprawling change.
6. **Prompt Hygiene** – Craft clear, non-contradictory prompts; state required output formats; break large asks into ordered steps. When in doubt, outline a plan before coding.

---

## 2. Task Execution Protocol

> Human issues an instruction (e.g., “add RetailCRM connector skeleton”). Determine complexity, then either plan or implement directly.

1. **Read Context**
   - Root docs (`docs/*.md`).
   - Module-specific docs/README under `apps/<module>/` or `libs/<package>/`.
   - Recent `AICODE-*` anchors relevant to the touched files (`rg "AICODE-" -n <path>`).
2. **Analyse the Request** – Identify impacted modules, dependencies, tests, and documentation.
3. **Plan Mode** – Required for complex work (§2.1); optional otherwise.
4. **Implementation** – Keep changes scoped. Respect module boundaries and shared library contracts.
5. **Verification**
   - Run proportionate checks (see §6) for the module you touched.
6. **Wrap-Up** – Summarise what changed, note any residual risks, and suggest follow-up actions. Do not update documentation outside the scope of your change unless behaviour actually shifted.

### 2.1. Determining Task Complexity

Treat a task as **complex** when it involves any of the following:
- Multiple modules (`apps/` or `libs/`) or cross-connector flows.
- Non-trivial algorithms, concurrency, or failure handling logic.
- New external integrations or security-sensitive changes.
- Large-scale refactors, schema changes, or dependency upgrades.
- Ambiguous requirements where additional clarification is needed.

When unsure, default to plan mode and wait for approval.

---

## 3. Plan Mode (Complex Tasks Only)

Plans live under `apps/<module>/plans/` (module-scoped) and root `plans/` for cross-cutting; naming stays `###-objective-description.md`.

> Before creating a plan, determine which module it belongs to and create it inside the corresponding module. Cross-cutting plans go in the root `plans/` directory.

A valid plan contains:
- **Objective** – the human request verbatim.
- **Proposed Steps** – numbered, concise, actionable.
- **Risks / Open Questions** – bullets highlighting uncertainties.
- **Rollback Strategy** – how to restore the previous behaviour quickly.

Proceed only after the human explicitly approves (acceptance reaction or equivalent).

---

## 4. Module Awareness

- **Backend (`apps/backend`)** – CRM core; Python FastAPI, central router, companies, orders, billing. Uses uv, pytest, structlog. Has migrations (Aerich).
- **Sales Agent (`apps/sales-agent`)** – Stateless LLM executor (no DB, no migrations). Receives context from Backend, runs tool loop, returns response. Uses uv, pytest, structlog.
- **Telegram Module (`apps/telegram-module`)** – Python FastAPI transport service. Uses uv, pytest, and structlog. Commands can run from module root or repo root using `uv run --package telegram-module`.
- **Wappi Module (`apps/wappi-module`)** – Python FastAPI transport service. Uses uv, pytest, and structlog. Commands can run from module root or repo root using `uv run --package wappi-module`.
- **Common Library (`libs/common`)** – Shared Python package managed through uv workspace. Ensure downstream modules remain compatible when modifying shared models or logging helpers.

Always confirm which module(s) your change touches and adapt commands, tooling, and documentation accordingly.

---

## 5. Inline Memory — `AICODE-*:` Anchors

Use language-appropriate comment tokens (`#`, `//`, etc.). Anchors are **mandatory** when logic is non-obvious, mirrors legacy behaviour, or touches historically fragile areas.

- `AICODE-NOTE:` – capture rationale or cross-file links.
- `AICODE-TODO:` – document known follow-ups out of scope.
- `AICODE-QUESTION:` – flag uncertainty that requires human review.

Example (Python):
```python
# AICODE-NOTE: Reuses debounce window logic to stay aligned with sales-agent pipeline.
```

Discover anchors via `rg "AICODE-"` before modifying related code.

---

## 6. Verification & Quality Gates

### 6.1 Python Modules (`apps/backend`, `apps/sales-agent`, `libs/common`)
Run commands from the module root unless noted otherwise:
1. **Formatting** – `uv run ruff format .` (run from module root).
2. **Linting & Imports** – `uv run ruff check --fix`.
3. **Type Checking** – `uv run pyright` (skip if the module lacks a config, but note it in your summary).
4. **Tests** – `uv run pytest` or a focused subset (`-k`, path filters) from module root, or `uv run --package <package-name> pytest` from repo root.

Only execute the steps that make sense for the change; justify any skipped checks in your summary.

### 6.2 Residual Risks Checklist (Complex Tasks)
- [ ] Test command(s) executed or clearly justified.
- [ ] Formatters/linters run (or rationale provided).
- [ ] No unresolved `AICODE-QUESTION:` anchors remain.
- [ ] Change is documented when it alters behaviour visible to other agents.

---

## 7. Environment & Tooling Notes

- Monorepo uses uv workspace with a single shared virtual environment in the root.
  - Sync all dependencies: `uv sync` (from repo root installs all workspace packages).
  - Run commands from root against a module: `uv run --package <package-name> <cmd>` (use package name from pyproject.toml, e.g., `sales-bot`, `telegram-module`, `backend`).
  - Run commands from within a module: `cd apps/<module> && uv run <cmd>` (simpler, no --package flag needed).
- Shared configuration resides in `libs/common/src/common/config.py`; modify with care and propagate necessary updates to dependent apps.
- Docker Compose (`docker-compose.yml`) runs multi-service stacks; ensure `.env` files exist (`apps/sales-agent/.env`) before launching.
- When adding a new connector, document its setup in `docs/product.md` and create a module-level README.

### 7.1 Database Migrations (Aerich + PostgreSQL Schemas)

**Critical:** Aerich does not automatically include schema qualifiers in generated migrations. After running `aerich migrate --name <name>`:

1. Open the generated migration file in `migrations/models/`
2. Manually add schema prefix to all table references:
   ```python
   # Before (generated by Aerich)
   CREATE TABLE "users" (...)
   CREATE INDEX "idx_users_email" ON "users" (...)
   
   # After (manually fixed)
   CREATE TABLE "backend"."users" (...)
   CREATE INDEX "idx_users_email" ON "backend"."users" (...)
   ```
3. Verify in downgrade as well

This applies to `backend` only (sales-agent has no migrations). The first migration (`aerich init-db`) sets the correct pattern to follow.

---

## 8. Prompt Management

**Prompts are stored in local `.md` files** under `apps/sales-agent/src/sales_agent/agents/prompts/`.

---

## 9. Documentation Maintenance

1. **Reading Order** – Root docs first, then module docs, then inline anchors.
2. **Where to Document Changes**:
   - **AGENTS.md** – Only update for changes to agent workflows, tooling setup, or prompt management procedures. Keep high-level.
   - **docs/** – All feature implementations, architectural decisions, and technical details belong here (e.g., `docs/architecture.md`, `docs/features.md`).
   - **Module docs** – Module-specific changes go to `apps/<module>/docs/` or module README.
3. **When to Update Docs** – Update only when behaviour, architecture, external contracts, or developer workflows change.

---

## 10. Prompting Best Practices

- Phrase instructions clearly; avoid contradictory requirements.
- Declare the desired output shape (bullets, tables, code snippets) when it matters.
- Break complex tasks into sub-steps. Ask for a plan first if scope is unclear.
- Use explicit context tags (e.g., `<module>`, `<task>`) when aggregating multiple asks in a single prompt.

---

## 11. Fallback Behaviour

When uncertain:
1. Add an `AICODE-QUESTION:` anchor at the relevant code location.
2. Surface the open question in your final summary.
3. If risk is high, keep the change behind a feature flag, guard, or draft PR and await human input.

Stay within these guardrails and the sales-bot monorepo will remain stable, traceable, and ready for additional CRM connectors.
