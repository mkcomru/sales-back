# Configuration Reference

Complete guide to environment variables and configuration settings.

## Environment Variable Naming

Variables use **double underscores** (`__`) as nested separators. Pydantic-settings automatically maps them to nested objects:

- `DATABASE__URL` → `settings.database.url`
- `LLM__OPENAI__API_KEY` → `settings.llm.openai.api_key`
- `BACKEND__URL` → `settings.backend.url`

## Configuration Loading Order

1. **Shared defaults** - `.env.shared` (or `.env.shared.{environment}` if `ENV` is explicitly set)
2. **Module-specific** - `apps/<module>/.env` (or `apps/<module>/.env.{environment}`)

If `ENV` or `APP__ENVIRONMENT` is explicitly set, only environment-specific files are loaded (no fallback to base files).

## Shared Configuration (`.env.shared`)

These variables are used by all modules:

### Database

- `DATABASE__URL` (required) - PostgreSQL connection string
  - Format: `postgresql://user:your_password_here@host:port/database`
  - Example: `postgresql://postgres:your_password_here@localhost:5432/sales_bot`

### Redis

- `REDIS__URL` (optional) - Redis connection string
  - Format: `redis://host:port` or `redis://:your_password_here@host:port`
  - Required if `EVENTING__ENABLED=true`

### Service Authentication

- `SERVICE__API_KEY` (required) - Shared secret for service-to-service authentication
  - Used in `X-Service-Key` header
  - Must match across all services

### Backend Service

- `BACKEND__URL` (required for transport modules) - Backend API base URL
  - Example: `http://localhost:8081` or `https://backend.example.com`
  - Required by: telegram-module, wappi-module, sales-agent

### Sales Agent Service

- `SALES_AGENT__URL` (optional) - Sales Agent API base URL
  - Example: `http://localhost:8080` (native dev via `just dev`), `http://sales-agent:8000` (Docker)
  - Used by: backend (for routing)

### LLM Configuration

- `LLM__BASE_URL` (default: `https://api.openai.com/v1`) - LLM API base URL
- `LLM__API_KEY` (required) - LLM API key
- `LLM__LIGHT_MODEL` (default: `gpt-4o-mini`) - Model for lightweight tasks
- `LLM__LARGE_MODEL` (default: `gpt-4o`) - Model for complex tasks

### Langfuse Telemetry

- `LANGFUSE__ENABLED` (default: `false`) - Enable Langfuse tracing
- `LANGFUSE__PUBLIC_KEY` (optional) - Langfuse public key
- `LANGFUSE__SECRET_KEY` (optional) - Langfuse secret key
- `LANGFUSE__HOST` (optional) - Langfuse host URL
- `LANGFUSE__SAMPLE_RATE` (default: `1.0`) - Sampling rate (0.0-1.0)

### RAG Configuration

- `RAG__EMBEDDING__API_URL` (optional) - Embedding API URL
- `RAG__EMBEDDING__API_KEY` (optional) - Embedding API key
- `RAG__QDRANT__URL` (optional) - Qdrant vector database URL
- `RAG__QDRANT__API_KEY` (optional) - Qdrant API key
- `RAG__RERANKER__API_URL` (optional) - Reranker API URL
- `RAG__RERANKER__API_KEY` (optional) - Reranker API key

### Eventing (Redis Streams)

- `EVENTING__ENABLED` (default: `false`) - Enable event bus
- `EVENTING__BROKER` (default: `redis_streams`) - Event broker type
- `EVENTING__STREAM__NAME` (default: `backend.events`) - Stream name
- `EVENTING__STREAM__GROUP` (required if enabled) - Consumer group name (unique per module)
- `EVENTING__STREAM__CONSUMER_NAME` (default: hostname) - Consumer instance name

### CORS

- `CORS__ORIGINS` (optional) - Allowed origins (JSON array)
- `CORS__ALLOW_CREDENTIALS` (default: `false`) - Allow credentials
- `CORS__ALLOW_METHODS` (optional) - Allowed methods (JSON array)
- `CORS__ALLOW_HEADERS` (optional) - Allowed headers (JSON array)

### App Settings

- `APP__ENVIRONMENT` (default: `dev`) - Environment name (`dev`, `staging`, `prod`)
- `APP__DEBUG` (default: `false`) - Enable debug mode
- `APP__VERSION` (default: `0.1.0`) - Application version

## Module-Specific Configuration

### Backend (`apps/backend/.env`)

**Required:**

- `AUTH__JWT_SECRET_KEY` - Secret key for JWT token signing
- `AUTH__JWT_ALGORITHM` (default: `HS256`) - JWT signing algorithm
- `AUTH__ACCESS_TOKEN_EXPIRE_MINUTES` (default: `15`) - Access token expiration
- `AUTH__REFRESH_TOKEN_EXPIRE_DAYS` (default: `30`) - Refresh token expiration

**Transport URLs:**

- `TRANSPORT__TELEGRAM__URL` (optional) - Telegram module URL
- `TRANSPORT__WAPPI__URL` (optional) - Wappi module URL

### Sales Agent (`apps/sales-agent/.env`)

**Optional:**

- `BOT__TOKEN` - Bot token (legacy, может не использоваться)
- `DEBOUNCE__WINDOW_SECONDS` (default: `45`) - Global debounce window
- `DEBOUNCE__PER_CHANNEL` (optional) - Per-channel overrides (JSON object)
- `CONNECTORS_REFRESH_INTERVAL_S` (default: `1800`) - Connector config refresh interval

