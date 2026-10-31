# Wappi Module — Архитектура

## Назначение

**wappi-module** — это микросервис-адаптер между **Sales Agent** и **Wappi API**, обеспечивающий:

1. **Двунаправленную коммуникацию**:
   - Входящие сообщения: `Wappi → wappi-module → Sales Agent`
   - Исходящие сообщения: `Sales Agent → wappi-module → Wappi API`

2. **Централизованное управление коннекторами**:
   - Загрузка конфигурации из backend
   - Периодическое обновление (hot-reload)
   - Поддержка множества компаний с изолированными настройками

3. **Гарантии доставки**:
   - Идемпотентность по `correlation_id`
   - Retry логика с экспоненциальным backoff
   - TTL-кеш для предотвращения дубликатов

---

## Компоненты системы

```
┌─────────────────────────────────────────────────────────────────┐
│                         WAPPI MODULE                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  API LAYER (FastAPI)                                     │   │
│  ├──────────────────────────────────────────────────────────┤   │
│  │  • /transport/delivery      (входящие от Sales Agent)    │   │
│  │  • /wappi/{id}/webhook      (входящие от Wappi)         │   │
│  │  • /admin/reload            (управление)                 │   │
│  │  • /healthz                 (мониторинг)                │   │
│  └──────────────────────────────────────────────────────────┘   │
│                          ↓                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  CONNECTOR MANAGER                                        │   │
│  ├──────────────────────────────────────────────────────────┤   │
│  │  • Загрузка из backend (GET /transport/wappi/connectors) │   │
│  │  • Периодическое обновление (каждые 60 сек)             │   │
│  │  • Хранение: connector_id → WappiConnectorConfig        │   │
│  │  • Отслеживание изменений и hot-reload                   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                          ↓                                       │
│  ┌──────────────────┬───────────────────────────────────────┐   │
│  │ TRANSPORT        │  WEBHOOK FORWARDER                    │   │
│  │ DELIVERY SERVICE │  (BackendInboundClient)               │   │
│  ├──────────────────┴───────────────────────────────────────┤   │
│  │  • Валидация X-Service-Key + X-Connector-Id             │   │
│  │  • Проверка идемпотентности (correlation_id cache)       │   │
│  │  • Форвардинг webhook-ов в Backend (который форвардит в Sales Agent) │   │
│  │  • Retry логика (до 3 попыток)                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                          ↓                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  WAPPI API CLIENT                                        │   │
│  ├──────────────────────────────────────────────────────────┤   │
│  │  • POST /tapi/async/message/send                         │   │
│  │  • Authorization: {wappi_token}                          │   │
│  │  • Параметры: profile_id, recipient, body               │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

        ↑ webhooks                        ↓ API calls
        │                                 │
   ┌────┴───────┐                   ┌────┴────────┐
   │   WAPPI    │                   │ SALES AGENT │
   │    API     │                   │   SERVICE   │
   └────────────┘                   └─────────────┘
```

---

## Структура кода

```
apps/wappi-module/
├── src/wappi_module/
│   ├── main.py                     # FastAPI app, lifespan, DI container
│   │
│   ├── config/
│   │   └── settings.py             # WappiModuleSettings (extends common.WappiModuleSettings)
│   │
│   ├── api/
│   │   ├── dependencies.py         # FastAPI Depends() провайдеры
│   │   └── routes.py               # HTTP endpoints (4 роутера)
│   │
│   ├── connectors/
│   │   ├── models.py               # WappiConnectorConfig (Pydantic)
│   │   └── manager.py              # ConnectorManager (lifecycle + reload)
│   │
│   ├── services/
│   │   ├── backend.py              # WappiBackendClient (загрузка конфигов)
│   │   ├── sales_agent.py          # BackendInboundClient (форвардинг webhooks в Backend)
│   │   └── wappi_api.py            # WappiApiClient (отправка сообщений)
│   │
│   └── transport/
│       ├── models.py               # TransportDeliveryPayload (Pydantic)
│       └── service.py              # TransportDeliveryService (валидация + retry)
│
├── docs/
│   ├── ARCHITECTURE.md             # Этот файл
│   ├── API.md                      # Описание endpoints
│   ├── CONFIGURATION.md            # Настройка и deployment
│   ├── DATA_FLOWS.md               # Потоки данных
│   └── TROUBLESHOOTING.md          # Решение проблем
│
└── tests/
    └── ...
```

