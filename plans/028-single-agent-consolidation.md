# 028 — Single Agent + Stateless Sales-Agent

> Collapse multi-agent pipeline into a single agent. Backend assembles all context into the envelope. Sales-agent renders the prompt and executes the LLM loop — no caches, no fetches.

---

## Зачем это делаем

Multi-agent routing adds complexity without UX benefit — single agent wins on win rate. Meanwhile sales-agent maintains caches (company spec, prompts, stages), fetches data from backend on every request (prompts, customer answers, history), and runs its own prompt formatting. This creates sync bugs, cache invalidation headaches, and a 404 crash when prompts aren't seeded (`/api/v1/prompts/qualifier`).

**What this fixes:**
- Eliminates 404 crash on first run (no more separate prompt fetching)
- Removes all caches and read-only backend calls from sales-agent
- Single prompt to configure = simpler onboarding
- Backend assembles data, sales-agent renders and executes — clear responsibility split
- Sales-agent becomes a pure function: `(template, data, history, tools, message) → response`

---

## Scope

**In scope:**
- Backend: assemble all context (template, company data, answers, history, tools) into the envelope
- Sales-agent: strip all read-only state, caches, fetchers — keep prompt rendering + LLM loop + tool execution + debounce
- Delete dead code (stubs, `domain.yaml`, multi-agent routing)
- Backend retry logic for sales-agent forwarding

**Out of scope:**
- Frontend changes (already aligned)
- Prompt content rewrite (merge qualifier + category_expert templates — separate task)
- Debounce changes (stays as-is)

---

## Architecture: Responsibility Split

**Backend** (data assembler):
- Loads prompt template from DB
- Loads company spec (fields, categories, tools, stages)
- Loads customer answers
- Loads recent message history
- Resolves enabled tool names + descriptions
- Resolves qualification_workflow/examples (per-connector via prompt_addon, fallback to company)
- Packs everything into `InternalInboundRequest` envelope
- Retries forwarding to sales-agent on failure

**Sales-agent** (LLM executor):
- Receives envelope with raw template + data
- Renders prompt (Jinja2 substitution — `prompt_formatter.py` stays here)
- Builds tool specs from enabled tool names (handlers + schemas are local)
- Runs LLM tool loop
- Executes tool side-effects (write calls to backend)
- Returns response

---

## Envelope Design

```python
class InternalInboundRequest(BaseModel):
    # --- existing fields ---
    envelope: InboundEnvelope
    context: ConnectorContext
    thread_id: str
    order_id: int | None = None
    order_stage: dict[str, Any] | None = None

    # --- new fields ---
    prompt_template: str                   # raw Jinja2 template from DB
    company: dict[str, Any]               # company spec (name, description, fields, categories, tools, stages, etc.)
    customer_answers: dict[str, Any]      # current customer field values
    history: list[dict[str, str]]         # recent messages [{role, content}, ...], capped at 20
    enabled_tools: list[dict[str, Any]]   # [{name, description}, ...] — names for handler wiring, descriptions for prompt
    langfuse_session_id: str | None = None
    form_data: dict[str, Any] | None = None

    # --- kept as-is (NOT absorbed into company) ---
    qualification_workflow: str | None = None   # resolved per-connector via prompt_addon
    qualification_examples: str | None = None   # resolved per-connector via prompt_addon
```

**Note on qualification_workflow/examples:** These are thread-specific — resolved via `chat_service.get_qualification_config(thread)` which checks prompt_addon per connector, then falls back to company defaults. They are NOT simple company-level fields and must stay as separate envelope fields.

**Size estimate:** ~20-60 KB total. Same data already transfers today across 4-5 sequential HTTP round-trips — this consolidates into one.

---

## Current sales-agent → backend read calls (to be eliminated)

| Call | What it fetches | Replacement |
|------|----------------|-------------|
| `get_company_spec(company_id)` | Company config, fields, categories, tools, stages | `company` in envelope |
| `get_prompt(agent_type)` | Prompt template text | `prompt_template` in envelope |
| `get_customer_answers(user_id, company_id)` | Customer field values | `customer_answers` in envelope |
| `get_customer_profile(user_id, company_id)` | Customer profile | `customer_answers` in envelope |
| `get_recent_history(thread_id, limit)` | Message history | `history` in envelope |
| `get_langfuse_session_id(...)` | Langfuse session ID | `langfuse_session_id` in envelope |
| `create_langfuse_session(...)` | Creates langfuse session | Move to backend |
| `get_or_create_thread(...)` | Thread creation | Already done in backend before forwarding |
| `get_order_by_thread(thread_id)` | Order context | Already in envelope (`order_id`, `order_stage`) |

