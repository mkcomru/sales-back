# Plan 009 — Sales Envelope Abstraction (Step 1 of 2)

## Objective
Abstract Sales ingestion to a single normalized envelope. Managed connectors use service key auth; custom connectors use per-connector API keys. Connectors become stateless producers. Token validation delegated to backend (forward-compatible with Plan 010).

## Scope
- **In scope:** Sales inbound endpoint, unified connectors table, connector auth model, Telegram/Wappi module adaptation
- **Out of scope:** Outbound transport (unchanged), Bitrix module (legacy, ignored)
- **No backward compatibility** — full migration

---

## Contract Specification

### Endpoint
```
POST /api/v1/messages/inbound
Content-Type: application/json

# Custom connectors:
Authorization: Bearer sk_xxx

# Managed connectors:
X-Service-Key: {shared_service_key}
X-Connector-Id: {connector_id}
```

### Envelope Schema
```python
class InboundEnvelope(BaseModel):
    conversation_id: str   # provider-determined (chat.id in Telegram, chatId in Wappi)
    user_id: str           # message sender
    text: str | None       # message content (None if audio-only)
    ts: float              # Unix timestamp

    audio: AudioData | None = None

class AudioData(BaseModel):
    bytes_base64: str
    mime: str = "audio/ogg"
```

`conversation_id` is opaque to Sales — connector extracts from provider payload, Sales uses for debounce bucketing.

### Auth Flow (Dual-Path)

