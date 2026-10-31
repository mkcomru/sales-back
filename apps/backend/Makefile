PORT ?= 8081

.PHONY: help test lint dev db-init migrate-create migrate-apply migrate-history

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

test: ## Run tests with pytest
	uv run pytest

lint: ## Run ruff linter and formatter
	uv run ruff check src tests
	uv run ruff format --check src tests

dev: ## Start development server (use PORT=8081 to override)
	uv run uvicorn src.backend.main:app --host 0.0.0.0 --port $(PORT)

db-init: ## Initialize database schema and create initial migration (run once)
	uv run aerich init-db

migrate-create: ## Create new database migration
	uv run aerich migrate --name auto

migrate-apply: ## Apply database migrations
	uv run aerich upgrade

migrate-history: ## Show migration history
	uv run aerich history
