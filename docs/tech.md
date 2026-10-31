# Технологический стек

Монорепозиторий содержит несколько Python‑сервисов: ядро AI Sales Agent, CRM‑коннекторы и транспортные модули (например, Telegram). Общие тулзы обеспечивают воспроизводимость разработки между сервисами.

## Языки и рантаймы
- **Python 3.12** — основной язык для всех модулей (`apps/backend`, `apps/sales-agent`, `apps/telegram-module`, `apps/wappi-module`) и пакетов в `libs/`.

## Python-стек приложений
- **FastAPI** (`uvicorn` для локальной разработки) — HTTP-слой для вебхуков и транспортных ручек.
- **Кастомный LLMClient** — унифицированный клиент для OpenAI-compatible API (Chat Completions + Responses API для GPT-5/o1/o3).
- **Tool Loop** — собственная реализация цикла вызова тулзов с `ToolSpec` и `ToolRegistry`.
- **OpenAI**‑клиент — LLM‑провайдер выбирается через конфиг (OpenAI, OpenRouter, etc.).
- **aiogram 3** — асинхронная работа с Telegram Bot API в транспортных модулях.
- **Tortoise ORM** + **Aerich** — асинхронное хранение и миграции (SQLite для тестов, PostgreSQL в продакшене с изоляцией по схемам).
- **Structlog** — структурированное логирование, общее для всех модулей через `libs/common`.
- **HTTPX** — исходящие HTTP‑запросы (handoff‑прокси, вызовы к Backend для маршрутизации, Telegram Bot API).

### Архитектура базы данных
- **PostgreSQL**, одна схема `backend`
- Backend — единственный модуль с БД (Aerich, схема `backend`)
- sales-agent и транспорты — stateless, БД не используют
- Конфигурация: `DATABASE__URL` в `.env.shared`
- Первый запуск: `cd apps/backend && uv run aerich init-db`

#### Важно: Aerich и схемы PostgreSQL

**Известное ограничение:** Aerich не добавляет имени схемы при генерации миграций, несмотря на `Meta.schema` в моделях. Требуется ручная правка миграций:

1. **Модели используют `Meta.schema`** — Tortoise ORM правильно подставляет схему в запросах во время работы (`schema.table_name`)
2. **Первая миграция (`aerich init-db`)** — Aerich автоматически создаёт `CREATE SCHEMA` и `SET search_path`
3. **Дальнейшие миграции** — Aerich генерирует SQL **без** схемы

**Что делать:** После `aerich migrate` вручную проставить схему `backend` в имена таблиц:

```python
# ❌ Сгенерировано Aerich
CREATE TABLE "users" (...)

# ✅ Ручная правка
CREATE TABLE "backend"."users" (...)
```

### Вспомогательные библиотеки
- Логика дебаунса для батчинга быстрых сообщений — `apps/sales-agent/src/sales_agent/services/debounce.py`.
- Кастомная телеметрия интегрируется с Langfuse при наличии ключей.

## Backend (`apps/backend`)
- **FastAPI**‑сервис, центральный роутер для всех потоков сообщений и API для управления конфигурацией.
- **Tortoise ORM + Aerich** — хранение данных в схеме `backend` (компании, продукты, коннекторы, чаты, биллинг).
- **HTTPX** — исходящие запросы к Sales Agent и транспортным модулям для маршрутизации сообщений.
- **Redis Streams** — публикация событий (`transport.connectors.changed`) для event-driven обновления конфигурации.
- **Structlog** — структурированное логирование через `libs/common`.
- **Pytest** — тесты для всех модулей backend.
- **WebSocket** — поддержка real-time коммуникации через `apps/backend/src/backend/modules/chat/websocket.py`.

## Sales Agent (`apps/sales-agent`) — stateless LLM-исполнитель
- **Без БД и миграций.** Получает контекст от Backend, возвращает ответ. Почти stateless (кроме debounce).
- **FastAPI** (`uvicorn`) — HTTP‑слой для internal endpoints.
- **Кастомный LLMClient** — унифицированный клиент для Chat Completions и Responses API (GPT-5/o1/o3).
- **Tool Loop** — собственный цикл вызова тулзов с поддержкой трейсинга через `Tracer`.
- **OpenAI**‑клиент — LLM‑провайдер, выбираемый через конфиг (поддержка OpenRouter и других compatible API).
- **Structlog** — общее структурное логирование (`libs/common`).
- **HTTPX** — исходящие запросы к Backend для маршрутизации ответов (`POST /api/v1/internal/messages/outbound`), а также к handoff‑прокси и вспомогательным сервисам.