**Stays** (write operations):
- `update_customer_fields`, `update_order_stage`, `update_order_fields`, `close_order`
- `request_handoff`, `notify_handoff`
- `send_outbound_message`
- `save_transcription`, `download_artifact`
- `create_order_task`

**Removed** (was write, now unnecessary):
- `append_history_batch` — backend already saves messages on both inbound and outbound

---

## Dead code to delete

| File/Module | Reason |
|-------------|--------|
| `agents/router.py` | Unused stub (always returns "qualifier") |
| `agents/qualifier.py` | Unused stub |
| `agents/product_expert.py` | Unused stub |
| `config/domain.yaml` | Not loaded anywhere |
| `services/prompt_service.py` | No more prompt fetching — template comes in envelope |
| `services/domain_config.py` | Config comes in envelope |
| `services/product_config.py` | Config comes in envelope |
| `agents/stage.py` | Stage data comes in `company` dict, formatting stays in `prompt_formatter.py` |

**NOT deleted (see validation findings):**
- `services/company_context.py` — repurposed: ContextVar still needed to pass `company` dict from envelope to tool handlers (`set_customer_fields`, `search_product`, `update_order_fields` all call `get_company_spec()` for field validation). Set from envelope data instead of backend fetch.
- `storage/customer_store.py` — partially kept: write wrappers (`update_customer_fields`, `get_backend_client`, `set_backend_client`) still needed by `tools.py`. Read functions removed.