**Audio Transcription:**

- `AUDIO__TRANSCRIBE__ENABLED` (default: `false`) - Enable transcription
- `AUDIO__TRANSCRIBE__API_URL` (optional) - Transcription API URL
- `AUDIO__TRANSCRIBE__API_KEY` (optional) - Transcription API key
- `AUDIO__TRANSCRIBE__TIMEOUT_S` (default: `30`) - Transcription timeout
- `AUDIO__TRANSCRIBE__FFMPEG_PATH` (default: `ffmpeg`) - FFmpeg executable path

**RAG:**

- `RAG__EMBEDDING__*` - See shared RAG configuration
- `RAG__QDRANT__*` - See shared RAG configuration
- `RAG__RERANKER__*` - See shared RAG configuration

**FAQ:**

- `FAQ__ENABLED` (default: `false`) - Enable FAQ matching
- `FAQ__MATCH_THRESHOLD` (default: `0.7`) - Similarity threshold

**Humanizer:**

- `HUMANIZER__ENABLED` (default: `false`) - Enable response humanization

### Telegram Module (`apps/telegram-module/.env`)

**Optional:**

- `TELEGRAM_MODULE_PUBLIC_URL` - Public URL for webhook setup
- `TELEGRAM_MODULE_REQUEST_TIMEOUT_S` (default: `10.0`) - HTTP timeout
- `TELEGRAM_MODULE_CONFIG_REFRESH_INTERVAL_S` (default: `120.0`) - Config refresh interval
- `TELEGRAM_MODULE_SIGNATURE_TOLERANCE_S` (default: `300`) - Signature tolerance
- `TELEGRAM_MODULE_MAX_DELIVERY_ATTEMPTS` (default: `3`) - Max retry attempts
- `TELEGRAM_MODULE_ALERT_AFTER_FAILURES` (default: `2`) - Alert threshold
- `TELEGRAM_MODULE_DROP_PENDING_ON_WEBHOOK_RESET` (default: `true`) - Drop pending on reset
- `TELEGRAM_MODULE_POLLING_TIMEOUT_S` (default: `25.0`) - Polling timeout

### Wappi Module (`apps/wappi-module/.env`)

**Optional:**

- `WAPPI_MODULE_REQUEST_TIMEOUT_S` (default: `10.0`) - HTTP timeout
- `WAPPI_MODULE_CONFIG_REFRESH_INTERVAL_S` (default: `60.0`) - Config refresh interval
- `WAPPI_MODULE_MAX_DELIVERY_ATTEMPTS` (default: `3`) - Max retry attempts

## Configuration Classes

Settings are organized into Pydantic models in `libs/common/src/common/config.py`:

- `AppSettings` - Application metadata
- `DatabaseSettings` - Database connection
- `RedisSettings` - Redis connection
- `ServiceAuthSettings` - Service-to-service auth
- `BackendSettings` - Backend service URL
- `LLMSettings` - LLM configuration
- `LangfuseSettings` - Telemetry
- `EventingSettings` - Event bus
- `CorsSettings` - CORS configuration
- `RagSettings` - RAG/vector search
- `DebounceSettings` - Message debouncing
- `ConnectorSettings` - Connector configuration
- `AudioTranscribeSettings` - Audio transcription
- `FaqSettings` - FAQ matching
- `HumanizerSettings` - Response humanization

Module-specific settings classes:

- `BackendModuleSettings` - Backend-specific (adds `auth`, `transport`)
- `SalesAgentSettings` - Sales Agent-specific (adds `llm`, `rag`, `debounce`, etc.)
- `TelegramModuleSettings` - Telegram-specific (adds Telegram config)
- `WappiModuleSettings` - Wappi-specific (adds Wappi config)

## Validation

Configuration is validated at startup:

- Required fields raise `ValueError` if missing
- Eventing configuration validated if `EVENTING__ENABLED=true`
- Database URL validated when accessed
- Service URLs validated when used

## Environment-Specific Files

You can create environment-specific files:

- `.env.shared.dev` - Development shared config
- `.env.shared.prod` - Production shared config
- `apps/backend/.env.dev` - Backend dev config
- `apps/backend/.env.prod` - Backend prod config

Set `ENV=dev` or `APP__ENVIRONMENT=prod` to use environment-specific files.

## Examples

### Minimal Setup

```bash
# .env.shared
DATABASE__URL=postgresql://postgres:your_password_here@localhost:5432/sales_bot
SERVICE__API_KEY=your-secret-key-here
BACKEND__URL=http://localhost:8081
LLM__API_KEY=sk-...
```

### With Eventing

```bash
# .env.shared
DATABASE__URL=postgresql://postgres:your_password_here@localhost:5432/sales_bot
REDIS__URL=redis://localhost:6379
SERVICE__API_KEY=your-secret-key-here
BACKEND__URL=http://localhost:8081
LLM__API_KEY=sk-...
EVENTING__ENABLED=true
EVENTING__STREAM__NAME=backend.events
EVENTING__STREAM__GROUP=sales-agent  # Per module
```

### Backend Setup

```bash
# apps/backend/.env
AUTH__JWT_SECRET_KEY=your-jwt-secret-key-here
TRANSPORT__TELEGRAM__URL=http://localhost:8082
TRANSPORT__WAPPI__URL=http://localhost:8002
```

### Sales Agent Setup

```bash
# apps/sales-agent/.env
DEBOUNCE__WINDOW_SECONDS=45
CONNECTORS_REFRESH_INTERVAL_S=1800
```
