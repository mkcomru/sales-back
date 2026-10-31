# Development Workflows

Common development tasks and workflows.

## Adding a New Module

1. **Create module directory:**
   ```bash
   mkdir -p apps/new-module/src/new_module
   ```

2. **Create `pyproject.toml`:**
   ```toml
   [project]
   name = "new-module"
   dependencies = [
       "common = { workspace = true }",
       "fastapi",
       "uvicorn[standard]",
   ]
   ```

3. **Add to workspace:**
   Edit root `pyproject.toml`:
   ```toml
   [tool.uv.workspace]
   members = [
       # ... existing members ...
       "apps/new-module",
   ]
   ```

4. **Sync dependencies:**
   ```bash
   uv sync
   ```

5. **Create settings class:**
   In `libs/common/src/common/config.py`, add:
   ```python
   class NewModuleSettings(CommonSettingsBase):
       # Module-specific settings
   ```

6. **Add to CI:**
   Edit `.github/workflows/ci.yml` to include new module in test matrix.

## Common Commands (justfile)

Корневой `justfile` — эталон для запуска задач. Команды из корня репозитория:

### Running Tests

```bash
# Run tests in all modules
just test

# Run tests in specific module
just test backend
just test sales-agent
```

### Database Operations (Backend only)

```bash
just db-init           # Initialize schema, create initial migration
just migrate-create    # Create new migration
just migrate-apply     # Apply migrations
just migrate-history   # Show migration history
```

### Environment Setup

```bash
just bootstrap   # Create .env.shared from template
just install     # uv sync + pre-commit hooks
```

## Database Migration Workflow

Only Backend has migrations. Sales-agent and transports are stateless.

### Creating a Migration

1. **Modify models** in `apps/backend/src/backend/modules/<domain>/` (каждый домен — свой модуль)

2. **Generate migration:**
   ```bash
   cd apps/backend
   uv run aerich migrate --name descriptive_name
   ```

3. **Edit migration file:**
   - Open `migrations/models/###_descriptive_name.py`
   - Add schema prefix to all table references:
     ```python
     # Before
     CREATE TABLE "users" (...)
     
     # After
     CREATE TABLE "schema_name"."users" (...)
     ```
   - Apply same fix to downgrade section

4. **Apply migration:**
   ```bash
   uv run aerich upgrade
   ```

### Schema Names

- Backend: `backend`

## Adding Dependencies

### To Shared Library (`libs/common`)

1. Edit `libs/common/pyproject.toml`
2. Run `uv sync` from repo root
3. All modules automatically get access

### To Specific Module

1. Edit `apps/<module>/pyproject.toml`
2. Run `uv sync` from repo root
3. Only that module gets the dependency

## Running Services Locally

### Individual Services

```bash
# Backend
cd apps/backend
uv run uvicorn src.backend.main:app --reload

# Sales Agent
cd apps/sales-agent
uv run uvicorn src.sales_agent.main:app --reload

# Telegram Module
cd apps/telegram-module
uv run uvicorn telegram_module.main:app --reload

# Wappi Module
cd apps/wappi-module
uv run uvicorn wappi_module.main:app --reload

```

### Using justfile

Запуск сервисов из корня репозитория:

```bash
just dev all                    # Все сервисы
just dev backend,sales-agent    # Выборочно
just dev backend                # Один модуль
```

### Service Startup Order

1. Start Redis (if using eventing):
   ```bash
   docker compose up redis
   ```

2. Start Backend:
   ```bash
   just dev backend
   ```

3. Start Sales Agent:
   ```bash
   just dev sales-agent
   ```

4. Start transport modules:
   ```bash
   just dev telegram-module
   cd apps/wappi-module && uv run uvicorn wappi_module.main:app --reload
   ```

## Debugging Tips

### Check Service Health

```bash
# Backend
curl http://localhost:8081/health

# Sales Agent
curl http://localhost:8000/healthz

# Transport modules
curl http://localhost:8082/healthz
```

### View Logs

Services use structured logging (structlog, JSON format):

```bash
# Filter by event
docker compose logs backend | grep "event.received"

# Filter by connector
docker compose logs telegram-module | grep "connector_id=tg-bot-123"

# Follow logs
docker compose logs -f backend
```

### Common Issues

