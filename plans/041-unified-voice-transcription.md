# 041 — Unified voice transcription for agent context

## Objective

Transcribe manager voice messages from CRM so the agent can see their content in conversation history. Unify with the existing inbound customer audio transcription path into a single `transcription` column on `ChatMessage`.

## Зачем это делаем

- **Проблема:** Менеджер отправляет голосовое сообщение из CRM клиенту, потом передаёт тред обратно агенту — агент не видит содержание голосового, потому что `content` пустой и `_build_messages` пропускает такие записи.
- **Ценность:** Агент получает полный контекст разговора, включая то, что менеджер сказал голосом. Без этого агент работает "вслепую" после менеджерского голосового.
- **Унификация:** Сейчас транскрипт входящих аудио пишется в `content` (затирает оригинал), а для менеджерских голосовых нет транскрипции вообще. Новый подход — единый `transcription` столбец для всех аудио, без затирания `content`.

## Context

### Current state

1. **Manager voice delivery works** — CRM uploads audio to S3, backend stores as attachment, delivers to Telegram/Wappi via `send_audio`.
2. **Agent never sees manager voice** — `get_recent_history` returns `role, content, metadata, created_at` (no attachments). Manager voice has empty `content`. `_build_messages` skips history items with empty content.
3. **Inbound customer audio** — sales-agent's `transcribe_if_audio` transcribes → `save_transcription` overwrites `message.content`. Works but conflates display text with transcription.

### Constraints

- **STT must live in sales-agent** — backend cannot make OpenAI/LLM requests (legal/infra constraint). Backend round-trips to sales-agent for transcription.
- **Transcript must not go to messenger** — do not send transcript text outbound to Telegram/Wappi/custom transport (CRM and agent may show it per **CRM / connector** below).
- **CRM / front** — STT is stored only in `transcription`. UIs use `transcription` for new data; `content` may still hold legacy pre-migration transcripts (`transcription || content`).
- **Internal notes (`INTERNAL_NOTE`)** — never included in `AgentContext.history`; manager-only. No background STT for `is_note` messages.

## Design

### Single `transcription` column

New `transcription` nullable `TextField` on `ChatMessage`. All STT output goes here, regardless of source (customer inbound, manager voice).

**Write rules:**

| Message type | `content` | `transcription` |
|---|---|---|
| Manager voice from CRM | empty | STT output |
| Inbound customer audio | unchanged (empty for pure voice) | STT output |
| Regular text message | original text | null |

**Read rule for LLM context:**
```python
text = item.get("content") or item.get("transcription") or ""
```

### Manager voice transcription flow

```
CRM → Backend (store + deliver) → Transport
                ↓ BackgroundTask
        Backend → Sales-Agent (POST /transcription/transcribe with artifact_id)
                    ↓
        Sales-Agent downloads audio from Backend S3
        Sales-Agent runs STT (OpenAI)
        Sales-Agent returns text
                    ↓
        Backend saves to message.transcription
```

---

## Phase 1: Backend — data model, migration, endpoint updates

**Module:** `apps/backend`

**Files modified:**
- `src/backend/modules/chat/models.py` — add `transcription = fields.TextField(null=True)`
- `migrations/models/` — Aerich migration with `backend` schema prefix
- `src/backend/modules/chat/routers.py` — update `save_transcription` endpoint: write **only** to `transcription` (never copy STT into `content`)
- `src/backend/modules/chat/repository.py` — add `"transcription"` to `get_recent_history` `.values()`; add optional `exclude_internal_notes: bool = False` on `get_recent_history` — when `True`, SQL `exclude` rows where `type == ChatMessageType.INTERNAL_NOTE` **before** `limit` (preserve “last N visible-to-agent messages”)
- `src/backend/modules/chat/service.py` — plumb `exclude_internal_notes` on `get_recent_history`
- `src/backend/modules/messages/context_assembly.py` — `AgentContextAssembler.build`: call `get_recent_history(..., exclude_internal_notes=True)`
- `src/backend/modules/chat/schemas.py` — add `transcription: str | None = None` to `ChatMessageResponse`, populate in `from_model`
- `tests/domains/chat/test_artifact_routers.py` — adjust assertions: STT only on `transcription`; `content` unchanged unless unrelated
- Tests — cover `get_recent_history(..., exclude_internal_notes=True)` (or assembler) so `INTERNAL_NOTE` rows never appear in the capped agent slice