**Custom connectors** (user's code):
```
Authorization: Bearer sk_xxx
```
1. Sales extracts Bearer token
2. Sales calls backend: `GET /internal/connectors/validate` with Bearer token
3. Backend hashes token, looks up `connector_api_keys`, loads connector
4. Backend returns `ConnectorContext` or 401/403
5. Sales processes with validated context

**Managed connectors** (our modules):
```
X-Service-Key: {shared_service_key}
X-Connector-Id: tg-bot-123
```
1. Sales validates service key (existing pattern)
2. Sales calls backend: `GET /internal/connectors/{connector_id}` with service key
3. Backend returns `ConnectorContext`
4. Sales processes with validated context

```python
class ConnectorContext(BaseModel):
    connector_id: str
    company_id: int
    channel_type: str
    debounce: DebounceConfig

class DebounceConfig(BaseModel):
    window_seconds: int
    storage_key_template: str  # e.g. "{connector_id}:{conversation_id}"
```

### Token Format (Custom Connectors Only)
- Prefix: `sk_` (standard connector key)
- Generated on connector creation, displayed once
- Stored as `sha256(key)` in `connector_api_keys` table
- Managed connectors don't use API keys — they use service key

### Response Contract
| Status | Reason | Body |
|--------|--------|------|
| `202 Accepted` | Queued | `{"status": "accepted"}` |
| `401 Unauthorized` | Missing header | `{"error": "missing_token"}` |
| `401 Unauthorized` | Malformed header | `{"error": "malformed_token"}` |
| `403 Forbidden` | Token not found | `{"error": "invalid_token"}` |
| `403 Forbidden` | Connector disabled | `{"error": "connector_disabled"}` |
| `422 Unprocessable Entity` | Bad envelope | `{"error": "validation_error", "detail": [...]}` |
| `503 Service Unavailable` | Not ready | `{"error": "service_unavailable"}` |

---

## Data Model

### Unified Connectors Table
Replaces separate `TelegramBot` / `WappiConnector` tables with single abstract model:

```python
class ConnectorType(str, Enum):
    TELEGRAM = "telegram"
    WAPPI = "wappi"
    CUSTOM = "custom"           # no built-in platform support

class Connector(BaseModel):
    id: int (PK)
    connector_id: str (unique)      # public identifier, e.g. "tg-company-bot"
    company_id: FK to Company
    type: ConnectorType             # for config validation/routing
    channel_type: str               # "telegram", "whatsapp", "custom", etc.
    display_name: str               # UI label, especially useful for custom connectors
    managed: bool                   # True = we run connector module; False = customer sends directly
    config: JSONB                   # platform credentials (for managed connectors)
    enabled: bool
    debounce_window_seconds: int = 45
    debounce_storage_key_template: str = "{connector_id}:{conversation_id}"
    created_at, updated_at

class ConnectorApiKey(BaseModel):
    id: int (PK)
    key_hash: str (unique)          # sha256(raw_key)
    connector_id: FK to Connector   # clean FK!
    enabled: bool
    created_at
```

### Managed vs Custom Connectors
| Type | `managed` | Who runs code | Auth to Sales | `config` contains |
|------|-----------|---------------|---------------|-------------------|
| telegram | `True` | Our telegram-module | Service Key + `X-Connector-Id` | bot_token, webhook_secret, ... |
| wappi | `True` | Our wappi-module | Service Key + `X-Connector-Id` | wappi_token, wappi_profile_id, ... |
| custom | `False` | Customer's code | Bearer `sk_xxx` | Optional metadata only |

**Flow:**
- Managed: Platform → Our Connector Module → Sales API (service key auth)
- Custom: Platform → Customer's Code → Sales API (API key auth)

### Type-Specific Config (validated at app layer)
```python
class TelegramConnectorConfig(BaseModel):
    """Platform credentials for telegram-module to use."""
    bot_token: str
    mode: str = "auto"
    webhook_secret: str | None = None
    webhook_path: str | None = None

class WappiConnectorConfig(BaseModel):
    """Platform credentials for wappi-module to use."""
    wappi_token: str
    wappi_profile_id: str
    transport_endpoint: str

class CustomConnectorConfig(BaseModel):
    """No platform credentials — customer handles their side."""
    pass  # empty, just validates as valid JSON
```

Config validated by Pydantic based on `Connector.type` field.

### Legacy Models (deprecated, not deleted)
- `TelegramBot` — mark deprecated, keep for data migration
- `WappiConnector` — mark deprecated, keep for data migration

Remove after data fully migrated to unified `Connector` table.

---

## Architecture Notes

### Envelope → IncomingMessage Mapping
Sales maps `InboundEnvelope` + `ConnectorContext` → `IncomingMessage` for debouncer:
- Enriches with `connector_id`, `company_id`, `channel_type` from context
- Computes `storage_key` from template
- Sets `debounce_seconds` from config
- Transforms `audio` → `attachments` list

### Forward Compatibility (Plan 010)
When backend becomes ingress router:
- Connector → Backend (validates token, gates, routes)
- Backend → Sales (X-Service-Key + `ConnectorContext` in body, no Bearer token)
- Sales trusts backend, no token validation code to remove

---

## Tasks

### 1. Backend: Unified Connectors Model
- [ ] Create `Connector` model with `type`, `config` JSONB, clean FK to Company
- [ ] Create `ConnectorApiKey` model with FK to `Connector`
- [ ] Add Pydantic config validators: `TelegramConnectorConfig`, `WappiConnectorConfig`
- [ ] Mark `TelegramBot`, `WappiConnector` as deprecated (keep models, add comment)
- [ ] Migration: copy data from legacy tables → unified `Connector` table

### 2. Backend: API Key Infrastructure
- [ ] Key generation on connector create (return raw key once, store hash)
- [ ] `GET /internal/connectors/validate` — hash Bearer token → find key → load connector → build `ConnectorContext` (custom connectors)
- [ ] `GET /internal/connectors/{connector_id}` — load connector by ID → build `ConnectorContext` (managed connectors, service key auth)
- [ ] Update `/transport/connectors` to read from unified table

### 3. Sales Agent: Inbound Endpoint
- [ ] Create `POST /api/v1/messages/inbound`
- [ ] Dual-auth: Bearer token → `/internal/connectors/validate`, OR service key + `X-Connector-Id` → `/internal/connectors/{id}`
- [ ] Map `(envelope, context)` → `IncomingMessage` for debouncer
- [ ] Stop mounting provider-specific routers (keep code)

### 4. Connector Adaptation (Managed)
- [ ] **telegram-module**: Normalize Telegram update → `InboundEnvelope`, POST with service key + `X-Connector-Id`
- [ ] **wappi-module**: Normalize Wappi webhook → `InboundEnvelope`, POST with service key + `X-Connector-Id`
- [ ] Remove `X-Company-Id` header (derived from connector lookup)
- [ ] Keep audio bytes download in connectors

### 5. Shared Library
- [ ] Add `InboundEnvelope`, `AudioData` schemas to `libs/common`
- [ ] Add `SalesAgentInboundClient` with dual auth support (service key for managed, Bearer for custom)

### 6. Tests
- [ ] Unified connector CRUD + config validation
- [ ] Token validation: missing, malformed, invalid, disabled
- [ ] Envelope validation: required fields, optional audio
- [ ] E2E: connector → Sales → backend validation flow

---

## Risks / Notes
- **Token compromise**: Regenerate via backend, single key per connector
- **Debounce hot-swap**: Config loaded per-request via backend call, no token reissue needed

## Dependency
- Step 2 (Plan 010: backend as router) depends on this plan
