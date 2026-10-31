# Telegram Broadcast & Batch Delivery Plan

## Objective
- Implement backend-managed broadcast jobs that deliver batched messages through connectors supporting Telegram bot transport without regressing existing conversational delivery.

## Proposed Architecture

### Relations & Data Model
- `broadcasts` table (backend schema): `id`, `company_id`, `connector_id`, `channel_type`, `status` (enum: draft/queued/in_progress/paused/completed/cancelled/failed), `message_body`, `parse_mode`, `attachments_ref`, `metadata`, `total_recipients`, `sent_success`, `sent_failed`, `scheduled_at`, `dispatched_at`, `completed_at`, `created_by`, `approved_by`, timestamps.
- `broadcast_recipients` table: `id`, `broadcast_id` (FK), `chat_id`, `username`, `full_name`, `extra_metadata`, `status` (pending/sent/failed/cancelled), `attempts`, `last_error`, `correlation_id`, `sent_at`, indexes on `(broadcast_id, status)` and `(connector_id via broadcast join, status)`.
- `messages` table (existing transport logs) gains nullable `broadcast_id` FK for correlating per-recipient delivery telemetry.
- Settings layer: connector metadata advertises `supports_broadcast` (bool) + `max_broadcast_chunk` (int) so backend gates feature per connector without hardcoding Telegram specifics.

### Backend API Surface
- `POST /transport/broadcasts` (service-key auth): create broadcast record with message payload, connector/company bindings, optional schedule info; returns identifiers + upload URL.
- `POST /transport/broadcasts/{broadcast_id}/recipients/upload` (multipart CSV or JSON array): backend parses, validates required `chat_id` or resolves via known mapping, stores rows into `broadcast_recipients`, updates `total_recipients`.
- `GET /transport/broadcasts` with filters (`company_id`, `status`, pagination): list jobs for UI dashboards.
- `GET /transport/broadcasts/{broadcast_id}`: return headline stats, timeline fields, connector metadata, and aggregated counters powering charts.
- `GET /transport/broadcasts/{broadcast_id}/recipients` (paginated): surface normalized rows + statuses for debugging and targeting replays.
- `POST /transport/broadcasts/{broadcast_id}/dispatch`: transition draft → queued, enqueue worker task.
- `POST /transport/broadcasts/{broadcast_id}/cancel`: set to cancelled if not finished, mark remaining recipients as cancelled.
- `POST /transport/broadcasts/{broadcast_id}/retry-failed` (optional action): clone failed recipients into a follow-up broadcast or reset statuses back to pending.

### Connector-Agnostic Delivery Contract
- New shared schema `BroadcastChunkRequest` (in `libs/common`) encapsulates connector-neutral payload: `broadcast_id`, `chunk_id`, `message` block, list of `recipients` (each with connector-agnostic `recipient_id`, contact identifiers, metadata).
- Backends send chunks via `POST {connector.transport_endpoint}/transport/broadcasts/chunks`, reusing service key + connector id headers defined today for single deliveries.
- Response contract (`BroadcastChunkResponse`) carries per-recipient statuses plus chunk-level summary; backend persists results regardless of connector type.
- Connectors that do not implement the endpoint ignore `supports_broadcast`, so backend blocks creation up front.

### Telegram-Specific Implementation
- Telegram module implements the generic `/transport/broadcasts/chunks` hook by mapping recipient identifiers to `chat_id`, reusing existing bot runtime, retries, and rate limits; no Telegram-only fields leak into shared contracts.
- Module-level settings define `max_recipients_per_chunk` and throttling defaults; connectors of other types can pick their own numbers while adhering to the same schema.
- Existing `/transport/delivery` keeps handling real-time messages; only the new service touches broadcast chunks, so other transports can replicate the pattern without inheriting Telegram code.

### Processing & Worker Flow
- Backend worker (async loop, Dramatiq, Celery, etc.) polls broadcasts with status `queued`, transitions to `in_progress`, then repeatedly:
  1. Fetch next N pending recipients (bounded by connector chunk limit and rate throttles).
  2. Assemble payload chunk, assign deterministic `chunk_id`, send to connector broadcast endpoint.
  3. Update per-recipient status + message log rows (with `broadcast_id`), adjust aggregate counters.
- Worker handles retries per chunk (e.g., exponential backoff) and flips broadcast to `failed` if max retry budget exhausted; success path marks broadcast `completed` once all recipients exit pending.
- Ensure worker respects Telegram Bot API throughput (e.g., 30 msg/sec per bot) by inserting paced delays or concurrency caps.

### Phase 2 – Live Progress Feeds (ship right after core MVP)
- Once chunk processing is reliable, expose progress via Server-Sent Events (or WebSockets if infra prefers) from backend: `GET /transport/broadcasts/{broadcast_id}/stream`.
- Stream emits broadcast-level counters (pending/sent/failed) and chunk progress payloads so UI can update charts without polling.
- Worker publishes updates to an internal channel (async queue / Redis pub-sub); SSE handler fans them out with backpressure + auth identical to REST endpoints.
- This enhancement is mandatory immediately after the base functionality so dashboards stay reactive for large batches.

## Optional Enhancements
- Template variables (optional but recommended): allow `{first_name}`-style placeholders rendered server-side per recipient before chunk dispatch.
- Failure export endpoint (optional): `POST /transport/broadcasts/{broadcast_id}/export` to download failed rows as CSV for manual outreach/audit.

## Risks / Open Questions
- Recipient data validity: callers must supply correct identifiers (chat_id/phone/etc.); backend skips or rejects rows lacking required data instead of guessing.
- Rate limiting & fairness: connectors shoulder pacing; backend just obeys `max_broadcast_chunk`, so lack of throttling becomes connector-specific risk.
- Storage growth: `broadcast_recipients` may swell; explore post-delivery summarization/archival if we need more efficient retention (open question).
- Security & compliance: current endpoints run under service-key auth without roles; acceptable for test environments, but full RBAC/audit switch can come later.

## Rollback Strategy
- Because broadcasts are additive, rollback is primarily schema-level: drop new tables (`broadcasts`, `broadcast_recipients`) and remove new routes/services if feature is disabled.
- Transport modules can keep broadcast endpoint behind feature flag; disable flag to fall back to single-message delivery without touching data.