**Dependencies:** none (foundation phase)

## Phase 2: Sales-agent — transcription endpoint

**Module:** `apps/sales-agent`

**Files modified:**
- `src/sales_agent/api/internal.py` — add **separate** `APIRouter(prefix="/api/v1/internal/transcription")` (do not nest under existing `.../messages` router) + `POST /transcribe` → full path `/api/v1/internal/transcription/transcribe`; protect with `Depends(_require_service_api_key)` like `debounce/cancel`
- `src/sales_agent/lifespan/routers.py` — `app.include_router(transcription_router)` (same file as existing internal routers)

**Endpoint contract:**

```python
# Request
class TranscriptionRequest(BaseModel):
    artifact_id: str
    mime: str | None = None

# Response
class TranscriptionResponse(BaseModel):
    text: str
```

**Logic:**
1. Get `settings` and `backend_client` from `app.state`
2. Download audio via `backend_client.download_artifact(artifact_id)`
3. Create `OpenAITranscriptionService(settings)`, call `transcribe()`
4. Return `TranscriptionResponse(text=...)`

**Dependencies:** Phase 1 is not a strict dependency — this endpoint is standalone. Can be developed in parallel.

## Phase 3: Backend — manager voice transcription trigger

**Module:** `apps/backend`

**Files modified:**
- `src/backend/modules/messages/sales_agent_client.py` — add `request_transcription(artifact_id: str, mime: str | None) -> str`: POST to `/api/v1/internal/transcription/transcribe`, parse response JSON `text`. **Current `_post_with_retry` returns `None` and drops the body** — refactor: extract shared retry loop (same `MAX_RETRIES` / backoff / 5xx rules as today) into a helper that can **`return response`** or **`return response.json()`**, then wire `forward_inbound` / `cancel_debounce` / `execute_task` and the new transcription call through it; use a **longer read timeout** for the transcription request only (dedicated `httpx` call or per-request timeout inside the helper)
- `src/backend/modules/chat/service.py` — add async `transcribe_voice_message(message_id: str, attachments: list[dict]) -> None`: find the **single** attachment with `type in ("audio","voice")` and `artifact_id` (product assumption: at most one voice per message), call client, persist `transcription`. If `SalesAgentClient` / URL missing, log and return — **no silent success**. Inject `SalesAgentClient` into `ChatService` (avoid relying on `ThreadsService` private client)
- `src/backend/modules/chat/dependencies.py` — pass `sales_agent_client: SalesAgentClientDep` into `ChatService(...)` factory
- `src/backend/modules/chat/routers.py` — add required `background_tasks: BackgroundTasks` to `send_manager_message`. When **`not payload.is_note`** and attachments include `audio`/`voice`, after **`deliver_manager_message` succeeded**, `background_tasks.add_task(chat_service.transcribe_voice_message, ...)`. **`is_note=True`:** no STT (notes never go to the agent).

**Dependencies:** Phase 1 (column must exist), Phase 2 (sales-agent endpoint must exist)

**Attachment assumption:** At most **one** voice/audio attachment per manager message — no multi-file merge.

**File overlap:** Phases 1 and 3 both edit `chat/routers.py` and **`chat/service.py`** — merge in one branch or single PR chunk to avoid conflicts.

## Phase 4: Sales-agent — pipeline history builder

**Module:** `apps/sales-agent`

**Files modified:**
- `src/sales_agent/agents/pipeline.py` — update `_build_messages`: use `content or item.get("transcription", "")` when checking if a history item has text

**Change (line 79):**
```python
# Before:
if role in ("user", "assistant", "tool", "manager") and content:

# After:
text = content or item.get("transcription", "")
if role in ("user", "assistant", "tool", "manager") and text:
    ...
    messages.append({"role": role, "content": text})
```

