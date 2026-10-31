# План 015: Ревью архитектуры History Sync + Миграция на Connector-Owned Sync

## Контекст

План 014 описывает реализацию sync где **Backend напрямую вызывает внешние API** (Wappi). Данный документ — архитектурное ревью этого подхода и план миграции на **Connector-Owned Sync**.

---

# Часть 1: Архитектурное ревью плана 014

## Проблема 1: Backend знает про внешние API

### Где в плане

> Этап 3: Создание сервиса синхронизации истории (Backend)
> - Использовать существующий `WappiApiClient` из wappi-module
> - Или создать клиент в backend для прямых вызовов Wappi API

### Почему плохо

Backend — ядро CRM. Его ответственность: бизнес-логика, хранение данных, права доступа. Он **не должен** знать:
- Как Wappi структурирует JSON ответы
- Какие endpoints у Wappi API (`/tapi/sync/chats/get`)
- Как парсить `fromMe` поле для определения роли

### Что происходит при масштабировании

```
Сейчас (1 тип коннектора):
Backend содержит: WappiApiClient

Через 3 месяца (3 типа):
Backend содержит: WappiApiClient + InstagramApiClient + WhatsAppBusinessApiClient

Через год (10 типов):
Backend содержит: 10 разных API клиентов, каждый со своим форматом, auth, rate limits
```

Backend превращается в "god service" который знает всё обо всех внешних системах.

### Нарушение принципов

| Принцип | Нарушение |
|---------|-----------|
| Single Responsibility | Backend = CRM core + Wappi client + Instagram client + ... |
| Dependency Inversion | Ядро (Backend) зависит от периферии (Wappi API) |
| Domain Encapsulation | Знание о Wappi размазано между wappi-module и backend |

---

## Проблема 2: Дублирование доменного знания

### Где в плане

> Интеграция с Wappi API:
> - Использовать существующий `WappiApiClient` из wappi-module

### Почему плохо

`wappi-module` уже понимает Wappi API:
- Знает как авторизоваться
- Знает формат webhook'ов
- Знает как отправлять сообщения

Если Backend тоже реализует `WappiApiClient`:
- **Два места** знают один домен
- Изменение API Wappi требует изменений в **двух** сервисах
- Тесты Wappi интеграции нужны в **двух** местах

### Пример

```
Wappi меняет формат ответа /tapi/sync/messages/get

Нужно изменить:
1. apps/wappi-module/src/wappi_module/... (для webhook'ов)
2. apps/backend/src/backend/modules/transport/wappi_client.py (для sync)

Два PR, два review, два деплоя, риск рассинхрона версий.
```

---

## Проблема 3: Credentials размазаны

### Где в плане

> В `Connector.config` хранить `wappi_token`, `wappi_profile_id`

### Текущая реализация (sync_service.py:193-200)

```python
def _get_wappi_credentials(self, connector: Connector) -> tuple[str, str]:
    config = connector.config or {}
    wappi_config = WappiConnectorConfig.model_validate(config)
    return wappi_config.wappi_token, wappi_config.wappi_profile_id
```

### Почему плохо

Секреты Wappi (`wappi_token`) используются в двух местах:
1. `wappi-module` — для отправки сообщений
2. `backend` — для sync

**Вопрос:** Кто владеет этими credentials?

При правильной архитектуре: только `wappi-module`. Backend не должен знать что такое `wappi_token`.

---

## Проблема 4: Жёсткая привязка к типу коннектора

### Где в коде (sync_service.py:202-206)

```python
async def _validate_wappi_connector(self, connector: Connector) -> None:
    if connector.type != ConnectorType.WAPPI:
        raise ValueError(f"Connector {connector.connector_id} is not Wappi type")
```

### Где в коде (service.py:138-141)

```python
if payload.type == ConnectorTypeEnum.WAPPI and payload.enabled:
    asyncio.create_task(self._auto_start_initial_sync(payload.connector_id))
```

### Почему плохо

Каждый новый тип коннектора требует:
1. Добавить `if connector.type == NEW_TYPE` в service.py
2. Добавить `_validate_new_type_connector()` в sync_service.py
3. Добавить `NewTypeApiClient` в backend

**Не масштабируется.** При 10 типах коннекторов — 10 условий, 10 валидаторов, 10 клиентов.

---

## Проблема 5: Слабая проверка по времени

