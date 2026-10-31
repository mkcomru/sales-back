# Wappi Module

**Микросервис-адаптер для интеграции Sales Agent с Wappi API**

---

## Что это такое?

**wappi-module** — это транспортный модуль, обеспечивающий двунаправленную коммуникацию между **Sales Agent** и **Wappi API** для обработки сообщений через Telegram, WhatsApp и другие мессенджеры, поддерживаемые Wappi.

### Ключевые возможности

✅ **Двунаправленная коммуникация:**
- Входящие: `Wappi → wappi-module → Backend → Sales Agent`
- Исходящие: `Sales Agent → Backend → wappi-module → Wappi API`

✅ **Централизованное управление:**
- Загрузка конфигурации из backend
- Hot-reload без рестарта (каждые 60 сек)
- Поддержка множества компаний

✅ **Гарантии доставки:**
- Идемпотентность по `correlation_id` (TTL 24 часа)
- Retry логика с экспоненциальным backoff (до 3 попыток)
- Обработка rate limits (429) от Wappi API

✅ **Production-ready:**
- Structured logging (structlog, JSON)
- Health checks (`/healthz`)
- Admin endpoints (`/admin/reload`)
- Async/await everywhere

---

## Быстрый старт

### 1. Установка зависимостей

```bash
# Из корня репозитория
cd d:\aigency\sales-main
uv sync
```

### 2. Настройка переменных окружения

```bash
# Создайте .env.shared в корне репозитория
cat > .env.shared << EOF
BACKEND__URL=http://localhost:8001
SERVICE__API_KEY=$(openssl rand -hex 32)
APP__ENVIRONMENT=dev
APP__DEBUG=true
EOF
```

### 3. Запуск сервисов

```bash
# Terminal 1: Backend
cd apps/backend
uv run uvicorn backend.main:app --reload --port 8001

# Terminal 2: Sales Agent
cd apps/sales-agent
uv run uvicorn src.sales_agent.main:app --reload --port 8000

# Terminal 3: Wappi Module
cd apps/wappi-module
uv run uvicorn wappi_module.main:app --reload --port 8002
```

### 4. Проверка работоспособности

```bash
# Health check
curl http://localhost:8002/healthz
# {"status": "ok"}

# Проверка логов
# Должно быть: connector.reload.completed count=N
```

---

## Архитектура (Plan 010: Backend Router)

**Wappi-module адаптирован под новую архитектуру Backend Router Ingress**, где Backend является центральным роутером для всех сообщений.

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐         ┌─────────────┐
│   Wappi     │         │    wappi-    │         │   Backend   │         │    Sales   │
│    API      │◄───────►│   module     │◄───────►│  (Router)   │◄───────►│    Agent    │
└─────────────┘         └──────────────┘         └─────────────┘         └─────────────┘
                               │                        │
                               ▼                        ▼
                        Unified Connector API    Event Publishing
                    GET /transport/connectors    (Redis Streams)
                     ?type=wappi&enabled=true
