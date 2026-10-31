# CI/CD Documentation

Continuous Integration and Deployment workflows.

## CI Pipeline

GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every push and pull request.

### Jobs

#### 1. Lint Job

**Triggers:** All pushes and PRs

**Steps:**
1. Checkout repository
2. Set up uv (package manager)
3. Set up Python 3.12
4. Install dependencies (`uv sync --all-packages`)
5. Run pre-commit hooks (linting, formatting, secrets detection)

**Timeout:** 10 minutes

**Failure:** Blocks other jobs

#### 2. Test Job

**Triggers:** After lint passes

**Matrix Strategy:**
- Tests run for: `sales-agent`, `backend`
- Each module tested independently
- `fail-fast: false` - All modules tested even if one fails

**Steps:**
1. Checkout repository
2. Set up uv and Python 3.12
3. Install dependencies
4. Run tests: `uv run --directory apps/${{ matrix.app }} pytest -q`

**Timeout:** 20 minutes

**Output:** Test results per module

#### 3. Docker Build Job

**Triggers:** After lint passes

**Matrix Strategy:**
- Builds images for: `backend`, `sales-agent`
- Each service has specific build args:
  - `backend`: `package=backend`, `app_path=apps/backend`, `pythonpath_suffix=""`, `uvicorn_module_path=src.backend.main:app`
  - `sales-agent`: `package=sales-bot`, `app_path=apps/sales-agent`, `pythonpath_suffix=""`, `uvicorn_module_path=src.sales_agent.main:app`

**Steps:**
1. Checkout repository
2. Set up Docker Buildx
3. Login to GitHub Container Registry (optional)
4. Build image with cache:
   - Uses GitHub Actions cache (`cache-from: type=gha`)
   - Writes cache (`cache-to: type=gha,mode=max`)
   - Tags: `ghcr.io/aigency-ru/<service>:ci-<sha>`
   - Push: `false` (images not published by default)

**Timeout:** Default (no explicit timeout)

## Adding New Modules to CI

### 1. Add to Test Matrix

Edit `.github/workflows/ci.yml`:

```yaml
strategy:
  matrix:
    app:
      - sales-agent
      - backend
      - new-module  # Add here
```

### 2. Add to Docker Build Matrix

Edit `.github/workflows/ci.yml`:

```yaml
matrix:
  include:
    # ... existing entries ...
    - service: new-module
      package: new-module
      app_path: apps/new-module
      pythonpath_suffix: ""  # or "/src" if needed
      uvicorn_module_path: new_module.main:app  # adjust path
```

### 3. Verify Package Name

Ensure `apps/new-module/pyproject.toml` has correct `[project].name` matching the `package` in CI config.

## Pre-commit Hooks

Configured in `.pre-commit-config.yaml`. Hooks run automatically on commit and in CI.

**Hooks:**
- `ruff` - Formatting and linting
- `detect-secrets` - Secret detection
- Other hooks as configured

**Manual Run:**
```bash
uv run pre-commit run --all-files
```

## Docker Image Publishing

Images are built but not published by default. To enable publishing:

1. Set `push: true` in `.github/workflows/ci.yml`
2. Ensure `GITHUB_TOKEN` has write permissions
3. Images will be tagged and pushed to `ghcr.io/aigency-ru/<service>:ci-<sha>`

## Deployment Process

Deployment is not automated in current CI. Manual deployment:

1. Build images locally or in CI
2. Push to registry
3. Deploy to target environment (Kubernetes, Cloud Run, etc.)

## CI Environment Variables

CI uses default environment (no secrets required for lint/test).

For Docker builds requiring secrets:
- Add secrets to GitHub repository settings
- Reference in workflow: `${{ secrets.SECRET_NAME }}`

## Test Coverage

Current CI runs tests but doesn't enforce coverage thresholds. To add:

1. Install coverage tool: `pytest-cov`
2. Run with coverage: `pytest --cov=src --cov-report=xml`
3. Upload coverage: Use `codecov` or similar action
4. Set coverage threshold in workflow

## Failure Handling

- **Lint failures:** Block all other jobs
- **Test failures:** Reported per module, don't block Docker builds
- **Docker build failures:** Reported per service, don't block other builds

## Local CI Simulation

Run CI steps locally:

```bash
# Lint
uv run pre-commit run --all-files

# Test all modules
just test

# Test specific module
cd apps/backend && uv run pytest

# Build Docker image
docker compose build backend
```

## Workflow Triggers

- **Push:** Any branch
- **Pull Request:** Any branch
- **Manual:** Can be triggered manually from GitHub Actions UI

## Permissions

Workflow uses `contents: read` permission (read-only access to repository).

For publishing images, may need `contents: write` or `packages: write`.

## Caching

- **uv dependencies:** Cached by `setup-uv` action
- **Docker layers:** Cached via GitHub Actions cache (`type=gha`)
- **Python:** Cached by `setup-python` action

## Performance

- Lint: ~2-5 minutes
- Tests: ~5-15 minutes (depends on module)
- Docker builds: ~5-10 minutes per service (with cache)

Total pipeline time: ~15-30 minutes (parallel jobs).
