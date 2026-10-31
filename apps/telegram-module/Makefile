PORT ?= 8082

.PHONY: help run test lint reload

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

run: ## Start development server with uvicorn reload
	uv run uvicorn telegram_module.main:app --host 0.0.0.0 --port $(PORT)

test: ## Run pytest suite
	uv run pytest

lint: ## Run ruff lint and formatting checks
	uv run ruff check src tests
	uv run ruff format --check src tests

reload: ## Trigger configuration reload via admin endpoint
	curl -X POST http://localhost:$(PORT)/admin/reload