```

### Входящие сообщения (Inbound Flow)

1. **Wappi API** отправляет webhook на `POST /wappi/{connector_id}/webhook`
2. **wappi-module** нормализует в `InboundEnvelope` формат
   - Сохраняет специальные флаги: `_manager_outgoing`, `_sync_mode`, `fromMe`
3. **wappi-module** отправляет в Backend: `POST /api/v1/messages/inbound`
   - Авторизация: `X-Service-Key` + `X-Connector-Id` headers
4. **Backend** валидирует auth, получает `ConnectorContext`
5. **Backend** форвардит в Sales Agent: `POST /api/v1/internal/messages/inbound`
6. **Sales Agent** обрабатывает через LLM pipeline

### Исходящие сообщения (Outbound Flow)

1. **Sales Agent** отправляет в Backend: `POST /api/v1/internal/messages/outbound`
2. **Backend** маршрутизирует на модуль: `POST /transport/delivery`
   - Добавляет `X-Service-Key` + `X-Connector-Id` headers
3. **wappi-module** доставляет в Wappi API с retry логикой
4. **Wappi API** отправляет сообщение пользователю

### Event-driven Updates

При изменении коннекторов в Backend:
- Backend публикует `transport.connectors.changed` event в Redis Streams
- wappi-module подписан на этот event (consumer group: `wappi-module`)
- При получении event → автоматический reload конфигурации

### Unified Connector API

Backend предоставляет единый endpoint для всех транспортных модулей:

```bash
GET /transport/connectors?type=wappi&enabled=true
Authorization: X-Service-Key: {shared_key}
```

Response:
```json
{
  "connectors": [
    {
      "connector_id": "wappi-tg-123",
      "type": "wappi",
      "channel_type": "telegram",
      "company_id": 42,
      "config": {
        "wappi_token": "...",
        "wappi_profile_id": "...",
        "metadata": {...}
      },
      "debounce_window_seconds": 45,
      "enabled": true
    }
  ]
}
```

### Компоненты

| Компонент | Ответственность |
|-----------|----------------|
| **API Layer** | FastAPI endpoints (transport, webhook, admin, health) |
| **ConnectorManager** | Загрузка и hot-reload конфигурации через unified API |
| **TransportDeliveryService** | Валидация auth, идемпотентность, retry логика |
| **WappiApiClient** | HTTP клиент для Wappi API |
| **BackendInboundClient** | Нормализация в `InboundEnvelope`, форвардинг в Backend |
| **EventingLifespan** | Подписка на Redis Streams для event-driven reload |

### Специальные возможности Wappi

**Manager Outgoing Detection**: Wappi webhook содержит флаг `from_where` для определения источника сообщения:
- `from_where="api"` → сообщение от assistant (пропускаем, уже в БД)
- `from_where!="api"` → сообщение от manager через веб/устройство (флаг `_manager_outgoing=true`)

**Historical Sync**: Endpoints для синхронизации истории сообщений:
- `POST /wappi/sync/{connector_id}` — синхронизация всех чатов
- `GET /wappi/{connector_id}/chat/{chat_id}/history` — история конкретного чата
- Флаг `_sync_mode=true` → Sales Agent проверяет БД перед созданием

**Extra Metadata**: `InboundEnvelope.extra` сохраняет:
- `_manager_outgoing` — сообщение от manager (не assistant)
- `_sync_mode` — историческое сообщение (проверить БД)
- `fromMe` — оригинальный флаг Wappi

---

## Endpoints

| Endpoint | Метод | Назначение |
|----------|-------|-----------|
| `/transport/delivery` | POST | Прием сообщений от Backend для отправки в Wappi API |
| `/wappi/{connector_id}/webhook` | POST | Прием webhook-ов от Wappi API |
| `/wappi/sync/{connector_id}` | POST | Синхронизация всей истории сообщений из Wappi |
| `/wappi/{connector_id}/chat/{chat_id}/history` | GET | Получение истории конкретного чата |
| `/admin/reload` | POST | Принудительная перезагрузка конфигурации |
| `/healthz` | GET | Health check для мониторинга |
| `/docs` | GET | Swagger UI (интерактивная документация) |

### Authentication

**Transport Delivery** (`/transport/delivery`):
- Требует headers: `X-Service-Key` + `X-Connector-Id`
- Backend добавляет эти headers автоматически

**Webhook** (`/wappi/{connector_id}/webhook`):
- Public endpoint (без auth)
- Wappi API не поддерживает подписи webhook-ов

См. подробности в [docs/API.md](./docs/API.md)

---

## Конфигурация

### Обязательные переменные

```bash
BACKEND__URL=http://localhost:8001          # URL backend сервиса (unified connector API)
SERVICE__API_KEY=your-secret-key            # Сервисный ключ (между сервисами)
REDIS__URL=redis://localhost:6379           # Redis для event-driven reload
```

### Опциональные переменные

```bash
APP__ENVIRONMENT=dev                        # dev | staging | prod
APP__DEBUG=true                             # Подробные логи
CONFIG_REFRESH_INTERVAL_S=60                # Интервал обновления конфигов (фоновый)
REQUEST_TIMEOUT_S=10.0                      # Таймаут HTTP запросов
MAX_DELIVERY_ATTEMPTS=3                     # Максимум попыток доставки