---

## Ключевые классы

### 1. **ConnectorManager**

```python
class ConnectorManager:
    _connectors: dict[str, WappiConnectorConfig]
    _lock: asyncio.Lock
    
    async def reload() -> None:
        """Загружает конфигурацию из backend и обновляет _connectors"""
    
    def get(connector_id: str) -> WappiConnectorConfig | None:
        """Возвращает конфигурацию коннектора"""
```

**Ответственность:**
- Загрузка конфигов из `backend` через `WappiBackendClient`
- Периодическое обновление (background task в `main.py`)
- Diff-анализ изменений (добавление/удаление/обновление)
- Thread-safe доступ через `asyncio.Lock`

---

### 2. **TransportDeliveryService**

```python
class TransportDeliveryService:
    _delivered_cache: dict[str, float]  # correlation_id → timestamp
    
    async def deliver(payload: TransportDeliveryPayload) -> None:
        """Доставляет сообщения в Wappi API с retry логикой"""
```

**Ответственность:**
- Валидация `TransportDeliveryPayload`
- Проверка идемпотентности (`correlation_id` в TTL-кеше)
- Извлечение `recipient` из `metadata.chat_id` или `metadata.extra.chat_id`
- Вызов `WappiApiClient.send_message()` с retry
- Очистка устаревших записей из кеша

**Retry логика:**
- Попытки: 1, 2, 3 (настраивается через `max_delivery_attempts`)
- Задержки: 1s, 2s, 4s (экспоненциальный backoff)
- Retry для: `429 Too Many Requests`, `5xx Server Error`, `httpx.ConnectError`
- Не retry для: `400 Bad Request`, `401 Unauthorized`, `404 Not Found`

---

### 3. **WappiApiClient**

```python
class WappiApiClient:
    async def send_message(
        wappi_token: str,
        profile_id: str,
        recipient: str,
        body: str
    ) -> dict:
        """Отправляет сообщение через Wappi API"""
```

**HTTP запрос:**
```http
POST https://wappi.pro/tapi/async/message/send?profile_id={profile_id}
Authorization: {wappi_token}
Content-Type: application/json

{
  "body": "текст сообщения",
  "recipient": "351311665"
}
```

**Ответственность:**
- Формирование HTTP-запроса к Wappi API
- Передача `profile_id` как query parameter (НЕ в теле!)
- Передача токена без префикса "Bearer"
- Обработка ошибок: `WappiApiError`

---

### 4. **BackendInboundClient**

```python
class BackendInboundClient:
    async def forward_update(
        connector_id: str,
        connector: WappiConnectorConfig,
        update: dict[str, Any]
    ) -> None:
        """Форвардит webhook от Wappi в Backend (который форвардит в Sales Agent)"""
```

**HTTP запрос:**
```http
POST http://backend:8001/api/v1/messages/inbound
X-Service-Key: {service_key}
X-Connector-Id: {connector_id}
Content-Type: application/json

{
  "connector_id": "...",
  "conversation_id": "...",
  "user_id": "...",
  "text": "...",
  "ts": 1234567890.0
}
```

**Ответственность:**
- Нормализация входящих webhook-ов от Wappi в `InboundEnvelope` формат
- Форвардинг в Backend через unified inbound endpoint (`/api/v1/messages/inbound`)
- Backend затем форвардит в Sales Agent через internal endpoint
- Обработка ошибок: `BackendInboundClientError`

---

### 5. **WappiBackendClient**

