# Sales Platform Monorepo

This repository houses multiple services that share common tooling:

- `apps/backend/` – **CRM core** — companies, orders, billing, message routing, config API
- `apps/sales-agent/` – Stateless LLM executor (no DB, no migrations) — receives context, runs tool loop, returns response
- `apps/telegram-module/` – Transport module delivering messages to Telegram Bot API
- `apps/wappi-module/` – Transport module delivering messages via Wappi API (WhatsApp/Telegram)
- `libs/common/` – Shared configuration, logging, and utility models
- `docs/` – Architecture, product, and testing guides

The monorepo uses uv workspace with a single lockfile (`uv.lock`) in the root. Shared libraries live under `libs/` and are consumed via workspace dependencies.

## Configuration Model

Settings are managed through Pydantic (`pydantic-settings`) with a layered env-file strategy:

1. **Shared defaults** — create `.env.shared` in the **repository root** (same directory as this README). Contains values visible to all services (e.g., `DATABASE__URL`). **This file is git-ignored and should NOT be committed**; use `.env.shared.example` as a template.
2. **Per-service overrides** — `apps/<service>/.env` files contain module-specific secrets. Each settings class loads its own env file in addition to `.env.shared`.
3. **Base vs. module settings** — common base provides optional shared fields; modules define additional required keys via dedicated subclasses to maintain isolation.

The shared template now ships with defaults for:
- LLM access (`LLM__*`)
- Langfuse telemetry (`LANGFUSE__*`)
- Retrieval stack (`RAG__*`, `FAQ__*`)
- Core service endpoints (`BACKEND__URL`, `SALES_AGENT__URL`), debounce window, audio transcription timeouts

**Environment Variable Naming Convention:**

Keys with **double underscores** (e.g., `DATABASE__URL`) represent **nested configuration separators** used by `pydantic-settings`. The loader automatically maps:
- `DATABASE__URL` → `database.url` in the settings object
- `LLM__OPENAI__API_KEY` → `llm.openai.api_key`

This enables hierarchical grouping of related settings while keeping environment variables flat and readable.

Example workflow:

```bash
# set up shared configuration (see .env.shared.example for template)
just bootstrap
$EDITOR .env.shared

# set up the sales agent service
cd apps/sales-agent
cp .env.example .env
$EDITOR .env

# set up the Telegram transport module
cd ../telegram-module
cp .env.example .env  # create from scratch if template is absent
$EDITOR .env
```

The shared module exposes `BackendSettings`, `SalesAgentSettings`, `TelegramModuleSettings`, and `WappiModuleSettings`; each service imports only the one it needs.

## Database Architecture

- **PostgreSQL** with `backend` schema — Backend is the only module with migrations (Aerich)
- **Sales-agent**, **telegram-module**, **wappi-module** — stateless, no DB, no migrations

**⚠️ Migrations Note:** Aerich has a known limitation with PostgreSQL schemas — after running `aerich migrate`, manually edit the generated migration file to add schema qualifiers to table names. See `docs/tech.md` for details.

## Local Development

### Initial Setup

1. **Install dependencies**:
   ```bash
   # From repository root - installs all workspace packages
   uv sync
   ```

2. **Initialize database** (first time only):
   ```bash
   # Create PostgreSQL database first:
   # psql -U postgres -c "CREATE DATABASE sales_bot;"
   
   cd apps/backend
   uv run aerich init-db
   ```

3. **Run services** (from repo root):
   ```bash
   just dev all
   # or selectively:
   just dev backend,sales-agent
   just dev telegram-module
   just dev wappi-module
   ```

Shared libraries are installed automatically through the workspace when running `uv sync`.

## Docker Builds

All modules use a shared Dockerfile (`docker/python-service.Dockerfile`) with build args for configuration:

### Building Images

All builds are done through Docker Compose from the repository root:

```bash
# Build all services
docker compose build

# Build a specific service
docker compose build sales-agent

# Build without cache
docker compose build --no-cache sales-agent
```

The shared Dockerfile uses multi-stage builds with `uv` for dependency management. Each service is configured via build args in `docker-compose.yml`:
- `PACKAGE_NAME` — package name for `uv sync`
- `APP_PATH` — module path (e.g., `apps/sales-agent`)
- `PYTHONPATH_SUFFIX` — PYTHONPATH suffix (empty or `/src`)
- `UVICORN_MODULE_PATH` — uvicorn module path

### Docker Compose

The `docker-compose.yml` file in the repository root can be used to run all services together:

```bash
# Build and start all services
docker compose up --build

# Run migrations first (one-time setup)
docker compose up backend-migrations

# Start services
docker compose up backend sales-agent telegram-module wappi-module
```

All services use the shared Dockerfile with appropriate build args configured in `docker-compose.yml`.

## CI and Docker publishing

- GitHub Actions lint and build each app image on every push/PR (`.github/workflows/ci.yml`).
- Docker publishes exist but are handled on demand (see workflows under `.github/workflows/`).