# Eventing (event-driven reload)
EVENTING__ENABLED=true                      # Включить Redis Streams подписку
EVENTING__STREAM__NAME=backend.events       # Имя stream в Redis
EVENTING__STREAM__GROUP=wappi-module        # Consumer group (уникально для модуля!)
EVENTING__STREAM__CONSUMER_NAME=worker-1    # Consumer name (default: hostname)
```

### CORS

```bash
CORS__ORIGINS=["http://localhost:3000"]     # Разрешенные origins
CORS__ALLOW_CREDENTIALS=true
CORS__ALLOW_METHODS=["*"]
CORS__ALLOW_HEADERS=["*"]
```

См. полный список в [docs/CONFIGURATION.md](./docs/CONFIGURATION.md)
IDEMPOTENCY_CACHE_TTL_S=86400              # TTL кеша (24 часа)
```

См. подробности в [docs/CONFIGURATION.md](./docs/CONFIGURATION.md)

---

## Потоки данных

### Исходящие сообщения (Sales Agent → Backend → Wappi)

```
1. Sales Agent генерирует ответ → OutboundDeliveryRequest
2. POST /api/v1/internal/messages/outbound (в Backend)
3. Backend маршрутизирует по connector.type → POST /transport/delivery (X-Service-Key, X-Connector-Id)
4. wappi-module валидирует и проверяет идемпотентность
5. Извлекает recipient из metadata.chat_id
6. Отправляет в Wappi API:
   POST https://wappi.pro/tapi/async/message/send?profile_id={id}
   Authorization: {wappi_token}
   Body: {"body": "текст", "recipient": "351311665"}
7. Retry при 429/5xx с экспоненциальным backoff
8. Возврат 200 OK или 500 Error
```

### Входящие сообщения (Wappi → Backend → Sales Agent)

```
1. Пользователь пишет в Telegram/WhatsApp
2. Wappi отправляет webhook:
   POST /wappi/{connector_id}/webhook
   Body: {"messages": [...]}
3. wappi-module логирует и проверяет connector_id
4. Нормализует в InboundEnvelope и форвардит в Backend:
   POST /api/v1/messages/inbound
   Headers: X-Service-Key, X-Connector-Id
5. Backend валидирует и форвардит в Sales Agent:
   POST /api/v1/internal/messages/inbound
6. Sales Agent нормализует через внутренний обработчик
7. Debounce → Pipeline → LLM → Ответ → Backend → wappi-module → Wappi
```

---

## Wappi API Integration

### Настройка в Wappi Dashboard

1. **Получить credentials:**
   - Зайти на https://wappi.pro/dashboard
   - Profile Settings → скопировать:
     - API Token → `wappi_token`
     - Profile ID → `wappi_profile_id` (ПОЛНЫЙ UUID, 36 символов!)

2. **Настроить Webhook URL:**
   ```
   https://your-domain.com/wappi/{connector_id}/webhook
   ```

3. **Сохранить в БД backend:**
   ```sql
   INSERT INTO backend.wappi_connectors (
       connector_id, company_id, wappi_token, wappi_profile_id, channel_type
   ) VALUES (
       'test', 1, 'your-token', 'full-uuid-36-chars', 'telegram'
   );
   ```

### Формат отправки (используется wappi-module)

```http
POST https://wappi.pro/tapi/async/message/send?profile_id={full-uuid}
Authorization: {wappi_token}
Content-Type: application/json

{
  "body": "текст сообщения",
  "recipient": "351311665"
}
```

**Важно:**
- `profile_id` — query parameter (НЕ в теле!)
- `Authorization` — без префикса "Bearer"
- `recipient` — это `chatId` из входящего webhook

---

## Идемпотентность

**Проблема:** Sales Agent может повторно отправить сообщение (retry, restart и т.д.)

**Решение:** TTL-кеш по `correlation_id` (24 часа)