**Dependencies:** Phase 1 (history must include `transcription` field)

## Phase 5: Sales-agent — unify inbound transcription cache

**Module:** `apps/sales-agent`

**Files modified:**
- `src/sales_agent/services/transcription.py` — update `TranscriptionCache.get_cached`: check `message_data.get("transcription")` instead of `message_data.get("content")`

**Change:**
```python
# Before:
cached_text = message_data.get("content")

# After (avoid re-STT for pre-migration rows that only have content filled):
cached_text = (message_data.get("transcription") or message_data.get("content") or "").strip() or None
```

The `save` path calls `save_transcription`, which writes **only** to `transcription`.

**Dependencies:** Phase 1 (internal GET must return `transcription` once schema/model expose it — automatic via `ChatMessageResponse` after Phase 1)

---

## Execution order

```
Phase 1 (backend model + migration)  ──→  Phase 3 (backend trigger)
         ↓                                         ↓
Phase 2 (sales-agent endpoint)  ←── parallel ──→  Phase 4 (pipeline)
```

**Phase 5** depends on Phase 1 only; run **after** Phase 1 (same release train as Phase 4 is fine). Do **not** deploy Phase 5 before Phase 1 — cache would read empty `transcription` while older rows might only have legacy text in `content`.

**Concrete dependency matrix**

| Consumer | Needs from Phase 1 | Needs from Phase 2 |
|----------|--------------------|--------------------|
| Phase 3 | DB column `transcription`; `save_transcription` / optional direct row update | HTTP `POST .../transcription/transcribe` returning `{ "text": "..." }` |
| Phase 4 | `get_recent_history` dict includes `transcription`; agent path excludes internal notes | — |
| Phase 5 | `GET /internal/chat/messages/{id}` JSON includes `transcription` | — |

Phases 1 and 2 share **no files** (true parallel). Phases 1 and 3 share `chat/routers.py` only if split across agents — coordinate.

## CRM / connector (decided)

- **CRM:** Prefer `transcription` for voice transcripts; use `transcription || content` for legacy rows. `ChatMessageResponse` exposes both.
- **Connector:** The invariant is **do not send the transcript text as an outbound text message** to Telegram/Wappi/custom transport. Delivery stays attachment-only (voice file); STT runs afterward and only updates DB (`transcription`), which does not trigger re-delivery.

## Decisions (decided)

- **Internal notes:** Excluded from agent history via `get_recent_history(..., exclude_internal_notes=True)` on the `AgentContextAssembler` path only. No STT for `is_note` manager messages.
- **STT HTTP:** Same retry policy as `_post_with_retry` today, but response body required — refactor client (see Phase 3 file list).
- **Voice attachments:** At most one `audio`/`voice` per non-note manager message.

## Internal docs to refresh

- `get_message_by_id` router docstring still says transcription lives in `content` — update after Phase 1 (`routers.py` ~1208–1215).
- Optional: `libs/common/.../outbound.py` `AgentContext.history` field description — add optional `transcription` key in the list item shape.

## Plan validation (codebase)

- **`ChatMessage.type`** exists (`CharEnumField(ChatMessageType)`); filtering `INTERNAL_NOTE` in the repository is valid.
- **Single assembler entry point:** `AgentContextAssembler.build` is used from `messages/routers`, `task_scheduler`, and `task_executor` — one `exclude_internal_notes=True` call covers all agent envelopes (not only inbound).
- **`_post_with_retry` blocker:** Present implementation returns `None` after `raise_for_status()`; transcription needs JSON `text`. Phase 3 must extend/refactor the client — calling `_post_with_retry` **as-is** is insufficient.
- **Internal history router:** `GET .../internal/.../history` uses `get_recent_history` **without** exclusion today — confirm product: internal API consumers (debug/scripts) may still see full thread including notes; only assembler path uses `exclude_internal_notes=True`.

## Рекомендуемая модель для выполнения

**Claude Sonnet 4.6** — 2 modules (`apps/backend` + `sales-agent`), well-defined changes, moderate complexity. One migration; client refactor for JSON+retry is the main non-obvious step.