## Транспортный модуль Telegram (`apps/telegram-module`)
- **FastAPI** — REST‑слой для приёма `TransportDelivery` от Backend, health‑чеки и административные ручки.
- **aiogram 3** — диспетчер Telegram Bot API, поддержка webhooks и long polling.
- **HTTPX** — исходящие запросы к Telegram Bot API, Backend для загрузки конфигурации (`GET /transport/connectors?type=telegram`) и для пересылки входящих сообщений (`POST /api/v1/messages/inbound`).
- **Structlog** — единое структурированное логирование.
- **Pydantic** — валидация `TransportDeliveryPayload`, `InboundEnvelope` и конфигураций ботов.
- **Идемпотентность** — встроенный TTL‑кеш по `correlation_id` предотвращает повторную отправку сообщений при ретраях транспорта.
- **Event-driven** — подписка на `transport.connectors.changed` через Redis Streams для автоматического обновления конфигурации.
- **Pytest** — тесты для handlers, manager и transport service.

## Транспортный модуль Wappi (`apps/wappi-module`)
- **FastAPI** — REST‑слой для приёма `TransportDelivery` от Backend, webhook endpoints для Wappi API, синхронизация истории.
- **HTTPX** — исходящие запросы к Wappi API, Backend для загрузки конфигурации (`GET /transport/connectors?type=wappi`) и для пересылки входящих сообщений (`POST /api/v1/messages/inbound`).
- **Structlog** — единое структурированное логирование.
- **Pydantic** — валидация `TransportDeliveryPayload`, `InboundEnvelope` и конфигураций коннекторов.
- **Идемпотентность** — встроенный TTL‑кеш по `correlation_id` (24 часа).
- **Retry логика** — экспоненциальный backoff при rate limits (429) и server errors (5xx).
- **Event-driven** — подписка на `transport.connectors.changed` через Redis Streams (consumer group: `wappi-module`).
- **Pytest** — тесты для всех компонентов модуля.

## Транспортный контракт

### Inbound (Connector → Backend → Sales Agent)
- Транспортные модули нормализуют входящие сообщения в `InboundEnvelope` и отправляют на Backend: `POST /api/v1/messages/inbound`.
- **Managed connectors**: авторизация через `X-Service-Key` + `X-Connector-Id` headers.
- **Custom connectors**: авторизация через `Authorization: Bearer sk_xxx` (API key валидируется через backend).
- Backend валидирует коннектор, получает `ConnectorContext` и форвардит `InternalInboundRequest` в Sales Agent (`POST /api/v1/internal/messages/inbound`).
- Sales Agent обрабатывает сообщение через LLM pipeline.

### Outbound (Sales Agent → Backend → Transport)
- Sales Agent формирует `OutboundDeliveryRequest` и отправляет в Backend: `POST /api/v1/internal/messages/outbound`.
- Backend маршрутизирует ответ на соответствующий транспортный модуль на основе `connector.type`:
  - `telegram` → `{TRANSPORT__TELEGRAM__URL}/transport/delivery`
  - `wappi` → `{TRANSPORT__WAPPI__URL}/transport/delivery`
- Авторизация между Backend и Transport: `X-Service-Key` + `X-Connector-Id`.
- При успешном приёме транспорт отвечает `202 Accepted`; при дубликате — `409 Conflict`.
- Повторные попытки: максимум 3 ретрая с экспоненциальной задержкой (1s, 5s, 15s).
- Транспортные модули обязаны транслировать `connector_id`, `company_id`, `channel_type`, `conversation_id`, `chat_id` и поля `metadata` без трансформаций.

## Инструменты и упаковка
- **uv** — управление зависимостями через workspace в монорепо, единый `uv.lock` в корне.
- **Docker / Docker Compose** — совместный запуск сервисов для локальной разработки.
- **Pre-commit** — хуки для линтинга/форматирования (ruff, detect-secrets).

### Docker Builds

Все модули используют единый общий Dockerfile (`docker/python-service.Dockerfile`) с параметризацией через build args:

- **Общий Dockerfile** использует multi-stage builds: builder устанавливает зависимости через `uv sync`, runtime копирует только необходимые файлы.
- **Build context** — корень репозитория (`.`) для доступа к workspace структуре.
- **Параметризация** — каждый сервис настраивается через build args в `docker-compose.yml`:
  - `PACKAGE_NAME` — имя пакета для `uv sync`
  - `APP_PATH` — путь к модулю (например, `apps/sales-agent`)
  - `PYTHONPATH_SUFFIX` — суффикс для PYTHONPATH (пустая строка или `/src`)
  - `UVICORN_MODULE_PATH` — путь модуля для команды uvicorn
