.PHONY: run test lint reload

run:
	uv run uvicorn wazzup_module.main:app --reload --host 0.0.0.0 --port 8004

test:
	uv run pytest

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

reload:
	curl -s -X POST http://localhost:8004/admin/reload | python -m json.tool