```python
# Первая попытка
POST /transport/delivery
correlation_id: "sa331c532f"
→ 200 OK {"status": "delivered"}

# Повторная попытка (в течение 24 часов)
POST /transport/delivery
correlation_id: "sa331c532f"
→ 409 Conflict {"status": "duplicate", "detail": "Message already delivered 3600 seconds ago"}
```

**Sales Agent обрабатывает 409 как успех** — сообщение уже доставлено.

---

## Retry логика

### Условия retry

✅ **Retry при:**
- `429 Too Many Requests` (rate limit)
- `5xx Server Error` (Wappi временно недоступен)
- `httpx.ConnectError` (connection timeout)
- `httpx.ReadTimeout`

❌ **НЕ retry при:**
- `400 Bad Request` (невалидный запрос, не исправится)
- `401 Unauthorized` (неверный токен)
- `404 Not Found` (неверный endpoint)

### Параметры

```python
MAX_DELIVERY_ATTEMPTS = 3
BACKOFF = [1.0, 2.0, 4.0]  # Экспоненциальный
```

**Пример:**
```
Попытка 1 → 429 → Wait 1s → Retry
Попытка 2 → 429 → Wait 2s → Retry
Попытка 3 → 200 → Success
```

---

## Логирование

**Формат:** JSON (structlog)

### Ключевые события

| Event | Level | Описание |
|-------|-------|----------|
| `app.start` | info | Старт приложения |
| `connector.reload.completed` | info | Загрузка конфигов (count=N) |
| `connector.added/removed/updated` | info | Изменение конфигурации |
| `transport.delivery.preparing` | debug | Начало доставки |
| `transport.delivery.delivered` | info | Успешная доставка |
| `transport.delivery.duplicate` | warning | Повторная попытка (409) |
| `transport.delivery.failed` | error | Ошибка доставки |
| `wappi.api.sending_request` | info | Запрос к Wappi API |
| `wappi.api.message_sent` | debug | Успешный ответ |
| `wappi.webhook.received` | info | Входящий webhook |
| `wappi.webhook.forwarded` | info | Успешный форвард в Sales Agent |
| `wappi.webhook.forward_failed` | error | Ошибка форварда |

### Фильтрация логов

```bash
# Только ошибки
grep '\[error\]' logs.txt

# Transport delivery
grep 'transport.delivery' logs.txt

# Webhook-и
grep 'wappi.webhook' logs.txt

# Конкретный correlation_id
grep 'sa331c532f' logs.txt
```

---

## Troubleshooting

### Частые проблемы

| Проблема | Решение |
|----------|---------|
| **404 на webhook** | Проверьте `connector.reload.completed` — загружены ли коннекторы? |
| **profile_id incorrect** | Убедитесь что `wappi_profile_id` — ПОЛНЫЙ UUID (36 символов), не короткий (13) |
| **Нет recipient** | Sales Agent должен передавать `metadata.chat_id` |
| **422 от Sales Agent** | Wappi шлёт `delivery_status` как объект `{}`, а не массив `[]` — исправьте в Sales Agent |
| **401 Unauthorized** | Проверьте `SERVICE__API_KEY` одинаковый в обоих сервисах |
| **502 Bad Gateway** | Sales Agent недоступен или медленно обрабатывает |


---

## Тестирование

### Health Check

```bash
curl http://localhost:8002/healthz
# {"status": "ok"}
```

### Force Reload

```bash
curl -X POST http://localhost:8002/admin/reload
# {"status": "reloaded", "connectors_count": 1}
```

### Test Transport Delivery

```bash
curl -X POST http://localhost:8002/transport/delivery \
  -H "Content-Type: application/json" \
  -H "X-Service-Key: your-key" \
  -H "X-Connector-Id: test" \
  -d '{
    "connector_id": "test",
    "company_id": "1",
    "channel_type": "telegram",
    "user_id": "351311665",
    "conversation_id": "351311665",
    "correlation_id": "unique-id-123",
    "replies": ["Тестовое сообщение"],
    "metadata": {"chat_id": "351311665"}
  }'
```

### Test Webhook (от Wappi)

```bash
curl -X POST http://localhost:8002/wappi/test/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{
      "id": "test123",
      "wh_type": "incoming_message",
      "body": "Привет!",
      "chatId": "351311665",
      "profile_id": "b51675ef-d41f",
      "type": "text",
      "platform": "telegram"
    }]
  }'
```

