# Глоссарий ключевых сущностей

## Connector (`apps/backend/src/backend/modules/transport/models.py`)
Унифицированная модель коннектора в backend. Заменяет устаревшие `TelegramBot` и `WappiConnector`. Ключевые поля:
- `connector_id` — уникальный публичный идентификатор (например, `tg-bot-abc123`)
- `type` — тип коннектора: `telegram`, `wappi`, `custom`
- `channel_type` — канал доставки: `telegram`, `whatsapp`, `custom`
- `managed` — управляемый (true) или custom (false)
- `config` — JSONB с типоспецифичными настройками (bot_token для telegram, wappi_token для wappi)
- `debounce_window_seconds` — окно дебаунса для батчинга сообщений

## ConnectorApiKey (`apps/backend/src/backend/modules/transport/models.py`)
API-ключ для custom-коннекторов. Позволяет внешним системам авторизоваться через `Authorization: Bearer sk_xxx`.

## InboundEnvelope (`libs/common/src/common/models/inbound.py`)
Нормализованная структура входящего сообщения, используемая всеми коннекторами при отправке в Sales Agent:
- `connector_id`, `conversation_id`, `user_id` — идентификаторы
- `text` — текст сообщения
- `audio` — опциональные аудиоданные (base64 + mime)
- `ts` — timestamp

## ConnectorContext (`libs/common/src/common/models/inbound.py`)
Контекст коннектора, возвращаемый backend при валидации:
- `connector_id`, `company_id`, `type`, `channel_type`
- `debounce` — настройки дебаунса

## Debounce Manager (`apps/sales-agent/src/sales_agent/services/debounce.py`)
Буфер сообщений, который объединяет несколько входящих апдейтов в батч с окнами тишины. После истечения окна вызывает `on_batch_callback`, где запускается основной LLM-пайплайн.

## ConnectorSync (`apps/sales-agent/src/sales_agent/services/connector_sync.py`)
Фоновая задача, периодически запрашивающая список доступных коннекторов у backend (`GET /transport/connectors`). Она обновляет `SalesAgentSettings.connectors`, чтобы новые источники/транспорты подхватывались без ручного деплоя Sales Agent.

## ConnectorSettings (`libs/common/src/common/config.py`)
Pydantic-модель, описывающая один коннектор в runtime Sales Agent: `connector_id`, тип (`crm` или `messaging`), каналы, секреты, debounce-параметры, транспортные endpoint'ы и метаданные.

## Backend Connector Endpoints (`apps/backend/src/backend/modules/transport/routers.py`)
REST-эндпоинты для управления коннекторами:
- `GET /transport/connectors` — список всех коннекторов (с фильтрами `?type=telegram&enabled=true`)
- `POST /transport/connectors` — создание коннектора
- `PATCH /transport/connectors/{id}` — обновление
- `DELETE /transport/connectors/{id}` — удаление
- `GET /internal/connectors/{connector_id}` — получение ConnectorContext для managed-коннекторов
- `GET /internal/connectors/validate` — валидация Bearer-токена для custom-коннекторов

## Transport Delivery / Backend Routing (`apps/backend/src/backend/modules/messages/transport_client.py`)
`TransportDelivery` — нормализованная структура ответа для транспортных модулей (connector/company/channel, текст, stage, метаданные). Backend `TransportClient` маршрутизирует ответы на соответствующие транспортные модули на основе `connector.type`, отправляя payload на `{transport_endpoint}/transport/delivery` с повторами, тайм-аутами и телеметрией.

**Note**: Sales Agent больше не вызывает транспорт напрямую. Все ответы отправляются в Backend (`POST /api/v1/internal/messages/outbound`), который выполняет маршрутизацию.

## Telegram Transport Module (`apps/telegram-module`)
Сервис, который:
- получает конфигурацию ботов через `GET /transport/connectors?type=telegram&enabled=true`
- принимает `TransportDeliveryPayload` на `/transport/delivery` от Backend и доставляет ответы в Telegram Bot API
- держит список ботов (`BotManager`) и в polling/webhook-режиме пересылает входящие обновления в Backend через `POST /api/v1/messages/inbound` (Backend затем форвардит в Sales Agent)

## Wappi Transport Module (`apps/wappi-module`)
Сервис для интеграции с Wappi Hub (WhatsApp и Telegram user-proxy):
- получает конфигурацию через `GET /transport/connectors?type=wappi&enabled=true`
- нормализует Wappi webhooks в `InboundEnvelope` и отправляет в Backend (`POST /api/v1/messages/inbound`), который форвардит в Sales Agent

## Company Specification
Полная конфигурация компании: правила, стадии, поля, инструменты. Основная масса данных приходит в envelope от Backend; отдельные тулы могут обращаться к Backend API при необходимости.

