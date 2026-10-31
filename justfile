set shell := ["bash", "-euo", "pipefail", "-c"]

# Dev server ports
sales_agent_port := "8080"
backend_port := "8081"
telegram_port := "8082"
wappi_port := "8083"
wazzup_port := "8084"

modules := "backend sales-agent telegram-module wappi-module wazzup-module"

choose:
    @just --justfile {{justfile()}} --choose

# ── Setup ──────────────────────────────────────────────

# Bootstrap project environment (create .env.shared from template)
bootstrap:
    #!/usr/bin/env bash
    if [[ -f .env.shared ]]; then
        echo ".env.shared already exists"
    elif [[ -f .env.shared.example ]]; then
        cp .env.shared.example .env.shared
        echo "Created .env.shared from template"
    else
        echo "Missing .env.shared.example template"
        exit 1
    fi

# Install dependencies and pre-commit hooks
install:
    #!/usr/bin/env bash
    uv sync
    uv run pre-commit install
    for module in {{modules}}; do
        echo "Installing pre-commit hooks in apps/$module..."
        (cd "apps/$module" && uv run pre-commit install)
    done

# ── Infrastructure ─────────────────────────────────────

# Start infrastructure (Redis). Optional local S3: `just infra-minio` or
# `docker compose --profile minio up -d minio`
infra:
    docker compose up -d redis

# Redis + MinIO for local S3-compatible storage
infra-minio:
    docker compose --profile minio up -d redis minio

# Stop infrastructure services
infra-down:
    docker compose down

# ── Development ────────────────────────────────────────

# Run selected apps in parallel (comma-separated or "all")
# Examples: just dev all | just dev backend,sales-agent | just dev task-scheduler,backend
dev apps="all":
    #!/usr/bin/env bash
    set -a
    source "{{justfile_directory()}}/.env.shared.dev"
    set +a

    # Override Docker hostnames → localhost for native dev
    export REDIS__URL="redis://localhost:6379"
    export BACKEND__URL="http://localhost:{{backend_port}}/api/v1"
    export SALES_AGENT__URL="http://localhost:{{sales_agent_port}}"
    export TRANSPORT__WAPPI__URL="http://localhost:{{wappi_port}}"
    export TRANSPORT__TELEGRAM__URL="http://localhost:{{telegram_port}}"
    export TRANSPORT__WAZZUP__URL="http://localhost:{{wazzup_port}}"

    if [[ "{{apps}}" == "all" ]]; then
        selected="backend sales-agent telegram-module wappi-module wazzup-module"
    else
        selected=$(echo "{{apps}}" | tr ',' ' ')
    fi
    procfile=$(mktemp /tmp/pulse-procfile.XXXXXX)
    trap "rm -f $procfile" EXIT
    for app in $selected; do
        case $app in
            backend)
                echo "backend: cd {{justfile_directory()}}/apps/backend && exec uv run uvicorn src.backend.main:app --host 0.0.0.0 --port {{backend_port}} --reload" >> "$procfile"
                ;;
            sales-agent)
                echo "sales-agent: cd {{justfile_directory()}}/apps/sales-agent && exec uv run uvicorn src.sales_agent.main:app --host 0.0.0.0 --port {{sales_agent_port}} --reload" >> "$procfile"
                ;;
            telegram-module)
                echo "telegram: cd {{justfile_directory()}}/apps/telegram-module && exec uv run uvicorn telegram_module.main:app --host 0.0.0.0 --port {{telegram_port}} --reload" >> "$procfile"
                ;;
            wappi-module)
                echo "wappi: cd {{justfile_directory()}}/apps/wappi-module && exec uv run uvicorn wappi_module.main:app --host 0.0.0.0 --port {{wappi_port}} --reload" >> "$procfile"
                ;;
            wazzup-module)
                echo "wazzup: cd {{justfile_directory()}}/apps/wazzup-module && exec uv run uvicorn wazzup_module.main:app --host 0.0.0.0 --port {{wazzup_port}} --reload" >> "$procfile"
                ;;
            workers)
                echo "workers: cd {{justfile_directory()}}/apps/backend && WORKERS=all exec uv run python -m src.backend.workers.hub" >> "$procfile"
                ;;
            task-scheduler)
                echo "scheduler: cd {{justfile_directory()}}/apps/backend && WORKERS=task_scheduler exec uv run python -m src.backend.workers.hub" >> "$procfile"
                ;;
            *)
                echo "Unknown app: $app"
                echo "Available: backend, sales-agent, telegram-module, wappi-module, wazzup-module, workers, task-scheduler"
                exit 1
                ;;
        esac
    done
    uv run honcho start -f "$procfile"

# Trigger config reload for a transport module
reload module:
    #!/usr/bin/env bash
    case "{{module}}" in
        telegram-module) curl -sS -X POST "http://localhost:{{telegram_port}}/admin/reload" ;;
        wappi-module)    curl -sS -X POST "http://localhost:{{wappi_port}}/admin/reload" ;;
        wazzup-module)   curl -sS -X POST "http://localhost:{{wazzup_port}}/admin/reload" ;;
        *) echo "Reload only available for: telegram-module, wappi-module, wazzup-module"; exit 1 ;;
    esac

# ── Testing ────────────────────────────────────────────