---

## Deployment

### Docker

```bash
# Build
docker build -t wappi-module:latest -f apps/wappi-module/Dockerfile .

# Run
docker run -p 8002:8002 \
  -e BACKEND__URL=http://backend:8001 \
  -e SERVICE__API_KEY=secret \
  wappi-module:latest
```

### Docker Compose

```bash
docker-compose up wappi-module
```

### Kubernetes

```bash
kubectl apply -f k8s/wappi-module/
```

См. подробности в [docs/CONFIGURATION.md](./docs/CONFIGURATION.md)

---

## Документация

| Документ | Описание |
|----------|----------|
| [ARCHITECTURE.md](./docs/ARCHITECTURE.md) | Архитектура, компоненты, модели данных |
| [API.md](./docs/API.md) | Описание endpoints, request/response, примеры |
| [CONFIGURATION.md](./docs/CONFIGURATION.md) | Настройка, deployment, security |
| [STRUCTURE.md](./docs/STRUCTURE.md) | Структура кода (legacy, обновлено выше) |
| [INTEGRATION.md](./docs/INTEGRATION.md) | Интеграция с backend и Wappi (legacy, обновлено выше) |

---

## Разработка

### Установка pre-commit hooks

```bash
# Форматирование
uv run ruff format .

# Linting
uv run ruff check --fix .

# Type checking (если настроен pyright)
uv run pyright
```

### Запуск тестов

```bash
cd apps/wappi-module
uv run pytest
```

### Структура кода

```
src/wappi_module/
├── main.py                 # FastAPI app, lifespan
├── config/
│   └── settings.py         # Settings (extends common.WappiModuleSettings)
├── api/
│   ├── dependencies.py     # FastAPI Depends() providers
│   └── routes.py           # HTTP endpoints (4 роутера)
├── connectors/
│   ├── models.py           # WappiConnectorConfig (Pydantic)
│   └── manager.py          # ConnectorManager (lifecycle + reload)
├── services/
│   ├── backend.py          # WappiBackendClient (загрузка конфигов)
│   ├── sales_agent.py      # SalesAgentClient (форвардинг webhooks)
│   └── wappi_api.py        # WappiApiClient (отправка сообщений)
└── transport/
    ├── models.py           # TransportDeliveryPayload (Pydantic)
    └── service.py          # TransportDeliveryService (валидация + retry)
```

---

## Зависимости

```toml
fastapi          # Web framework
uvicorn[standard] # ASGI server
httpx            # Async HTTP client
pydantic         # Data validation
structlog        # Structured logging
python-dotenv    # Environment variables
common           # Shared library (libs/common)
```

---

## Contributing

1. Создайте feature branch: `git checkout -b feature/my-feature`
2. Следуйте стилю кода (ruff format/check)
3. Добавьте тесты
4. Обновите документацию
5. Создайте Pull Request

---

## Известные ограничения

1. **Wappi API несогласованность:**
   - `incoming_message` → `{"messages": [...]}`  (массив)
   - `delivery_status` → `{"messages": {...}}`   (объект)
   - **Решение:** Sales Agent обрабатывает оба варианта

2. **Profile ID short vs full:**
   - Webhook содержит короткий ID: `"b51675ef-d41f"` (13 символов)
   - API требует полный UUID: `"b51675ef-d41f-4891-9dd0-b74d76f5b9b5"` (36)
   - **Решение:** В БД храните полный UUID

3. **In-memory кеш:**
   - Идемпотентность кеш хранится в памяти
   - При рестарте теряется (это безопасно, Sales Agent переотправит)
   - **Улучшение:** Использовать Redis для persistent кеша

---

## Лицензия

Proprietary — Sales Bot Platform

---

## Контакты

- **Документация:** `apps/wappi-module/docs/`
- **Issues:** Internal issue tracker
- **Мониторинг:** `/healthz`, structured logs

---

**Версия:** 0.1.0  
**Обновлено:** 2024-11-21  
**Python:** 3.12+