### Где в коде (chat/service.py:421-435)

```python
if is_historical:
    thread_age = datetime.now(UTC) - thread.created_at.replace(tzinfo=UTC)
    if thread_age < timedelta(minutes=1) and thread.assistant_active:
        # disable assistant
```

### Почему плохо

Проверка "thread создан менее минуты назад" ломается когда:
- Sync занимает больше минуты (backfill может часы)
- Clock drift между серверами
- Сервис перезапустился во время sync
- Сеть тормознула

**Решение:** Явный флаг `is_historical` уже передаётся. Использовать только его, убрать проверку по времени.

---

## Проблема 6: Rate limits захардкожены

### Где в коде (sync_service.py:25-31)

```python
INITIAL_SYNC_RATE = 2.0  # chats per second
BACKFILL_SYNC_RATE = 0.1  # chats per second
CATCHUP_SYNC_RATE = 0.5  # chats per second
```

### Почему плохо

1. Разные провайдеры имеют разные лимиты. Instagram API ≠ Wappi API.
2. Изменение лимита требует ребилда и редеплоя backend.
3. Нет возможности настроить per-connector (у одного клиента может быть premium план с higher limits).

### Как должно быть

- Дефолты в Settings (env variables)
- Возможность override на уровне connector.config

---

## Проблема 7: Дублирование проверки sync status

### Где в коде

**Место 1:** chat/service.py:244-251
```python
if connector_id:
    connector = await connectors_repo.get_by_connector_id(connector_id)
    if connector:
        if connector.sync_status in (SyncStatus.INITIAL, SyncStatus.BACKFILL, SyncStatus.CATCHUP):
            return False
```

**Место 2:** messages/routers.py:156-167
```python
connector = await service.get_by_connector_id(context.connector_id)
if connector:
    if connector.sync_status in (SyncStatus.INITIAL, SyncStatus.BACKFILL, SyncStatus.CATCHUP):
        # skip AI
```

### Почему плохо

Одна и та же логика в двух местах. При изменении условия — нужно менять оба.

### Решение

Property на модели:
```python
class Connector(BaseModel):
    @property
    def is_syncing(self) -> bool:
        return self.sync_status in (SyncStatus.INITIAL, SyncStatus.BACKFILL, SyncStatus.CATCHUP)
```

---

# Часть 2: Целевая архитектура — Connector-Owned Sync

## Принцип

**Connector-module владеет всей логикой интеграции с внешним API, включая sync.**

Backend:
- Предоставляет API для batch ingest сообщений
- Хранит состояние sync (статус, прогресс)
- Не знает деталей внешних API

Connector:
- Знает как работать с внешним API
- Выполняет sync и отправляет batches в Backend
- Владеет credentials и rate limits

## Архитектурная диаграмма

```
┌─────────────────────────────────────────────────────────────┐
│                         BACKEND                              │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              /internal/sync/*                        │    │
│  │  POST /batch    - принять batch сообщений            │    │
│  │  POST /status   - обновить статус sync               │    │
│  │  GET  /cursor   - получить cursor для resume         │    │
│  └─────────────────────────────────────────────────────┘    │
│                          ▲                                   │
│                          │                                   │
│  ┌───────────────────────┼───────────────────────────┐      │
│  │ ConnectorsService     │                           │      │
│  │ - start_sync()  ──────┼──► HTTP to connector      │      │
│  │ - get_status()        │                           │      │
│  │ - cancel_sync() ──────┼──► HTTP to connector      │      │
│  └───────────────────────┼───────────────────────────┘      │
└──────────────────────────┼──────────────────────────────────┘
                           │
                           │ HTTP
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ wappi-module │   │  tg-module   │   │ insta-module │
│              │   │              │   │              │
│ POST /sync   │   │ POST /sync   │   │ POST /sync   │
│   /start     │   │   /start     │   │   /start     │
│   /cancel    │   │   /cancel    │   │   /cancel    │
│              │   │              │   │              │
│ SyncProvider │   │ SyncProvider │   │ SyncProvider │
│      │       │   │      │       │   │      │       │
│      ▼       │   │      ▼       │   │      ▼       │
│ [Wappi API]  │   │ [Telegram]   │   │ [Meta API]   │
└──────────────┘   └──────────────┘   └──────────────┘
```

## Контракты