- **Migrations** копируются условно (только если директория существует).
- **Docker Compose** использует общий Dockerfile с соответствующими build args для каждого сервиса.

Сборка выполняется через Docker Compose:
```bash
# Сборка всех сервисов
docker compose build

# Сборка конкретного сервиса
docker compose build sales-agent

# Сборка с пересборкой без кеша
docker compose build --no-cache sales-agent
```

## Конвенции по конфигурации
- Общие переменные окружения хранятся в `.env.shared` в корне репозитория (LLM, база, Redis, RAG/Qdrant, `BACKEND__URL`, `SERVICE__API_KEY` и т.д.).
- Модульные переменные окружения в `apps/<module>/.env` содержат только специфичные для модуля настройки.
- Полный справочник переменных окружения: `docs/configuration.md`

## Зависимости

### Общие зависимости (`libs/common`)

- `fastapi` — веб-фреймворк
- `pydantic` / `pydantic-settings` — валидация и конфигурация
- `httpx` — асинхронный HTTP клиент
- `structlog` — структурированное логирование
- `tortoise-orm` — ORM для PostgreSQL
- `asyncpg` — драйвер PostgreSQL
- `aerich` — миграции для Tortoise ORM
- `redis` — клиент Redis (для eventing)

### Backend (`apps/backend`)

- `python-jose[cryptography]` — JWT токены
- `passlib[bcrypt]` — хеширование паролей
- `bcrypt` — криптография для паролей
- `email-validator` — валидация email

### Sales Agent (`apps/sales-agent`)

- `langfuse` — трейсинг LLM вызовов
- `qdrant-client` — векторная база данных
- `cohere` — embedding API
- `pymupdf` — обработка PDF
- `python-docx` — обработка Word документов
- `beautifulsoup4` — парсинг HTML
- `markdownify` — конвертация HTML в Markdown
- `readability-lxml` — извлечение текста
- `aiohttp` — HTTP клиент для веб-скрапинга
- `yandexcloud` — Yandex Cloud интеграция
- `jinja2` — шаблонизация промптов
- `click` — CLI утилиты

### Модули транспорта

- `telegram-module`, `wappi-module` — минимальные зависимости, используют `common` для базовой функциональности

### Управление зависимостями

- **uv** — менеджер пакетов и workspace
- Все модули объявлены в корневом `pyproject.toml` как workspace members
- Зависимости синхронизируются через `uv sync`
- Общие зависимости в `libs/common/pyproject.toml`
- Модуль-специфичные зависимости в `apps/<module>/pyproject.toml`
- Общие модели настроек хранятся в `libs/common/src/common/config.py` — LLM, база, Redis, параметры дебаунса и транспортные блоки (`ConnectorSettings.transport`, `BackendModuleSettings.transport`).
- Коннекторы загружаются из Backend через `GET /transport/connectors` (ConnectorSync в sales-agent, транспорты получают при старте и по event).
- Единый сервисный ключ (`SERVICE__API_KEY`) используется для авторизации между сервисами (Sales Agent ↔ Backend, транспорты ↔ Backend).
- **Обязательные для транспортов:** `BACKEND__URL` и `SERVICE__API_KEY` (в `.env.shared`).
- Промпты берутся из `.md`‑файлов в `src/sales_agent/agents/prompts/`.

## Обозреваемость (Observability)

### Логирование

- **Structlog** — структурированное логирование через `common.setup_logging`
- **Формат:** JSON в production, human-readable в development
- **Структура:** Все логи содержат данные среды, версию и фиче-флаги
- **События:** Используются структурированные ключи (`event.received`, `connector.reload.completed`, `transport.delivery.delivered`)

### Health Checks

Все сервисы предоставляют health check endpoints:

- Backend: `GET /health` → `200 OK`
- Sales Agent: `GET /healthz` → `{"ok": true, "service": "sales-agent"}`
- Telegram Module: `GET /healthz` → `{"status": "ok"}`
- Wappi Module: `GET /healthz` → `{"status": "ok"}`

Docker Compose использует health checks для управления зависимостями (`condition: service_healthy`).

### Телеметрия

- **Langfuse** — опциональная интеграция для трейсинга LLM вызовов
- Активируется через `LANGFUSE__ENABLED=true`
- Обрамляет вызовы LLM через `AsyncOpenAI` wrapper
- Трейсит тулзы через кастомный `Tracer`
- Настраивается через `LANGFUSE__PUBLIC_KEY`, `LANGFUSE__SECRET_KEY`, `LANGFUSE__HOST`

