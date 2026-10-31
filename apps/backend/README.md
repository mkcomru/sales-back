Backend
-------

Сервис для управления конфигурацией компаний, продуктов и транспортных коннекторов
для Sales Agent.

- **Управление компаниями и продуктами**: CRUD для сущностей компании, категорий,
  продуктов, полей и FAQ.
- **Unified Connector Model**: единая модель `Connector` для всех типов транспортов
  (Telegram-боты, Wappi-hub, custom).
- **API Key Management**: управление API-ключами для custom-коннекторов.
- **Event Publishing**: публикация событий в Redis Streams при изменении коннекторов.

## Message Routing (Plan 010)

Backend является центральным роутером для всех потоков сообщений:

### Inbound Flow (Connector → Backend → Sales Agent)
- Транспортные модули отправляют `InboundEnvelope` на `POST /api/v1/messages/inbound`
- Backend валидирует auth (managed: `X-Service-Key` + `X-Connector-Id`, custom: `Bearer sk_xxx`)
- Backend форвардит `InternalInboundRequest` в Sales Agent: `POST /api/v1/internal/messages/inbound`

### Outbound Flow (Sales Agent → Backend → Transport)
- Sales Agent отправляет `OutboundDeliveryRequest` на `POST /api/v1/internal/messages/outbound`
- Backend маршрутизирует ответ на соответствующий транспортный модуль на основе `connector.type`
- Транспортные модули получают `TransportDeliveryPayload` на `/transport/delivery`

### Manager Messages (CRM UI)
- Manager messages обрабатываются полностью в Backend (без участия Sales Agent)
- Backend отключает assistant для треда и маршрутизирует сообщение напрямую в транспорт

## Unified Connector Model (Plan 009)

Все транспортные коннекторы управляются через единую таблицу `connectors`:

### Типы коннекторов
- `telegram` — Telegram Bot API (managed)
- `wappi` — Wappi Hub для WhatsApp/Telegram user-proxy (managed)
- `custom` — внешние интеграции с собственной авторизацией

### Создание коннектора

```bash
POST /transport/connectors
X-Service-Key: <SERVICE__API_KEY>
Content-Type: application/json
```

**Telegram Bot:**
```json
{
  "connector_id": "tg-bot-abc123",
  "company_id": 1,
  "type": "telegram",
  "channel_type": "telegram",
  "display_name": "My Bot",
  "managed": true,
  "config": {
    "bot_token": "123456:ABC...",
    "mode": "polling"
  },
  "debounce_window_seconds": 45
}
```

**Wappi Hub:**
```json
{
  "connector_id": "wappi-main",
  "company_id": 1,
  "type": "wappi",
  "channel_type": "whatsapp",
  "display_name": "WhatsApp Business",
  "managed": true,
  "config": {
    "wappi_token": "WAPPI_TOKEN",
    "wappi_profile_id": "PROFILE_ID"
  }
}
```

**Custom Connector:**
```json
{
  "connector_id": "custom-crm",
  "company_id": 1,
  "type": "custom",
  "channel_type": "custom",
  "display_name": "CRM Integration",
  "managed": false,
  "config": {}
}
```

### Получение конфигурации

```bash
# Все коннекторы
GET /transport/connectors

# Фильтр по типу и статусу
GET /transport/connectors?type=telegram&enabled=true
```

### API Keys для Custom Connectors

```bash
# Создать API key
POST /transport/connectors/{id}/api-keys

# Список ключей
GET /transport/connectors/{id}/api-keys

# Удалить ключ
DELETE /transport/connectors/{id}/api-keys/{key_id}
```

## Конфигурация

Общие переменные (`SERVICE__API_KEY`, `DATABASE__URL`, `BACKEND__URL` и т.д.)
задаются в корневом `.env.shared`.

Для работы HTTP API backend необходим общий сервисный ключ:
- `SERVICE__API_KEY` в `.env.shared` — используется в заголовке `X-Service-Key`

## Event Publishing

При изменении коннекторов backend публикует событие `transport.connectors.changed`
в Redis Streams (`backend.events`). Транспортные модули и Sales Agent подписаны
на эти события и автоматически обновляют конфигурацию.

## Разработка

```bash
# From repository root - install all workspace dependencies
uv sync

# Запуск dev-сервера (из директории модуля)
cd apps/backend
uv run uvicorn src.backend.main:app --reload
# или использовать make
make dev

# Тесты (из директории модуля)
uv run pytest
```

Healthcheck: `GET /health` → 200 OK.

## База данных и миграции

- ORM: **Tortoise**; миграции: **Aerich**.

```bash
cd apps/backend

# Инициализация (один раз)
uv run aerich init-db

# После изменений моделей
uv run aerich migrate --name <change_name>
uv run aerich upgrade
```