### Backend → Connector: Команды

```python
# POST {connector_base_url}/internal/sync/start
class SyncStartCommand(BaseModel):
    connector_id: str
    sync_type: Literal["initial", "backfill", "catchup"]
    cursor: str | None = None  # для resume
    since: datetime | None = None  # для catchup

# POST {connector_base_url}/internal/sync/cancel
class SyncCancelCommand(BaseModel):
    connector_id: str
```

### Connector → Backend: Данные

```python
# POST /internal/sync/batch
class SyncBatchRequest(BaseModel):
    connector_id: str
    batch_id: str  # idempotency key
    messages: list[SyncMessage]

class SyncMessage(BaseModel):
    conversation_id: str
    user_id: str
    text: str
    role: MessageRole
    timestamp: datetime
    provider_message_id: str
    sender_name: str | None = None
    sender_phone: str | None = None
    # НЕТ wappi-специфичных полей

# POST /internal/sync/status
class SyncStatusUpdate(BaseModel):
    connector_id: str
    status: SyncStatus
    progress: SyncProgress | None = None
    error: str | None = None
    cursor: str | None = None  # для resume

class SyncProgress(BaseModel):
    total_chats: int
    processed_chats: int
    total_messages: int
    processed_messages: int
```

## Владение ответственностями

| Ответственность | Backend | Connector |
|-----------------|:-------:|:---------:|
| Хранение сообщений | ✅ | ❌ |
| Состояние sync (статус, прогресс) | ✅ | ❌ |
| Cursor для resume | ✅ | ❌ |
| Idempotency (batch_id) | ✅ | ❌ |
| Знание внешнего API | ❌ | ✅ |
| Credentials внешнего API | ❌ | ✅ |
| Rate limiting внешнего API | ❌ | ✅ |
| Retry logic для внешнего API | ❌ | ✅ |
| Трансформация в SyncMessage | ❌ | ✅ |

---

## Проблема: Sync логика дублируется в каждом connector-module

### Суть проблемы

Если каждый connector реализует sync самостоятельно, получаем **новое дублирование**:

```
wappi-module:
├── BackendSyncClient        # HTTP клиент к backend
├── retry_with_backoff()     # Retry logic
├── RateLimiter              # Rate limiting
├── progress_tracker()       # Progress updates
└── WappiSyncProvider        # ← Только это уникально

telegram-module:
├── BackendSyncClient        # Копипаста
├── retry_with_backoff()     # Копипаста
├── RateLimiter              # Копипаста
├── progress_tracker()       # Копипаста
└── TelegramSyncProvider     # ← Только это уникально

instagram-module:
├── BackendSyncClient        # Копипаста ×3
├── ...
```

**90% кода sync — одинаковое.** Уникальна только интеграция с внешним API.

### Решение: Sync Framework в `libs/common`

```
libs/common/src/common/sync/
├── __init__.py
├── base.py           # BaseSyncProvider (ABC)
├── client.py         # BackendSyncClient
├── runner.py         # SyncRunner (orchestration)
├── rate_limiter.py   # RateLimiter
└── schemas.py        # SyncMessage, SyncBatch, etc. (или в contracts/)
```

### Что живёт в `libs/common`

| Компонент | Ответственность |
|-----------|-----------------|
| `BackendSyncClient` | HTTP клиент к Backend (`/internal/sync/*`) |
| `SyncRunner` | Orchestration: start → fetch → batch → send → progress → complete |
| `RateLimiter` | Configurable rate limiting с backoff |
| `BaseSyncProvider` | ABC с методами которые connector реализует |

### Что connector реализует сам

```python
# libs/common/src/common/sync/base.py
class BaseSyncProvider(ABC):
    """Connector наследует и реализует только эти методы."""
    
    @abstractmethod
    async def fetch_dialogs(self, cursor: str | None) -> AsyncIterator[Dialog]:
        """Получить список диалогов от внешнего API."""
        ...
    
    @abstractmethod
    async def fetch_messages(self, dialog_id: str, cursor: str | None) -> AsyncIterator[RawMessage]:
        """Получить сообщения диалога от внешнего API."""
        ...
    
    @abstractmethod
    def transform_message(self, raw: RawMessage) -> SyncMessage:
        """Трансформировать provider-specific формат в SyncMessage."""
        ...
    
    @abstractmethod
    def get_rate_limit(self) -> float:
        """Вернуть rate limit для этого провайдера (requests/sec)."""
        ...
```