# Run tests (all modules in parallel, or specify one)
# Single module: full interactive output. All: quiet with summary.
test module="all":
    #!/usr/bin/env bash
    if [[ "{{module}}" != "all" ]]; then
        cd "apps/{{module}}" && uv run pytest
        exit $?
    fi

    modules=(backend sales-agent telegram-module wappi-module wazzup-module)
    tmpdir=$(mktemp -d /tmp/pulse-tests.XXXXXX)
    trap "rm -rf $tmpdir" EXIT

    for module in "${modules[@]}"; do
        (cd "apps/$module" && uv run pytest 2>&1 > "$tmpdir/$module.out"; echo $? > "$tmpdir/$module.rc") &
    done
    wait

    failed=()
    for module in "${modules[@]}"; do
        rc=$(cat "$tmpdir/$module.rc")
        if [[ "$rc" -eq 0 ]]; then
            echo "✓ $module"
        else
            echo "✗ $module"
            failed+=("$module")
        fi
    done

    echo ""
    if [[ ${#failed[@]} -eq 0 ]]; then
        echo "All tests passed!"
        exit 0
    fi

    for module in "${failed[@]}"; do
        echo "═══════════════════════════════════════"
        echo " $module (last 30 lines)"
        echo "═══════════════════════════════════════"
        tail -30 "$tmpdir/$module.out"
        echo ""
    done

    echo "To rerun failed modules:"
    for module in "${failed[@]}"; do
        echo "  just test $module"
    done
    exit 1

# Run tests with coverage
test-cov:
    cd apps/sales-agent && uv run pytest --cov=src.sales_agent

# ── Linting ────────────────────────────────────────────

# Run linters (all modules in parallel, or specify one)
lint module="all":
    #!/usr/bin/env bash
    if [[ "{{module}}" == "all" ]]; then
        just _lint-all
    else
        just "_lint-{{module}}"
    fi

[private]
_lint-all: _lint-backend _lint-sales-agent _lint-telegram-module _lint-wappi-module _lint-wazzup-module

[private]
_lint-backend:
    cd apps/backend && uv run ruff check src tests && uv run ruff format --check src tests

[private]
_lint-sales-agent:
    cd apps/sales-agent && uv run ruff check src tests && uv run ruff format --check src tests

[private]
_lint-telegram-module:
    cd apps/telegram-module && uv run ruff check src tests && uv run ruff format --check src tests

[private]
_lint-wappi-module:
    cd apps/wappi-module && uv run ruff check src tests && uv run ruff format --check src tests

[private]
_lint-wazzup-module:
    cd apps/wazzup-module && uv run ruff check src tests && uv run ruff format --check src tests

# ── Scripts ─────────────────────────────────────────────

# List available scripts
scripts:
    #!/usr/bin/env bash
    root="{{justfile_directory()}}"
    echo "Backend scripts (apps/backend/scripts/):"
    for f in "$root/apps/backend/scripts/"*.py; do
        [[ -f "$f" ]] || continue
        name=$(basename "$f" .py)
        desc=$(sed -n '2s/^"""\?//p; 2s/\?"""$//p' "$f" 2>/dev/null | head -1 || true)
        printf "  %-25s %s\n" "$name" "$desc"
    done
    echo ""
    echo "Manual tests: just manual-tests"
    echo ""
    echo "Usage: just script <name> [args...]"
    echo ""
    echo "Examples:"
    echo "  just script dump_company_config dump 1"
    echo "  just script dump_company_config restore company_dumps/foo.json --company-name New"
    echo "  just script wipe_customer"

# Run a backend script (apps/backend/scripts/<name>.py)
script name *args:
    #!/usr/bin/env bash
    root="{{justfile_directory()}}"
    script="$root/apps/backend/scripts/{{name}}.py"
    if [[ ! -f "$script" ]]; then
        echo "Script not found: $script"
        echo "Run 'just scripts' to list available scripts"
        exit 1
    fi
    cd "$root/apps/backend" && uv run -m scripts.{{name}} {{args}}

# ── Manual Testing ────────────────────────────────────

# List available manual tests
manual-tests:
    #!/usr/bin/env bash
    echo "Available manual tests:"
    echo ""
    for f in scripts/manual_testing/test_*.py; do
        name=$(basename "$f" .py | sed 's/^test_//')
        desc=$(sed -n '2s/^"""//p' "$f" 2>/dev/null || true)
        printf "  %-25s %s\n" "$name" "$desc"
    done
    echo ""
    echo "Usage: just manual <name> [env vars]"
    echo "Example: just manual yclients YCLIENTS_PARTNER_TOKEN=xxx YCLIENTS_COMPANY_ID=123"

# Run a manual test by name (without test_ prefix)
# Args with '=' are exported as env vars, the rest are passed to the script.
# Example: just manual yclients_booking YCLIENTS_PARTNER_TOKEN=xxx YCLIENTS_COMPANY_ID=123 all
manual name *args:
    #!/usr/bin/env bash
    script="scripts/manual_testing/test_{{name}}.py"
    if [[ ! -f "$script" ]]; then
        echo "Test not found: $script"
        echo "Run 'just manual-tests' to list available tests"
        exit 1
    fi
    script_args=()
    for arg in {{args}}; do
        if [[ "$arg" == *=* ]]; then
            export "$arg"
        else
            script_args+=("$arg")
        fi
    done
    export PYTHONPATH="{{justfile_directory()}}/apps/backend:${PYTHONPATH:-}"
    uv run --package manual-testing python "$script" "${script_args[@]}"

# ── Database (backend only) ────────────────────────────

# Initialize database schema and create initial migration
db-init:
    cd apps/backend && uv run aerich init-db

# Create a new database migration
migrate-create:
    cd apps/backend && uv run aerich migrate --name auto

# Apply database migrations
migrate-apply:
    cd apps/backend && uv run aerich upgrade

# Show migration history
migrate-history:
    cd apps/backend && uv run aerich history
