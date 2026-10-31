# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Code Architecture and Structure

This is a Python monorepo that uses `uv` workspaces. The project is structured into `apps` and `libs`.

- **`apps/`**: Contains individual services, each with its own `pyproject.toml` and dependencies.
    - `sales-agent`: The core FastAPI service with OpenAI Agents SDK integration. It handles business logic, and orchestrates calls to other services.
    - `bitrix-module`: A FastAPI service that acts as a connector to the Bitrix24 CRM.
    - `telegram-module`: A transport module for sending and receiving messages via the Telegram Bot API.
- **`libs/`**: Contains shared Python packages used by the services in `apps/`.
    - `common`: A shared library for configuration, logging, and other common utilities.
- **`docs/`**: Contains high-level documentation about the project's architecture, technology stack, and product features.
- **`plans/`**: Contains plans for complex tasks.

The database architecture is based on a shared PostgreSQL database with schema-based isolation for each service. Migrations are handled by Aerich, but require manual intervention to add schema prefixes.

## Common Development Commands

All commands should be run from the root of the respective module (e.g., `cd apps/sales-agent`). The monorepo uses `uv` for managing Python virtual environments and running commands.

- **Install dependencies for a module**:
  ```bash
  uv sync
  ```
- **Run a module in development mode**:
    - **sales-agent**:
      ```bash
      uv run uvicorn src.sales_agent.main:app --reload
      ```
    - **bitrix-module**:
      ```bash
      uv run uvicorn src.bitrix_module.main:app --reload --port 8081
      ```
    - **telegram-module**:
      ```bash
      uv run uvicorn telegram_module.main:app --reload --port 8081
      ```

- **Linting and Formatting**:
  ```bash
  uv run ruff format .
  uv run ruff check --fix
  ```

- **Type Checking**:
  ```bash
  uv run pyright
  ```

- **Running Tests**:
  - Run all tests for a module:
    ```bash
    uv run pytest
    ```
  - Run a specific test:
    ```bash
    uv run pytest tests/path/to/test.py::test_name
    ```

- **Database Migrations**:
  - **Initialize database (first time only)**:
    ```bash
    uv run aerich init-db
    ```
  - **Create a new migration**:
    ```bash
    uv run aerich migrate --name <migration_name>
    ```
    **IMPORTANT**: After creating a migration, you must manually edit the generated file to add the correct schema prefix to all table names.
  - **Apply migrations**:
    ```bash
    uv run aerich upgrade
    ```