### Пример: wappi-module

```python
# apps/wappi-module/src/wappi_module/sync/provider.py
from common.sync import BaseSyncProvider, SyncMessage, Dialog, RawMessage

class WappiSyncProvider(BaseSyncProvider):
    """Только Wappi-специфичная логика."""
    
    async def fetch_dialogs(self, cursor: str | None) -> AsyncIterator[Dialog]:
        # Вызов Wappi API /tapi/sync/chats/get
        response = await self.wappi_client.get_chats(cursor=cursor)
        for dialog in response["dialogs"]:
            yield Dialog(id=dialog["id"], name=dialog.get("name"))
    
    async def fetch_messages(self, dialog_id: str, cursor: str | None) -> AsyncIterator[RawMessage]:
        # Вызов Wappi API /tapi/sync/messages/get
        response = await self.wappi_client.get_messages(dialog_id, cursor=cursor)
        for msg in response["messages"]:
            yield msg  # Raw dict from Wappi
    
    def transform_message(self, raw: RawMessage) -> SyncMessage:
        # Трансформация Wappi формата в универсальный
        return SyncMessage(
            conversation_id=raw["chatId"],
            user_id=raw["from"],
            text=raw["body"],
            role=MessageRole.MANAGER if raw["fromMe"] else MessageRole.USER,
            timestamp=datetime.fromtimestamp(raw["time"]),
            provider_message_id=str(raw["id"]),
        )
    
    def get_rate_limit(self) -> float:
        return 2.0  # Wappi allows 2 req/sec
```

### Запуск sync в connector

```python
# apps/wappi-module/src/wappi_module/sync/controller.py
from common.sync import SyncRunner, BackendSyncClient

async def start_sync(connector_id: str, sync_type: str):
    provider = WappiSyncProvider(connector_id)
    client = BackendSyncClient(backend_url=settings.backend_url)
    
    runner = SyncRunner(provider=provider, client=client)
    await runner.run(sync_type=sync_type)
```

### Результат

| До | После |
|----|-------|
| Каждый connector: ~500 строк sync кода | Каждый connector: ~50 строк (только provider) |
| Баг в retry logic — фиксить в N местах | Баг в retry logic — фиксить в `libs/common` |
| Новый connector = копипаста всего | Новый connector = наследовать `BaseSyncProvider` |
| Rate limits захардкожены per-module | Rate limits через `get_rate_limit()` метод |

**Connector знает только свой внешний API. Всё остальное — shared infrastructure.**

---

# Часть 3: План миграции

## Этап 1: Backend — Batch Ingest API

**Цель:** Backend предоставляет API для приёма batches от connectors.

**Файлы:**
- `apps/backend/src/backend/modules/sync/routers.py` (новый)
- `apps/backend/src/backend/modules/sync/service.py` (новый)
- `apps/backend/src/backend/modules/sync/schemas.py` (новый)
- `libs/common/src/common/contracts/sync.py` (новый)

**Задачи:**
1. Создать `SyncBatchRequest`, `SyncStatusUpdate`, `SyncMessage` в `libs/common`
2. Создать `POST /internal/sync/batch` endpoint:
   - Принимает batch сообщений + `correlation_id`
   - Проверяет `batch_id` на idempotency
   - Создаёт threads и messages через `ChatService`
   - Отвечает 200 OK или 409 Conflict (duplicate batch)
3. Создать `POST /internal/sync/status` endpoint:
   - Обновляет `connector.sync_status`, `sync_progress`
   - Сохраняет cursor для resume
4. Создать `POST /internal/sync/heartbeat` endpoint:
   - Принимает `connector_id` + `correlation_id`
   - Обновляет `last_heartbeat_at` в connector
   - Backend ставит FAILED если нет heartbeat > 2 минут
5. Создать `GET /internal/sync/cursor/{connector_id}` endpoint:
   - Возвращает последний cursor для resume

**Критерии готовности:**
- [ ] Endpoints созданы и задокументированы
- [ ] Схемы в `libs/common` доступны connector-modules
- [ ] Unit тесты на idempotency
- [ ] Heartbeat timeout работает

---

## Этап 2: Backend — Command API для connectors

