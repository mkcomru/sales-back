# Руководство по тестированию

Покрытие тестами различается между модулями монорепозитория. Sales Agent и Backend поставляются с тестами на pytest. В этом документе описаны общие ожидания и особенности для отдельных модулей.

## Общие рекомендации для репозитория
- По возможности используйте автоматические тесты; для Python-модулей предпочтительнее pytest.
- Фикстуры и вспомогательные функции держите рядом с тестируемым модулем; избегайте кросс-модульных импортов, чтобы не создавать циклические зависимости.

## `apps/backend`
- Обширный набор тестов для всех модулей backend.
- Тесты запускаются через pytest:
  - `cd apps/backend && uv run pytest` или `uv run --package backend pytest` из корня
- Покрывает: auth, billing, chat, companies, categories, products, prompts, tools, transport, sync, simulator, users, forms, messages.

## `apps/sales-agent`
- Тесты запускаются через pytest:
  - `cd apps/sales-agent && uv run pytest` или `uv run --package sales-bot pytest` из корня
- Покрывает: agents, API endpoints, connectors, core functionality, handlers, services.

## `apps/telegram-module`
- Тесты запускаются через pytest:
  - `cd apps/telegram-module && uv run pytest` или `uv run --package telegram-module pytest` из корня
- Покрывает: handlers, manager, transport service, API routes.

## `apps/wappi-module`
- Тесты запускаются через pytest:
  - `cd apps/wappi-module && uv run pytest` или `uv run --package wappi-module pytest` из корня
- Покрывает: connectors, services, transport, sync functionality.

## `libs/common`
- Общие утилиты должны сопровождаться точечными юнит-тестами, если поведение становится нетривиальным (например, загрузчики конфигов, врапперы для логирования).