## Service API Key (`libs/common/src/common/config.py`)
Единый секрет (`SERVICE__API_KEY`), который передаётся в заголовке `X-Service-Key` для всех сервис-сервис взаимодействий: Sales Agent → транспорты, транспорты → backend. Проверяется на каждой критичной ручке.

## Dual-Path Authentication
Авторизация входящих сообщений в **Backend** (`POST /api/v1/messages/inbound`):
- **Managed connectors**: `X-Service-Key` + `X-Connector-Id` headers
- **Custom connectors**: `Authorization: Bearer sk_xxx` (валидация через backend)

## Environment Variables
Переменные окружения используют двойное подчёркивание (`__`) для вложенных структур:
- `DATABASE__URL` → `settings.database.url`
- `LLM__API_KEY` → `settings.llm.api_key`
- `EVENTING__STREAM__GROUP` → `settings.eventing.stream.group`

## Schema Isolation
База данных использует схемы PostgreSQL для изоляции модулей:
- `backend` — схема для Backend модуля

## Service-to-Service Authentication
Аутентификация между сервисами через `X-Service-Key` header с общим секретом `SERVICE__API_KEY`.

## Event Bus (Redis Streams)
Единый поток событий `backend.events` для асинхронной коммуникации между сервисами. Каждый модуль использует уникальную consumer group (`EVENTING__STREAM__GROUP`).

## Connector Types
- `telegram` — Telegram Bot API коннектор
- `wappi` — Wappi Hub коннектор (WhatsApp/Telegram user-proxy)
- `custom` — внешний коннектор с API ключом

## Channel Types
Типы каналов доставки сообщений:
- `telegram` — Telegram
- `whatsapp` — WhatsApp (через Wappi)

## Managed vs Custom Connectors
- **Managed** — коннекторы, созданные через Backend API, используют `X-Connector-Id` для авторизации
- **Custom** — внешние коннекторы с собственными API ключами (`Authorization: Bearer sk_xxx`)

## Unified Router Pattern
Новый паттерн маршрутизации: все сообщения проходят через Backend (`/api/v1/messages/inbound`), который валидирует коннектор и форвардит в Sales Agent. Ответы возвращаются через Backend (`/api/v1/internal/messages/outbound`), который маршрутизирует в соответствующий транспортный модуль.

## Debounce Window
Окно тишины (по умолчанию 45 секунд) для батчинга сообщений перед отправкой в LLM pipeline. Настраивается глобально (`DEBOUNCE__WINDOW_SECONDS`) или per-channel.

## Connector Sync
Фоновая задача в Sales Agent, периодически запрашивающая список коннекторов у Backend для обновления runtime конфигурации без перезапуска.

## Health Check
Эндпоинт для проверки работоспособности сервиса:
- Backend: `GET /health`
- Sales Agent: `GET /healthz`
- Transport modules: `GET /healthz`

## Migration (Aerich)
Система миграций базы данных через Aerich. Требует ручного добавления префикса схемы в SQL миграций после генерации.

## Workspace (uv)
Монорепозиторий использует uv workspace для управления зависимостями. Все модули объявлены в корневом `pyproject.toml` как workspace members.

## Structured Logging
Логирование через structlog с JSON форматом в production. Все логи содержат структурированные ключи для фильтрации и анализа.

## Langfuse Integration
Опциональная интеграция для трейсинга LLM вызовов. Активируется через `LANGFUSE__ENABLED=true` и настраивается через `LANGFUSE__*` переменные окружения.

---

# Integration Pattern — Service Inheritance + DI Resolution

## Integration (`apps/backend/src/backend/modules/integrations/models.py`)
Модель, привязывающая внешний сервис к компании. Ключевые поля:
- `provider_type: str` — идентификатор провайдера (e.g., `"yclients"`). Это plain string, **не enum** — каждый провайдер-пакет определяет свой тип при регистрации.
- `credentials_encrypted` / `credentials_dek` — зашифрованные креды через Envelope Encryption (никогда plaintext в БД).
- `config: JSONField` — несекретные настройки провайдера (plain JSON).
- `enabled_capabilities: JSONField` — список Capability-значений, которые этот провайдер обеспечивает.
- `enabled: bool` — вкл/выкл.
- `unique_together = [("company", "provider_type")]` — у компании может быть только одна интеграция с каждым провайдером.

## Capability (`libs/common/src/common/integrations.py`)
`StrEnum`, описывающий функциональную область, которую может предоставить внешний сервис. Текущие значения: `PRODUCTS`, `SCHEDULING`, `STAFF`, `CUSTOMER_DATA`, `ORDERS`. Используется для:
- контроля конфликтов (одна capability — один провайдер на компанию)
- маппинга на агентские тулы через `CAPABILITY_TOOLS`
- резолва провайдера в capability action endpoints

## CAPABILITY_TOOLS (`libs/common/src/common/integrations.py`)
Маппинг `Capability → list[AvailableTool]`. Определяет, какие тулы агент получает при активации данной capability у компании. Заполняется integration-specific планами при добавлении конкретных тулов (scheduling/slots, staff/list и т.д.). Пустой в базовой инфраструктуре.