```python
class WappiBackendClient:
    async def fetch_connectors() -> list[WappiConnectorConfig]:
        """Загружает список активных коннекторов из backend"""
```

**HTTP запрос:**
```http
GET http://backend:8001/transport/wappi/connectors
X-Service-Key: {SERVICE__API_KEY}
```

**Ответственность:**
- Загрузка конфигурации из backend API
- Парсинг и валидация через Pydantic
- Логирование невалидных конфигов (не прерывает загрузку остальных)

---

## Модели данных

### WappiConnectorConfig

```python
@dataclass
class WappiConnectorConfig:
    connector_id: str           # Уникальный ID коннектора
    company_id: str             # ID компании (строка!)
    wappi_token: SecretStr      # API токен Wappi
    wappi_profile_id: str       # Profile ID (полный UUID)
    channel_type: str           # "telegram", "whatsapp", etc.
    metadata: dict[str, Any]    # Дополнительные настройки
```

**Валидация:**
- `company_id` конвертируется в строку (может приходить как `int`)
- `wappi_token` — секретный, не логируется
- `wappi_profile_id` — ДОЛЖЕН быть полным UUID (36 символов)

---

### TransportDeliveryPayload

```python
@dataclass
class TransportDeliveryPayload:
    connector_id: str
    company_id: str
    channel_type: str
    user_id: str
    conversation_id: str
    correlation_id: str         # Уникальный ID для идемпотентности
    replies: list[str]          # Массив текстовых сообщений
    metadata: dict[str, Any]    # ОБЯЗАТЕЛЬНО содержит chat_id
    stage_id: str | None
    handoff: dict | None
    delivery_hint: dict | None
    attachments: list[dict] | None
```

**Требования:**
- `replies` — минимум 1 непустая строка
- `metadata.chat_id` или `metadata.extra.chat_id` — ОБЯЗАТЕЛЕН (используется как `recipient`)
- `correlation_id` — уникален для каждого сообщения (генерируется Sales Agent)

---

## Потоки выполнения

### Инициализация (startup)

```python
# main.py → lifespan()
1. setup_logging()
2. WappiBackendClient.init()
3. BackendInboundClient.init()
4. ConnectorManager.init()
5. TransportDeliveryService.init()
6. ConnectorManager.reload()  # Первая загрузка конфигов
7. asyncio.create_task(periodic_reload(60s))  # Background task
8. FastAPI app start
```

### Периодическое обновление (background)

```python
# main.py → periodic_reload()
while True:
    await asyncio.sleep(60)
    await connector_manager.reload()
```

**ConnectorManager.reload():**
```python
1. backend.fetch_connectors()  # GET /transport/wappi/connectors
2. Diff анализ: to_add, to_remove, to_update
3. Обновление _connectors словаря (под asyncio.Lock)
4. Логирование изменений: connector.added/removed/updated
```

### Shutdown (teardown)

```python
1. Отмена background task (reload_task.cancel())
2. ConnectorManager.shutdown()  # Очистка _connectors
3. Graceful shutdown FastAPI
```

---

## Зависимости

### Внешние сервисы

- **backend** (`http://localhost:8001`) — конфигурация коннекторов
- **sales-agent** (`http://localhost:8000`) — обработка входящих сообщений
- **Wappi API** (`https://wappi.pro`) — отправка исходящих сообщений

### Python пакеты

```toml
fastapi          # Web framework
uvicorn[standard] # ASGI server
httpx            # Async HTTP client
pydantic         # Data validation
structlog        # Structured logging
python-dotenv    # Env variables
common           # Shared library (libs/common)
```

---

## Безопасность

### Аутентификация между сервисами

**Sales Agent → wappi-module:**
```http
X-Service-Key: {SERVICE__API_KEY}
X-Connector-Id: {connector_id}
```

**wappi-module → backend:**
```http
X-Service-Key: {SERVICE__API_KEY}
```

**wappi-module → Sales Agent:**
```http
X-Connector-Id: {connector_id}
X-Company-Id: {company_id}
```