### Мониторинг

Ключевые события для мониторинга:

- `event.received` — получение события из Redis Streams
- `connector.reload.completed` — обновление конфигурации коннекторов
- `transport.delivery.delivered` — успешная доставка сообщения
- `transport.delivery.failed` — ошибка доставки
- `sales_agent.pipeline.completed` — завершение LLM pipeline
- `billing.balance.updated` — обновление баланса компании

## Обработка ошибок

### Иерархия исключений

**Backend исключения** (`apps/backend/src/backend/modules/*/exceptions.py`):

- `CompanyNotFoundError` → `404 Not Found`
- `ConnectorNotFoundError` → `404 Not Found`
- `ProductNotFoundError` → `404 Not Found`
- `CategoryNotFoundError` → `404 Not Found`
- `PromptNotFoundError` → `404 Not Found`
- `ToolNotFoundError` → `404 Not Found`
- `FieldNotFoundError` → `404 Not Found`
- `FieldOptionNotFoundError` → `404 Not Found`
- `FAQNotFoundError` → `404 Not Found`
- `UserAlreadyExistsError` → `409 Conflict`
- `SimulatorSessionNotFoundError` → `404 Not Found`

**Сервисные исключения:**

- `TransportClientError` — ошибка доставки в транспортный модуль
- `SalesAgentClientError` — ошибка вызова Sales Agent
- `SyncCommanderError` — ошибка управления синхронизацией

### HTTP Error Responses

Все ошибки возвращают стандартные HTTP статус коды:

- `400 Bad Request` — невалидные данные запроса
- `401 Unauthorized` — отсутствует или неверная аутентификация
- `403 Forbidden` — недостаточно прав доступа
- `404 Not Found` — ресурс не найден
- `409 Conflict` — конфликт состояния (дубликат, идемпотентность)
- `422 Unprocessable Entity` — ошибка валидации Pydantic
- `500 Internal Server Error` — внутренняя ошибка сервера
- `503 Service Unavailable` — сервис недоступен

Формат ответа:

```json
{
  "detail": "Error message"
}
```

Для валидационных ошибок:

```json
{
  "detail": [
    {
      "loc": ["body", "field_name"],
      "msg": "Error message",
      "type": "error_type"
    }
  ]
}
```

### Retry Patterns

**Transport Delivery:**

- Максимум 3 попытки с экспоненциальным backoff (1s, 5s, 15s)
- Retry при: `429 Too Many Requests`, `5xx Server Error`, network errors
- Не retry при: `400 Bad Request`, `401 Unauthorized`, `404 Not Found`

**HTTP Clients:**

- Используют `httpx.AsyncClient` с таймаутами
- Таймауты настраиваются через `REQUEST_TIMEOUT_S` или `TELEGRAM_MODULE_REQUEST_TIMEOUT_S`

### Логирование ошибок

- Используется `logger.exception("message")` для захвата stack trace
- Структурированные ключи: `error`, `error_type`, `status_code`
- Контекстные поля: `connector_id`, `company_id`, `thread_id`, `correlation_id`

### Exception Handlers

Backend регистрирует exception handlers в `apps/backend/src/backend/modules/core/exceptions.py`:

- Кастомные исключения маппятся на HTTP статус коды
- Обработчики логируют ошибки и возвращают стандартизированные ответы

## Цели деплоя
- **Backend** — контейнеризированный FastAPI‑сервис (CRM‑ядро); центральный роутер и API для управления платформой.
- **Sales Agent** — stateless LLM‑исполнитель; требует доступа к OpenAI и Backend API; без БД, без миграций.
- **Telegram Module** — контейнеризированный сервис, которому нужен доступ к Telegram Bot API и Backend для загрузки конфигов.
- **Wappi Module** — контейнеризированный сервис, которому нужен доступ к Wappi API и Backend для загрузки конфигов.

## Локальный разработческий цикл
- Установить зависимости: `uv sync` в корне репозитория (установит все модули workspace).
- Инициализация БД (первый запуск): `cd apps/backend && uv run aerich init-db`. Sales-agent и транспорты БД не используют.
- Запуск: `just dev all` или `just dev backend,sales-agent` из корня репозитория.
- Для Wappi-модуля: `uv run uvicorn wappi_module.main:app --reload` из `apps/wappi-module` (сервисные URL задаются через `.env.shared`).
- Миграции: `uv run aerich migrate --name <имя>` — генерация; `uv run aerich upgrade` — применение (запускать из папки модуля).
- Общие библиотеки устанавливаются автоматически через workspace при `uv sync`.
