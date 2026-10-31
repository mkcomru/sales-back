ENV ?= dev
MODULE ?= sales-agent

SUPPORTED_MODULES := sales-agent bitrix-module backend telegram-module wappi-module
MODULE_DIR := $(if $(filter $(MODULE),$(SUPPORTED_MODULES)),$(addprefix apps/,$(MODULE)),)

define run_module_target
	@if [ -z "$(MODULE_DIR)" ]; then \
		echo "Unknown module '$(MODULE)'. Supported: $(SUPPORTED_MODULES)"; \
		exit 1; \
	fi
	APP__ENVIRONMENT=$(ENV) ENV=$(ENV) $(MAKE) -C $(MODULE_DIR) $(1)
endef

M.PHONY: help bootstrap bootstrap-env install
help: ## Show this help message
	@echo "Sales Bot Monorepo - Root Makefile"
	@echo ""
	@echo "Current configuration:"
	@echo "  ENV=$(ENV)"
	@echo "  MODULE=$(MODULE)"
	@echo ""
	@echo "Supported modules: $(SUPPORTED_MODULES)"
	@echo ""
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Examples:"
	@echo "  make test                    # Run tests in all apps"
	@echo "  make MODULE=backend test     # Run tests in backend only"
	@echo "  make MODULE=backend db-init  # Initialize database for backend"

bootstrap: bootstrap-env ## Bootstrap project environment (create .env.shared from template)

bootstrap-env: ## Create .env.shared from .env.shared.example template
	@if [ -f .env.shared ]; then \
		echo ".env.shared already exists"; \
	elif [ -f .env.shared.example ]; then \
		cp .env.shared.example .env.shared; \
		echo "Created .env.shared from template"; \
	else \
		echo "Missing .env.shared.example template"; \
		exit 1; \
	fi

install: ## Install dependencies and pre-commit hooks (set MODULE=name to target one)
	@if [ -n "$(MODULE)" ] && [ -z "$(MODULE_DIR)" ]; then \
		echo "Unknown module '$(MODULE)'. Supported: $(SUPPORTED_MODULES)"; \
		exit 1; \
	fi
	uv sync
	@if [ -n "$(MODULE_DIR)" ]; then \
		echo "Installing pre-commit hooks in $(MODULE_DIR)..."; \
		(cd $(MODULE_DIR) && uv run pre-commit install); \
	else \
		echo "Installing pre-commit hooks in repo root..."; \
		uv run pre-commit install; \
		for module in $(SUPPORTED_MODULES); do \
			echo "Installing pre-commit hooks in apps/$$module..."; \
			(cd apps/$$module && uv run pre-commit install) || exit 1; \
		done; \
	fi

.PHONY: test db-init migrate-create migrate-apply migrate-history

test: ## Run tests in all apps
	@echo "Running tests in all apps..."
	@failed_modules=""; \
	failed=0; \
	for module in $(SUPPORTED_MODULES); do \
		echo ""; \
		echo "========================================="; \
		echo "Running tests in $$module..."; \
		echo "========================================="; \
		if ! APP__ENVIRONMENT=$(ENV) ENV=$(ENV) $(MAKE) -C apps/$$module test; then \
			failed=$$((failed + 1)); \
			failed_modules="$$failed_modules $$module"; \
		fi; \
	done; \
	echo ""; \
	if [ $$failed -eq 0 ]; then \
		echo "✓ All tests passed!"; \
	else \
		echo "✗ Tests failed in $$failed module(s):"; \
		for module in $$failed_modules; do \
			echo "  - $$module"; \
		done; \
		echo ""; \
		echo "To rerun tests for failed modules, use:"; \
		for module in $$failed_modules; do \
			echo "  make -C apps/$$module test"; \
		done; \
		exit 1; \
	fi

db-init: ## Initialize database schema and create initial migration (use MODULE=name to target specific module)
	$(call run_module_target,db-init)

migrate-create: ## Create new database migration (use MODULE=name to target specific module)
	$(call run_module_target,migrate-create)

migrate-apply: ## Apply database migrations (use MODULE=name to target specific module)
	$(call run_module_target,migrate-apply)

migrate-history: ## Show migration history (use MODULE=name to target specific module)
	$(call run_module_target,migrate-history)