**Цель:** Backend может отправлять команды start/cancel в connector-module.

**Файлы:**
- `apps/backend/src/backend/modules/transport/sync_commander.py` (новый)
- `apps/backend/src/backend/modules/transport/service.py` (обновить)

**Задачи:**
1. Создать `SyncCommander`:
   ```python
   class SyncCommander:
       async def send_start(self, connector: Connector, sync_type: str, correlation_id: str) -> None
       async def send_cancel(self, connector: Connector) -> None
   ```
2. URL connector-module: **уже есть** `connector.config.transport_endpoint` — используем его
3. Генерировать `correlation_id` при старте sync — передавать в connector, включать во все логи
4. Обновить `ConnectorsService.start_sync()`:
   - Устанавливает `sync_status = INITIAL`
   - Отправляет команду в connector через `SyncCommander`
   - Не ждёт завершения (fire-and-forget с timeout)

**Критерии готовности:**
- [ ] `SyncCommander` создан
- [ ] Backend может отправить start/cancel команду
- [ ] `correlation_id` генерируется и передаётся в connector
- [ ] Timeout handling если connector не отвечает

---

## Этап 3: Sync Framework в libs/common

**Цель:** Shared infrastructure для sync, чтобы connectors не дублировали код.

**Файлы:**
- `libs/common/src/common/sync/__init__.py` (новый)
- `libs/common/src/common/sync/base.py` (новый)
- `libs/common/src/common/sync/client.py` (новый)
- `libs/common/src/common/sync/runner.py` (новый)
- `libs/common/src/common/sync/rate_limiter.py` (новый)

**Задачи:**
1. Создать `BaseSyncProvider` (ABC):
   - `fetch_dialogs()` — получить диалоги
   - `fetch_messages()` — получить сообщения
   - `transform_message()` — трансформировать в `SyncMessage`
   - `get_rate_limit()` — вернуть rate limit провайдера
2. Создать `BackendSyncClient`:
   - `send_batch()` — отправить batch в backend
   - `update_status()` — обновить статус
   - `get_cursor()` — получить cursor для resume
   - `heartbeat()` — сигнал "я жив" независимо от batches (каждые 30 сек)
3. Создать `SyncRunner`:
   - Orchestration: dialogs → messages → transform → batch → send
   - Progress tracking
   - Error handling с retry
   - Background heartbeat task (отправляет heartbeat пока sync идёт)
   - `correlation_id` во всех запросах и логах
4. Создать `RateLimiter`:
   - Configurable rate
   - Exponential backoff при 429

**Критерии готовности:**
- [ ] `BaseSyncProvider` определён
- [ ] `BackendSyncClient` реализован (включая heartbeat)
- [ ] `SyncRunner` работает с любым provider
- [ ] Background heartbeat task в `SyncRunner`
- [ ] `correlation_id` прокидывается везде
- [ ] Unit тесты с mock provider

---

## Этап 4: wappi-module — Sync Provider

**Цель:** wappi-module реализует только Wappi-специфичную логику.

**Уже есть (переиспользуем):**
- `ConnectorManager` — хранит конфиги с credentials (`wappi_token`, `wappi_profile_id`)
- `WappiApiClient` — клиент для Wappi API (уже умеет `get_chats_list`, `get_chat_messages`)
- Credentials flow: Backend → `fetch_connectors()` → `ConnectorManager`

**Файлы:**
- `apps/wappi-module/src/wappi_module/sync/provider.py` (новый)
- `apps/wappi-module/src/wappi_module/sync/controller.py` (новый)
- `apps/wappi-module/src/wappi_module/api/routes.py` (обновить)

**Задачи:**
1. Создать `WappiSyncProvider(BaseSyncProvider)`:
   ```python
   class WappiSyncProvider(BaseSyncProvider):
       def __init__(self, connector_manager: ConnectorManager, wappi_client: WappiApiClient):
           # Переиспользуем существующую инфраструктуру
   ```
   - `fetch_dialogs()` — использует `wappi_client.get_chats_list()`
   - `fetch_messages()` — использует `wappi_client.get_chat_messages()`
   - `transform_message()` — маппинг `fromMe` → role, etc.
   - `get_rate_limit()` — вернуть 2.0 (Wappi limit)
2. Создать `SyncController`:
   - Инстанцирует `WappiSyncProvider` + `SyncRunner`
   - Обрабатывает команды start/cancel
   - Принимает `correlation_id` от Backend