**Service won't start:**
- Check `.env.shared` exists and has required variables
- Check module `.env` file exists
- Check database is accessible
- Check Redis is accessible (if eventing enabled)

**Migrations fail:**
- Ensure schema prefix is added to migration SQL
- Check database connection string
- Verify schema exists (run `aerich init-db` first)

**Connector not found:**
- Check backend is running
- Check `SERVICE__API_KEY` matches across services
- Check connector exists in backend database
- Check `EVENTING__STREAM__GROUP` is unique per module

**Messages not routing:**
- Check backend logs for routing decisions
- Verify `assistant_active` status in thread
- Check transport module logs for delivery attempts
- Verify connector type matches transport module

## Code Quality

### Formatting

```bash
# Format code
uv run ruff format .

# From module directory
cd apps/backend
uv run ruff format .
```

### Linting

```bash
# Lint and auto-fix
uv run ruff check --fix .

# From module directory
cd apps/backend
uv run ruff check --fix .
```

### Type Checking

```bash
# If pyright config exists
uv run pyright

# From module directory
cd apps/backend
uv run pyright
```

### Pre-commit Hooks

Hooks run automatically on commit. Manual run:

```bash
uv run pre-commit run --all-files
```

## Testing

### Run All Tests

```bash
make test
```

### Run Module Tests

```bash
cd apps/backend
uv run pytest

# With coverage
uv run pytest --cov=src.backend

# Specific test file
uv run pytest tests/domains/chat/test_service.py

# Specific test
uv run pytest tests/domains/chat/test_service.py::test_create_thread
```

### Test Patterns

- Unit tests: `tests/unit/` or `tests/domains/<module>/test_*.py`
- Integration tests: `tests/integration/` or `tests/domains/<module>/test_*_integration.py`
- Use fixtures from `tests/conftest.py`
- Mock external dependencies (HTTP clients, databases)

## Git Workflow

1. Create feature branch: `git checkout -b feature/my-feature`
2. Make changes
3. Run tests: `just test` or `just test <module>`
4. Format and lint: `uv run ruff format . && uv run ruff check --fix .`
5. Commit with clear message
6. Push and create PR

## Adding New Endpoints

1. **Create router** in `apps/<module>/src/<module>/api/routers.py` or module-specific router file
2. **Add to main app:**
   ```python
   from my_module.api.routers import router
   app.include_router(router)
   ```
3. **Add authentication** if needed (service key or user auth)
4. **Add tests** for new endpoint
5. **Update API documentation** if public endpoint

## Adding New Models (Backend only)

1. **Create model** in `apps/backend/src/backend/modules/<domain>/` (models.py или models/)
2. **Set schema** if using PostgreSQL:
   ```python
   class Meta:
       table = "my_table"
       schema = "schema_name"
   ```
3. **Create migration:**
   ```bash
   just migrate-create
   # или: cd apps/backend && uv run aerich migrate --name add_my_table
   ```
4. **Fix schema prefix** in migration file
5. **Apply migration:** `just migrate-apply`

## Environment Variables

### Adding New Variable

1. **Add to settings class** in `libs/common/src/common/config.py`:
   ```python
   class MySettings(BaseModel):
       my_var: str = Field(alias="MY_MODULE__MY_VAR")
   ```
2. **Add to module settings:**
   ```python
   class MyModuleSettings(CommonSettingsBase):
       my_settings: MySettings = Field(default_factory=MySettings)
   ```
3. **Document** in `docs/configuration.md`
4. **Add to `.env.example`** if module-specific

## Troubleshooting

### Import Errors

- Ensure `uv sync` was run after adding dependencies
- Check `pyproject.toml` has correct package name
- Verify workspace member is listed in root `pyproject.toml`

### Database Connection Errors

- Check `DATABASE__URL` in `.env.shared`
- Verify PostgreSQL is running
- Check schema exists (run `aerich init-db`)

### Service Communication Errors

- Verify `SERVICE__API_KEY` matches across services
- Check `BACKEND__URL` is correct
- Check service is running and healthy
- Check network connectivity between services

### Eventing Not Working

- Verify `EVENTING__ENABLED=true`
- Check `REDIS__URL` is set
- Verify `EVENTING__STREAM__GROUP` is unique per module
- Check Redis is accessible
- Check consumer group exists in Redis
