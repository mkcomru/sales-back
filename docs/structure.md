# Структура репозитория

## Общее устройство монорепозитория

Репозиторий — это монорепозиторий на основе uv workspace, объединяющий клиентские сервисы и общие библиотеки для автоматизации продаж. Основная структура на верхнем уровне выглядит следующим образом:
```
├── apps/
│   ├── backend/             # CRM: компании, заказы, биллинг, маршрутизация сообщений
│   ├── sales-agent/         # Stateless LLM-исполнитель (фича, без БД и миграций)
│   ├── telegram-module/     # Транспортный модуль для Telegram Bot API
│   └── wappi-module/        # Транспортный модуль для Wappi API (WhatsApp/Telegram)
├── libs/
│   └── common/              # Общий Python‑пакет с конфигами и логированием
├── docs/                    # Каноничная документация по всем модулям
├── plans/                   # Утвержденные планы для комплексных задач агентов
├── docker-compose.yml       # Compose‑стэк для одновременного запуска сервисов
├── README.md                # Гайд по запуску всего монорепозитория
└── sales-bot.code-workspace # Workspace‑файл для VS Code
```

Каждый модуль содержит свой манифест зависимостей (`pyproject.toml` для Python). Общий код находится в каталоге `libs/` и импортируется через uv workspace (`common = { workspace = true }` в корневом `pyproject.toml`).

## Описание модулей

### `apps/backend`
- **CRM‑ядро платформы.** Центральный роутер и API для управления конфигурацией, заказами, компаниями.
- Управляет компаниями, продуктами, категориями, промптами, инструментами и транспортными коннекторами через единую модель `Connector`.
- Обрабатывает все потоки сообщений: валидирует входящие от транспортов, форвардит в Sales Agent, маршрутизирует исходящие ответы.
- Управляет чатами и тредами, биллингом, синхронизацией истории сообщений.
- Хранит состояние в схеме PostgreSQL `backend` с независимыми миграциями через Aerich.
- Публикует события в Redis Streams (`transport.connectors.changed`) для event-driven обновления конфигурации.
- Предоставляет REST API по `/api/v1/*` и внутренние endpoints по `/api/v1/internal/*`.
- Подробности в `apps/backend/README.md`.

### `apps/sales-agent`
- **Stateless LLM‑исполнитель** — изолированный FastAPI‑сервис, не хранит состояние (кроме debounce), не имеет миграций и своей схемы БД.
- Принимает внутренние запросы от Backend (`POST /api/v1/internal/messages/inbound`), получает весь контекст в envelope, формирует ответ и возвращает его в Backend (`POST /api/v1/internal/messages/outbound`).
- Оркестрация LLM‑тулов через OpenAI Agents SDK, промпты хранятся в Markdown‑файлах под `src/sales_agent/agents/prompts/`.
- Предоставляет поиск в базе знаний, уведомления об эскалации, телеметрию — всё через write-only вызовы Backend API.

### `apps/telegram-module`
- FastAPI‑сервис, агрегирующий Telegram‑ботов разных компаний и выступающий транспортным слоем.
- Принимает `TransportDelivery` от Backend (`POST /transport/delivery`), проверяет единый сервисный ключ (`SERVICE__API_KEY`) и идентификатор коннектора, доставляет сообщения в Telegram Bot API с ретраями и идемпотентностью.
- Получает конфигурацию ботов из unified backend API через `GET /transport/connectors?type=telegram&enabled=true`.
- Форвардит входящие обновления в Backend через единый endpoint `POST /api/v1/messages/inbound` с нормализованным `InboundEnvelope`.
- Использует Router-паттерн aiogram 3 для обработки обновлений с поддержкой webhook и polling режимов.
- Подписан на `transport.connectors.changed` события через Redis Streams для автоматического обновления конфигурации.

### `apps/wappi-module`
- FastAPI‑сервис для интеграции с Wappi API (WhatsApp/Telegram user-proxy).
- Аналогичен telegram-module по архитектуре: получает конфигурацию из Backend, форвардит входящие в Backend, принимает исходящие от Backend.
- Обрабатывает webhook-и от Wappi API и нормализует их в `InboundEnvelope`.
- Поддерживает синхронизацию истории сообщений через специальные endpoints.
- Доставляет сообщения в Wappi API с retry логикой и обработкой rate limits.
- Подписан на `transport.connectors.changed` события через Redis Streams.
- Подробности в `apps/wappi-module/README.md` и `apps/wappi-module/docs/`.

### `libs/common`
- Python‑пакет, централизующий конфигурационные модели, настройку логирования и IO‑схемы.
- Используется в приложениях через uv workspace (`common = { workspace = true }`).
- Новые общие библиотеки должны следовать этому же шаблону.

## Приоритет документации