3. Добавить endpoints:
   - `POST /internal/sync/start` — принять команду от Backend
   - `POST /internal/sync/cancel` — отменить sync

**Критерии готовности:**
- [ ] `WappiSyncProvider` наследует `BaseSyncProvider`
- [ ] `SyncController` использует `SyncRunner` из `libs/common`
- [ ] Endpoints для команд созданы
- [ ] Интеграционный тест: mock Wappi API → provider → backend

---

## Этап 5: Удаление sync логики из Backend

**Цель:** Backend больше не содержит Wappi-специфичный код.

**Файлы:**
- `apps/backend/src/backend/modules/transport/sync_service.py` (удалить или рефакторить)
- `apps/backend/src/backend/modules/transport/wappi_client.py` (удалить)

**Задачи:**
1. Удалить `WappiApiClient` из backend
2. Удалить `HistorySyncService._run_initial_sync()`, `_run_backfill_sync()`, etc.
3. Упростить `HistorySyncService` до координатора:
   ```python
   class SyncCoordinator:
       async def start_sync(self, connector_id: str, sync_type: str) -> None:
           # 1. Update status to INITIAL
           # 2. Send command to connector via SyncCommander
           
       async def handle_timeout(self, connector_id: str) -> None:
           # Set status to FAILED if no progress for N minutes
   ```
4. Удалить `_validate_wappi_connector()` и подобные type-specific методы
5. Убрать `if connector.type == WAPPI` условия

**Критерии готовности:**
- [ ] Backend не содержит `WappiApiClient`
- [ ] Backend не знает про Wappi API формат
- [ ] Все `if connector.type == X` убраны из sync логики

---

## Этап 6: Cleanup и унификация

**Цель:** Чистый код без дублирования.

**Задачи:**
1. Добавить `Connector.is_syncing` property
2. Убрать проверку по времени в `chat/service.py`
3. Вынести rate limit defaults в Settings
4. Убрать дублирование sync status check

---

## Этап 7: Тестирование

**Файлы:**
- `apps/backend/tests/domains/sync/test_batch_ingest.py` (новый)
- `apps/wappi-module/tests/domains/sync/test_provider.py` (новый)

**Задачи:**
1. Unit тесты Backend:
   - Batch ingest с idempotency
   - Status updates
   - Cursor management
2. Unit тесты wappi-module:
   - Sync flow с mocked Wappi API
   - Retry logic
   - Rate limiting
3. Integration тест:
   - Mock Wappi API → wappi-module → Backend → DB
   - Проверить что messages сохранены корректно

---

## Открытые проблемы (out of scope)

### Graceful shutdown

**Проблема:** Connector получает SIGTERM во время sync. Что происходит?

**Идеальное решение:**
1. Ловить SIGTERM
2. Дослать текущий batch
3. Отправить status update с cursor
4. Завершиться

**Текущее решение:** Потеряли — retry с cursor. Не критично для MVP.

---

## Риски и митигация

### Риск: Network failure между connector и backend

**Митигация:**
- `batch_id` для idempotency — safe retry
- Cursor хранится в Backend — resume после падения connector
- Heartbeat от connector — Backend знает что sync жив

### Риск: Connector завис / медленно обрабатывает

**Митигация:**
- Heartbeat каждые 30 сек независимо от batches
- Backend timeout: если нет heartbeat > 2 минут — статус FAILED
- При рестарте connector запрашивает cursor и продолжает

### Риск: Backend недоступен

**Митигация:**
- Connector retry с exponential backoff
- Circuit breaker если Backend лежит долго

---

## Критерии приёмки (DoD)

- [ ] Backend не содержит Wappi/Instagram/etc API клиентов
- [ ] Sync логика живёт только в connector-modules
- [ ] Backend предоставляет универсальный batch ingest API
- [ ] Добавление нового типа коннектора не требует изменений в Backend
- [ ] Connector переиспользует существующий `ConnectorManager` и API клиент
- [ ] Rate limits настраиваются per-connector (через `get_rate_limit()`)
- [ ] Resume после падения работает через cursor
- [ ] Heartbeat механизм работает — Backend видит что connector жив
- [ ] `correlation_id` присутствует во всех запросах и логах sync
- [ ] Все тесты проходят