## SERVICE_OVERRIDES (`apps/backend/src/backend/modules/integrations/registry.py`)
Глобальный dict `(provider_type, base_service_class) → override_service_class`. Провайдер-пакеты регистрируют свои переопределения при импорте через `register_override()`. Используется `_resolve()` для поиска нужного сервис-класса.

## PROVIDER_REGISTRY (`apps/backend/src/backend/modules/integrations/registry.py`)
Глобальный dict `provider_type → ProviderInfo`. Содержит метаданные провайдера (display name, поддерживаемые capabilities). Используется:
- для валидации при создании Integration — отклоняет неизвестные `provider_type`
- в эндпоинте `GET /providers` — чтобы фронт знал какие провайдеры доступны

## ProviderInfo (`apps/backend/src/backend/modules/integrations/registry.py`)
`@dataclass(frozen=True)` с метаданными провайдера: `provider_type`, `display_name`, `supported_capabilities`. Регистрируется через `register_provider()` при импорте провайдер-пакета.

## `_resolve()` (`apps/backend/src/backend/modules/integrations/registry.py`)
Ядро DI-резолва. Принимает `(base_cls, company_id)`, загружает все enabled интеграции компании, ищет override в `SERVICE_OVERRIDES`. Возвращает:
- override-инстанс, если ровно одно совпадение
- base-инстанс, если совпадений нет
- `IntegrationConflictError`, если несколько интеграций override'ят один и тот же сервис

## `integration_aware()` / `integration_aware_by_id()` (`apps/backend/src/backend/modules/integrations/registry.py`)
Фабрики FastAPI-зависимостей, оборачивающие `_resolve()`:
- `integration_aware(BaseService)` — для публичных роутов, берёт `company_id` из `CompanyViewerDep`
- `integration_aware_by_id(BaseService)` — для внутренних роутов, берёт `company_id` как path/query параметр

Использование: `ProductsServiceDep = Annotated[ProductsService, Depends(integration_aware(ProductsService))]`

## Service Override (паттерн)
Наследование сервиса, где дочерний класс переопределяет **только** нужные методы. Три режима:
- **Full replacement** — метод полностью возвращает данные из внешнего API
- **Augmentation** — `super().method()` + сайд-эффект (e.g., синхронизация в CRM)
- **No change** — метод не переопределён, работает через нашу БД как обычно

## Capability Conflict Detection
Два уровня проверки:
1. **CRUD time** (`IntegrationService`) — при создании/обновлении интеграции проверяет, что ни одна capability не пересекается с другими интеграциями компании. Если пересечение — `IntegrationCapabilityConflictError`.
2. **Resolve time** (`_resolve()`) — при резолве зависимости проверяет, что не более одного override для данного сервис-класса. Если больше — `IntegrationConflictError`. Ловит код-level конфликты, невидимые на уровне capabilities.

## Envelope Encryption (`libs/common/src/common/crypto.py`)
Сервис шифрования через Fernet:
- Каждая запись получает уникальный DEK (Data Encryption Key)
- DEK шифрует данные, `MASTER_KEY` шифрует DEK
- В БД хранятся `encrypted_data` + `encrypted_dek`, никогда plaintext
- `rotate_master_key()` — перешифровывает DEK новым мастер-ключом без перешифровки данных
- `ENCRYPTION__MASTER_KEY` — переменная окружения, обязательная при работе с интеграциями

## IntegrationService (`apps/backend/src/backend/modules/integrations/service.py`)
CRUD-сервис для Integration. Отвечает за:
- шифрование/дешифрование credentials через `EnvelopeEncryption`
- валидацию `provider_type` через `PROVIDER_REGISTRY`
- проверку capability conflicts
- CRUD операции

## Integration Endpoints (`apps/backend/src/backend/modules/integrations/routers.py`)
REST API для управления интеграциями:
- `GET /companies/{company_id}/integrations/providers` — список зарегистрированных провайдеров
- `GET /companies/{company_id}/integrations` — список интеграций компании
- `POST /companies/{company_id}/integrations` — создание
- `GET /companies/{company_id}/integrations/{id}` — чтение
- `PATCH /companies/{company_id}/integrations/{id}` — обновление
- `DELETE /companies/{company_id}/integrations/{id}` — удаление

## Provider Package (конвенция)
Самодостаточный пакет в `apps/backend/src/backend/integrations/<provider_name>/`:
```
<provider_name>/
├── __init__.py      # register_provider() + register_override()
├── client.py        # HTTP-клиент, наследник BaseIntegrationClient
├── config.py        # Pydantic-схема credentials/config
├── schemas.py       # Типы ответов внешнего API
└── services/        # Override-классы сервисов
```
Регистрация происходит при импорте `__init__.py`. Каждый провайдер полностью изолирован — удаление пакета полностью убирает интеграцию.