1. Документация на уровне модуля (`apps/<module>/docs/`) — **максимальный приоритет при наличии**.
2. Основные документационные файлы в `docs/` — канон для всего монорепозитория.
3. Корневые README и инлайн‑анкоры `AICODE-*`, обнаруживаемые через поиск.

Агенты всегда должны читать как корневую документацию, так и docs соответствующего модуля, если они существуют внутри целевого workspace, перед изменениями кода.

## Конфигурация и секреты

- Общие переменные окружения хранятся в `.env.shared` в корне репозитория (LLM, база, Redis, RAG/Qdrant, сервисные URL, единый сервисный ключ).
- Модульные файлы окружения (`apps/sales-agent/.env`, `apps/backend/.env`, `apps/telegram-module/.env`, `apps/wappi-module/.env`) содержат только специфичные для модуля настройки.
- Общие дефолты и структурированные настройки хранятся в `libs/common/src/common/config.py`.
- **Обязательные переменные для транспортов:** `BACKEND__URL` и `SERVICE__API_KEY` (в `.env.shared`).
- Docker Compose предполагает наличие `.env.shared` и модульных `.env` файлов до запуска сервисов.

## Архитектура базы данных

- **PostgreSQL** — единая БД со схемой `backend`
- **Backend** — единственный модуль с миграциями (Aerich, схема `backend`)
- **Sales-agent**, **telegram-module**, **wappi-module** — не используют БД напрямую (stateless / конфиг через Backend API)

## Зависимости между сервисами

```
┌─────────────┐
│   Redis     │
└──────┬──────┘
       │
       ├──────────────┐
       │              │
┌──────▼──────┐  ┌────▼─────┐
│   Backend   │  │PostgreSQL│
└──────┬──────┘  └──────────┘
       │
       ├──────────────┬──────────────┐
       │              │              │
┌──────▼──────┐  ┌────▼──────┐  ┌────▼──────┐
│Sales Agent  │  │Telegram   │  │  Wappi    │
└─────────────┘  │  Module   │  │  Module   │
                 └───────────┘  └───────────┘
```

**Зависимости:**

- **Backend** → PostgreSQL (`backend` schema), Redis (если eventing включен)
- **Sales Agent** → Backend (write-only API), Redis (если eventing) — stateless, без БД
- **Telegram Module** → Backend (конфигурация, маршрутизация), Redis (если eventing включен)
- **Wappi Module** → Backend (конфигурация, маршрутизация), Redis (если eventing включен)

**Порядок запуска:**

1. Redis (если eventing используется)
2. Backend migrations → Backend
3. Sales-agent, Transport modules (после Backend готов)

## Взаимодействие между модулями

### Unified Connector Model

Все транспортные коннекторы (Telegram-боты, Wappi, custom) управляются через единую модель `Connector` в backend:

- **Backend** хранит коннекторы в таблице `connectors` с полями `type` (telegram/wappi/custom), `config` (JSONB), `managed` (bool).
- **Транспортные модули** (telegram-module, wappi-module) получают конфигурацию через `GET /transport/connectors?type={type}&enabled=true`.
- **Backend** принимает входящие сообщения (`POST /api/v1/messages/inbound`), валидирует auth и роутит в Sales Agent (`POST /api/v1/internal/messages/inbound`) или обрабатывает сам.

### Dual-path Authentication

- **Managed connectors** (telegram, wappi): `X-Service-Key` + `X-Connector-Id` headers
- **Custom connectors**: `Authorization: Bearer sk_xxx` (API key validation через backend)

### Поток сообщений (Unified Backend Router)

**Стандартный поток (telegram-module, wappi-module):**
1. Транспортный модуль получает входящее сообщение (Telegram update, Wappi webhook)
2. Нормализует в `InboundEnvelope` и отправляет на Backend: `POST /api/v1/messages/inbound`
3. Backend валидирует auth, получает `ConnectorContext`, сохраняет сообщение в БД и форвардит `InternalInboundRequest` в Sales Agent: `POST /api/v1/internal/messages/inbound`
4. Sales Agent обрабатывает сообщение через LLM pipeline
5. Sales Agent отправляет ответ в Backend: `POST /api/v1/internal/messages/outbound`
6. Backend сохраняет ответ в БД, проверяет `assistant_active` и маршрутизирует на соответствующий транспортный модуль: `POST /transport/delivery`

### Event-driven Updates

При изменении коннекторов backend публикует `transport.connectors.changed` в Redis Streams. Транспортные модули и Sales Agent подписаны (eventing) и обновляют конфигурацию без перезапуска.

- Общие тулзы для телеметрии и конфинга должны выноситься в `libs/common`, чтобы избежать дублирования по приложениям.
- При добавлении нового приложения или библиотеки обновляйте этот документ и корневой README для наглядности структуры.
