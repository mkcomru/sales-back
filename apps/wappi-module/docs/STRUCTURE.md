# Структура Wappi Module

## Созданные файлы

```
apps/wappi-module/
├── src/wappi_module/
│   ├── __init__.py              # Метаданные модуля
│   ├── main.py                  # FastAPI app + lifespan
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py          # WappiModuleSettings
│   ├── connectors/
│   │   ├── __init__.py
│   │   ├── models.py            # WappiConnectorConfig
│   │   └── manager.py           # ConnectorManager (загрузка из backend)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── backend.py           # WappiBackendClient (GET /transport/wappi/connectors)
│   │   ├── sales_agent.py       # BackendInboundClient (форвардинг webhooks в Backend)
│   │   └── wappi_api.py         # WappiApiClient (POST /api/async/message/send)
│   ├── transport/
│   │   ├── __init__.py
│   │   ├── models.py            # TransportDeliveryPayload
│   │   └── service.py           # TransportDeliveryService (валидация + отправка)
│   └── api/
│       ├── __init__.py
│       ├── dependencies.py      # FastAPI DI
│       └── routes.py            # Endpoints: /transport/delivery, /wappi/{id}/webhook, /healthz, /admin/reload
├── docs/
│   ├── INTEGRATION.md           # Инструкция по интеграции
│   └── STRUCTURE.md             # Этот файл
├── README.md                    # Основная документация
├── pyproject.toml               # Зависимости
└── Makefile                     # Команды запуска

libs/common/
├── src/common/
│   ├── config.py                # + WappiModuleSettings
│   └── __init__.py              # + экспорт WappiModuleSettings
```

## Ключевые компоненты

### 1. ConnectorManager
- Загружает список коннекторов из backend (`GET /transport/wappi/connectors`)
- Периодически обновляет конфигурацию (каждые 60 секунд)
- Хранит мапинг `connector_id` → `WappiConnectorConfig`

### 2. WappiApiClient
```python
async def send_message(
    wappi_token: str,
    profile_id: str,
    recipient: str,  # номер телефона или chat_id
    body: str,       # текст сообщения
) -> dict
```
- Отправляет в `POST https://wappi.pro/api/async/message/send`
- Авторизация: `Authorization: Bearer {wappi_token}`

### 3. TransportDeliveryService
- Принимает `POST /transport/delivery` от sales-agent
- Валидирует `X-Service-Key` + `X-Connector-Id`
- Проверяет идемпотентность по `correlation_id` (TTL 24ч)
- Вызывает `WappiApiClient.send_message()`
- Retry логика: до 3 попыток с экспоненциальной задержкой

### 4. Webhook Handling
- `POST /wappi/{connector_id}/webhook` — принимает от Wappi
- Форвардит в Backend через `BackendInboundClient` (Backend затем форвардит в Sales Agent)
- Sales Agent обрабатывает через `WappiHubInboundConnector` (уже существует)

## Поток данных

### Исходящие сообщения (Sales Agent → Backend → Wappi)
```
Sales Agent
    ↓ POST /api/v1/internal/messages/outbound
    ↓ headers: X-Service-Key
    ↓ body: OutboundDeliveryRequest
Backend (TransportClient)
    ↓ маршрутизация по connector.type
    ↓ POST /transport/delivery
    ↓ headers: X-Service-Key, X-Connector-Id
    ↓ body: TransportDeliveryPayload
wappi-module (TransportDeliveryService)
    ↓ валидация + идемпотентность
    ↓ извлечение recipient из metadata
WappiApiClient
    ↓ POST https://wappi.pro/api/async/message/send
    ↓ Authorization: Bearer {wappi_token}
    ↓ body: {profile_id, recipient, body}
Wappi API → Пользователь
```

### Входящие сообщения (Wappi → Backend → Sales Agent)
```
Wappi API (webhook)
    ↓ POST /wappi/{connector_id}/webhook
    ↓ body: {messages: [{...}]}
wappi-module (wappi_webhook)
    ↓ получение connector config
    ↓ нормализация в InboundEnvelope
BackendInboundClient
    ↓ POST /api/v1/messages/inbound
    ↓ headers: X-Service-Key, X-Connector-Id
Backend
    ↓ валидация + получение ConnectorContext
    ↓ POST /api/v1/internal/messages/inbound
    ↓ headers: X-Service-Key
Sales Agent
    ↓ normalize → IncomingMessage
DebounceManager → Pipeline → Ответ → Backend → Wappi
```

## Отличия от telegram-module

| Аспект | telegram-module | wappi-module |
|--------|-----------------|--------------|
| **Режимы** | webhook + polling | только webhook |
| **Bot Manager** | aiogram Dispatcher | простой ConnectorManager |
| **API клиент** | aiogram Bot | кастомный WappiApiClient |
| **Авторизация** | bot_token встроен | Bearer token в заголовке |
| **Идентификация** | chat_id из Telegram | recipient (номер/chat_id) |
| **Конфигурация** | TelegramBot (bot_token, webhook_secret) | WappiConnector (wappi_token, wappi_profile_id) |

## Зависимости

- `fastapi` — HTTP API
- `httpx` — HTTP клиент для backend/sales-agent/Wappi API
- `structlog` — логирование
- `pydantic` — валидация моделей
- `common` — shared библиотека (WappiModuleSettings)

## Запуск

```bash
# Из корня репозитория
uv sync  # установить зависимости

# Запуск wappi-module
cd apps/wappi-module
uv run uvicorn wappi_module.main:app --reload --port 8002

# Или из корня
uv run --package wappi-module uvicorn wappi_module.main:app --reload --port 8002
```

## Endpoints

- `POST /transport/delivery` — приём от sales-agent (основной)
- `POST /wappi/{connector_id}/webhook` — приём webhook от Wappi
- `POST /admin/reload` — принудительная перезагрузка конфигурации
- `GET /healthz` — health check