**Stays in sales-agent:**
- `services/prompt_formatter.py` — renders template with envelope data (sales-agent's responsibility)
- `services/company_context.py` — repurposed as request-scoped ContextVar for envelope `company` dict
- `core/tools/registry.py` — builds tool handlers from enabled tool names
- `agents/tools.py` — tool implementations (validation, search, handoff, etc.)
- `services/backend_client.py` — write operations only
- `services/debounce.py` — unchanged
- `services/message_processor.py` — simplified (no fetching)
- `services/humanizer.py` — refactored to accept history from args (not fetch)
- `services/transcription.py` — stays
- `services/crm_adapter.py` — stays (CRM stage mapping, handoff notifications)
- `core/llm/` — LLM client + tool loop — stays
- `faq/` — stays (search_kb tool uses it)

---

## Validation Findings

### Finding 1: `tools.py` depends on `get_company_spec()` for runtime validation

`set_customer_fields()`, `search_product()`, `update_order_fields()` all call `get_company_spec()` to validate enum fields and search products. This means `company_context.py` **cannot be deleted** — it must be repurposed to hold envelope's `company` dict in a ContextVar, set once per request in `pipeline.py`.

**Resolution:** Keep `company_context.py` but remove the backend-fetching logic. Pipeline sets `set_company_spec(envelope.company)` at request start, tools read via `get_company_spec()` as before.

### Finding 2: `humanizer.py` fetches history via `get_recent_history()`

`humanize_message()` (line 200) calls `get_recent_history()` from `storage/customer_store.py` to get recent bot messages for emoji/bracket decisions. With envelope-based approach, history is already available.

**Resolution:** Refactor `humanize_message()` to accept `history: list[dict] | None` as parameter. Pipeline passes `history` from envelope. Eliminates the backend call.

### Finding 3: `message_processor.py` has two read calls that need envelope data

- Line 201: `get_recent_history()` — used to check if first message (for Bitrix initial stage)
- Line 276: `get_answers()` — used to read `handoff_summary` after pipeline execution

**Resolution:** First-message check uses `history` from envelope (empty history = first message). Handoff summary check is trickier — pipeline may set `handoff_summary` during execution via `set_customer_fields` tool. After pipeline returns, `message_processor` needs this value. Options:
- Return `handoff_summary` from pipeline result (extend `AgentsPipelineResult`)
- Or keep a single `get_answers()` call post-pipeline (acceptable — it's one read after processing, not a pre-fetch)

### Finding 4: Simulator endpoint is a separate entry point

`api/simulator.py` calls `process_user_message_agents()` directly with a minimal `SimpleMessage`. It doesn't go through the envelope flow. Currently it fetches everything from backend internally.

**Resolution:** Simulator must construct the same enriched data structure. Two options:
1. Simulator calls backend API to get enriched envelope data, then calls pipeline
2. Simulator becomes a backend endpoint that uses the same assembly logic

Option 2 is cleaner — move simulator to backend, have it call the same enrichment + forwarding logic. **Alternatively**, keep simulator as-is for now (it's a dev-only tool) and mark as follow-up.

### Finding 5: Reminder flow (`process_reminder`) is a second entry point

`TaskExecutionRequest` (used for scheduled reminders) currently goes through `process_reminder()` → `process_user_message_agents()`. It has no enriched envelope data. Backend sends only `task_id`, `auto_action`, `title`, `description` + base fields.

**Resolution:** `TaskExecutionRequest` must be enriched the same way as `InternalInboundRequest`. Backend already has all context when executing a task — add the same fields to `TaskExecutionRequest`. This is a **Phase 1 requirement** — both request types must carry the full context.

### Finding 6: `/clear` command in pipeline still calls backend

Pipeline line 290-299: `/clear` calls `reset_customer_profile()` and `create_langfuse_session()` from `storage/customer_store.py`.

**Resolution:** `/clear` becomes a backend_client write call: `backend_client.reset_customer_profile(user_id, company_id)`. Langfuse session creation moves to backend.

### Finding 7: `crm_adapter.py` depends on `stage.py` → `domain_config.py`

`crm_adapter.py` imports `to_crm_stage` from `stage.py`, which loads stages via `domain_config.py` → `get_company_spec()`. If `stage.py` and `domain_config.py` are deleted, `crm_adapter` breaks.

**Resolution:** `crm_adapter.py` stage mapping can use the `company` dict from ContextVar (same pattern as tools). Stage definitions are in `company["stages_config"]`. Inline the simple `to_crm_stage()` lookup into `crm_adapter`.

### Finding 8: `qualification_workflow/examples` are NOT company-level

Plan originally said "absorbed into company dict". Wrong. These are resolved per-connector via `chat_service.get_qualification_config(thread)` which checks `prompt_addon` for the specific connector, falling back to company defaults. They must stay as separate envelope fields.

**Resolution:** Keep `qualification_workflow` and `qualification_examples` as separate fields on `InternalInboundRequest` (already there today — no change needed).

---

## Phase 1 — Backend: Enrich Envelope + Retries

**Goal:** Backend assembles all context into `InternalInboundRequest` and `TaskExecutionRequest`. Retry forwarding to sales-agent on failure.

**Depends on:** Nothing — this is the foundation.

**Concrete outputs consumed by Phase 2:**
- `InternalInboundRequest` with fields: `prompt_template`, `company`, `customer_answers`, `history`, `enabled_tools`, `langfuse_session_id`, `form_data`
- `TaskExecutionRequest` with same enrichment fields
- `SalesAgentClient` with retry logic
- `AgentType.AGENT` enum value

**Files modified:**
- `libs/common/src/common/models/outbound.py` — extend `InternalInboundRequest` and `TaskExecutionRequest` with new fields. Keep `qualification_workflow` and `qualification_examples` as-is.
- `apps/backend/src/backend/modules/messages/routers.py` — assemble full context before forwarding:
  - Load prompt template from DB (single `agent` type)
  - Load company spec via existing `get_specification` service method
  - Load customer answers via `CustomersRepository`
  - Load recent history via `ChatMessagesRepository` (cap at 20)
  - Resolve enabled tools from company spec
  - Resolve langfuse session ID
  - Pack into enriched envelope
  - **Note:** The existing `order`, `thread`, `order_stage_data`, `qualification_workflow`, `qualification_examples` assembly stays — we add to it, not replace.
- `apps/backend/src/backend/modules/tasks/routes.py` — enrich `TaskExecutionRequest` with same context before forwarding to sales-agent for reminder execution.
- `apps/backend/src/backend/modules/messages/sales_agent_client.py` — add retry logic:
  - Configurable max retries (default 3)
  - Exponential backoff (1s, 2s, 4s)
  - Retry on 5xx and connection errors only (not 4xx)
  - Log each retry attempt
- `apps/backend/src/backend/modules/prompts/models.py` — replace `AgentType` enum values: `ROUTER`, `QUALIFIER`, `CATEGORY_EXPERT` → single `AGENT = "agent"` (DBs are empty — no migration needed)

---

## Phase 2 — Sales-Agent: Strip to Stateless Executor

**Depends on:** Phase 1 — specifically: `InternalInboundRequest` has `prompt_template: str`, `company: dict`, `customer_answers: dict`, `history: list[dict]`, `enabled_tools: list[dict]`, `langfuse_session_id: str | None`, `form_data: dict | None`. `TaskExecutionRequest` has same fields.

**Goal:** Sales-agent receives everything it needs. No caches. No read calls. Renders prompt locally, runs LLM loop.

**Files modified:**
- `apps/sales-agent/src/sales_agent/agents/pipeline.py` — rewrite:
  - Accept enriched envelope fields from metadata
  - `set_company_spec(company_dict)` at request start (for tool validation)
  - Render prompt via `PromptFormatter` with envelope data
  - Build tool specs from `enabled_tools` (handlers wired locally)
  - Single code path: render → build messages from `history` → `run_tool_loop` → return
  - Remove `_invoke_category_expert`, `_ready_for_category_expert`, routing gates
  - Remove all `get_company_spec` fetch, `get_answers` fetch, `get_recent_history` fetch
  - `/clear` command → `backend_client.reset_customer_profile()` direct call
  - Return `handoff_summary` in `AgentsPipelineResult` (for message_processor)
- `apps/sales-agent/src/sales_agent/core/tools/registry.py` — replace `build_qualifier_tools()` + `build_category_expert_tools()` with single `build_tools(enabled_tools, ...)` that maps tool names to handlers. Tool descriptions come from envelope's `enabled_tools[].description`.
- `apps/sales-agent/src/sales_agent/services/backend_client.py` — delete all read-only methods and caches (`_spec_cache`, `_prompt_cache`, `get_company_spec`, `get_prompt`, `get_customer_answers`, `get_customer_profile`, `get_recent_history`, `get_langfuse_session_id`, `create_langfuse_session`). Keep write methods only. Add `reset_customer_profile()` as direct write method.
- `apps/sales-agent/src/sales_agent/services/company_context.py` — simplify: keep ContextVar, remove any backend-fetching logic. Just `set_company_spec(dict)` / `get_company_spec() -> dict`.
- `apps/sales-agent/src/sales_agent/services/prompt_formatter.py` — simplify: receives `dict[str, Any]` instead of `CompanySpec` model.
- `apps/sales-agent/src/sales_agent/services/humanizer.py` — refactor `humanize_message()` to accept `history` parameter instead of fetching.
- `apps/sales-agent/src/sales_agent/api/internal_utils.py` — update `map_to_incoming_message` to pass new envelope fields through metadata.
- `apps/sales-agent/src/sales_agent/services/message_processor.py` — simplify:
  - Use `history` from envelope for first-message check
  - Read `handoff_summary` from pipeline result instead of `get_answers()`
  - Remove `get_recent_history` and `get_answers` imports
  - `process_reminder()` now receives enriched `TaskExecutionRequest`
- `apps/sales-agent/src/sales_agent/services/crm_adapter.py` — inline `to_crm_stage()` lookup using `company` dict from ContextVar instead of `stage.py` → `domain_config.py` chain.
- `apps/sales-agent/src/sales_agent/storage/customer_store.py` — strip to writes only: keep `update_customer_fields()`, `get_backend_client()`, `set_backend_client()`. Remove all read functions.
- `apps/sales-agent/src/sales_agent/agents/tools.py` — `set_customer_fields()` line 179 calls `get_answers()` to check `_form_pending_confirmation`. Pass `customer_answers` from envelope into tool handler closure instead.

**Files deleted:**
- `agents/router.py`, `agents/qualifier.py`, `agents/product_expert.py` — unused stubs
- `services/prompt_service.py` — no more prompt fetching
- `services/domain_config.py`, `services/product_config.py` — config comes in envelope
- `agents/stage.py` — inlined into `crm_adapter.py`
- `config/domain.yaml` — not loaded anywhere

**Tests updated:**
- `tests/domains/agents/test_pipeline.py`
- `tests/domains/agents/test_pipeline_e2e.py`

---

## Phase 3 — Cleanup

**Depends on:** Phase 2

- `apps/backend/tests/domains/prompts/` — update for single `agent` type
- Decide on simulator: move to backend endpoint or keep with separate enrichment call
- Verify `services/connector_sync.py` — still needed for webhook connector config or can be removed
- Remove unused imports across modified files
- Run `ruff format` + `ruff check --fix` + `pyright` on both modules

---

## Risks

- **Envelope size**: ~20-60 KB per request. Same data as today but in one payload. Cap history at 20 messages.
- **Sales-agent downtime**: backend retries with exponential backoff (3 attempts, 1s/2s/4s) handle transient failures.
- **Tool description drift**: tool descriptions now travel in envelope from DB. If DB descriptions are empty, sales-agent falls back to hardcoded defaults in registry (existing pattern).
- **Tool execution still calls backend**: write operations remain as HTTP calls — that's fine, these are side-effects not state.
- **`_form_pending_confirmation` check**: `set_customer_fields` tool reads current answers to check form lock. Must receive `customer_answers` from envelope via closure — stale by definition (answers may have been updated by a tool call earlier in the same LLM loop). Acceptable: the lock is only relevant for the first message in a Bitrix form batch.