**wappi-module → Wappi API:**
```http
Authorization: {wappi_token}
```

### Защита от повторной отправки

- TTL-кеш по `correlation_id` (24 часа)
- При повторной попытке: `409 Conflict`
- Клиент обрабатывает 409 как успешную доставку

---

## Метрики и мониторинг

### Логи (structlog)

**Ключевые события:**

| Event | Level | Когда |
|-------|-------|-------|
| `app.start` | info | Старт приложения |
| `connector.reload.completed` | info | Успешная загрузка конфигов |
| `connector.added/removed/updated` | info | Изменение конфигурации |
| `transport.delivery.preparing` | debug | Начало доставки |
| `transport.delivery.delivered` | info | Успешная доставка |
| `transport.delivery.duplicate` | warning | Повторная попытка доставки |
| `transport.delivery.failed` | error | Ошибка доставки |
| `wappi.api.sending_request` | info | Запрос к Wappi API |
| `wappi.api.message_sent` | debug | Успешный ответ от Wappi |
| `wappi.api.http_error` | error | HTTP ошибка от Wappi |
| `wappi.webhook.received` | info | Входящий webhook от Wappi |
| `wappi.webhook.forwarded` | info | Успешный форвард в Sales Agent |
| `wappi.webhook.forward_failed` | error | Ошибка форварда |

### Health check

```http
GET /healthz
Response: {"status": "ok"}
```

---

## Ограничения и известные проблемы

### 1. Wappi API несогласованность

**Проблема:** Wappi отправляет разные структуры для разных типов webhook-ов:

- `incoming_message`: `{"messages": [...]}`  ← массив
- `delivery_status`: `{"messages": {...}}`   ← объект

**Решение:** Sales Agent должен обрабатывать оба варианта в `WappiHubInboundConnector.normalize()`.

### 2. Profile ID короткий vs полный

**Проблема:**
- Wappi webhook содержит короткий `profile_id`: `"b51675ef-d41f"` (13 символов)
- Wappi API требует полный UUID: `"b51675ef-d41f-4891-9dd0-b74d76f5b9b5"` (36 символов)

**Решение:** В БД backend должен храниться **полный UUID**.

### 3. Recipient extraction

**Проблема:** `recipient` для Wappi API должен быть `chatId` из входящего webhook.

**Решение:** 
- Sales Agent сохраняет `chatId` в `metadata.chat_id` при нормализации
- wappi-module извлекает: `metadata.get("chat_id") or metadata.get("extra", {}).get("chat_id")`

---

## Сравнение с telegram-module

| Аспект | telegram-module | wappi-module |
|--------|-----------------|--------------|
| **Режимы работы** | webhook + polling | только webhook |
| **Bot framework** | aiogram (Dispatcher, Bot) | Нет, чистый HTTP |
| **API клиент** | aiogram.Bot | Кастомный WappiApiClient |
| **Авторизация** | bot_token встроен в URL | Authorization header |
| **Конфигурация** | bot_token, webhook_secret | wappi_token, wappi_profile_id |
| **Идентификация** | chat_id (число) | recipient (строка) |
| **Retry логика** | Нет (aiogram обрабатывает) | Да, кастомная |
| **Webhook validation** | Telegram signature | Опционально (x-wappi-signature) |

---

## Дальнейшее развитие

### Возможные улучшения:

1. **Persistent cache для идемпотентности** (Redis вместо in-memory)
2. **Метрики** (Prometheus counters/histograms)
3. **Rate limiting** (на входящие webhooks)
4. **Webhook signature validation** (проверка x-wappi-signature)
5. **Attachment support** (изображения, файлы)
6. **Batch delivery** (групповая отправка сообщений)
7. **Dead letter queue** (для failed deliveries)
8. **Circuit breaker** (для защиты от каскадных отказов)

---

**Документ обновлён:** 2024-11-21  
**Версия модуля:** 0.1.0

