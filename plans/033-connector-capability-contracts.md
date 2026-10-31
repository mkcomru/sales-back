# 033 — Connector Capability Contracts

## Objective

Ввести декларативную систему capabilities и структурные контракты (ABC) для транспортных коннекторов (telegram, wappi). По образцу того, как это уже сделано для интеграций (plan 032).

Результат: каждый тип коннектора декларирует свои возможности в коде, отдаёт их через API и реализует общий набор базовых классов — так что система (и UI) всегда знают, что коннектор умеет, а что нет.

---

## Зачем это делаем

### Проблема для разработчиков

Сейчас у нас два транспортных модуля — telegram и wappi. Оба делают похожие вещи (принимают сообщения, отправляют ответы, управляют конфигурацией), но каждый написан **независимо**. Нет общих базовых классов, нет единого реестра возможностей. Что это значит на практике:

- Чтобы понять, поддерживает ли telegram-module приём изображений — нужно открыть его код и прочитать хендлеры. Нигде в системе это не описано декларативно.
- Чтобы написать **новый** коннектор (например, для другого мессенджера) — нет чеклиста "что реализовать". Разработчик берёт один из существующих модулей как пример, копирует структуру, и надеется, что ничего не забыл. Нет гарантии, что новый модуль реализует всё необходимое.
- Общие вещи (модель `TransportDeliveryPayload`, логика извлечения `chat_id` из metadata, загрузка артефактов в S3) **дублируются** в каждом модуле. Сейчас они идентичны, но со временем начнут расходиться — и это будут баги, которые сложно ловить.

### Проблема для продукта и клиентов

- Админ-панель не может показать, что именно умеет подключённый коннектор. Клиент не видит "ваш Telegram-бот не поддерживает отправку картинок".
- Когда backend отправляет сообщение с вложениями (attachments) — транспортный модуль их **молча игнорирует**, потому что отправка медиа не реализована. Клиент не получает ни ошибки, ни предупреждения. Просто вложение пропадает.
- Нет формального описания возможностей коннектора — непонятно, что конкретно он умеет, пока не прочитаешь код.

### Что у нас уже хорошо работает (и что мы берём за образец)

Система **интеграций** (plan 032) уже решила аналогичную проблему для внешних сервисов (YClients, RetailCRM и т.д.):

- `Capability` enum — перечисляет все возможные скиллы интеграции
- `ProviderCatalogEntry` — self-describing метаданные провайдера с `supported_capabilities`
- `PROVIDER_CATALOG` — реестр, который фронт получает через API
- Разработчик открывает код и **сразу видит**: что умеет провайдер, чего не умеет

Для транспортных коннекторов такой системы нет. Этот план её создаёт.

### Что станет возможным после реализации

1. **Для нового коннектора:** разработчик наследует базовые классы, видит список abstract-методов, которые нужно реализовать, регистрирует capabilities — и готово. ABC подсказывает структуру, но **не ограничивает**: коннектор, который умеет только принимать сообщения — тоже имеет право на жизнь, просто его capabilities будут отражать ровно это.
2. **Для UI:** на странице каналов (connectors) у каждого коннектора видны его capabilities — что он умеет. Полная матрица "тип × все capabilities" доступна только суперпользователям как дебаг-сводка.
3. **Для backend:** перед отправкой медиа можно проверить, поддерживает ли коннектор `OUTBOUND_MEDIA` — и дать fallback или предупреждение вместо молчаливого игнорирования.
4. **Для качества кода:** общие вещи живут в одном месте (`libs/common`), а не дублируются в каждом модуле. Drift между модулями становится невозможным.

---

## Scope

**Что входит в план:**
- `ConnectorCapability` enum и `ConnectorTypeCatalogEntry` в `libs/common`
- Общие базовые модели: `TransportDeliveryPayload` и `BaseConnectorConfig` → переезжают в `libs/common`
- ABC-контракты: `BaseTransportDeliveryService`, `BaseConnectorManager`, `BaseTransportBackendClient`
- Реестр типов коннекторов и API endpoint для каталога
- Миграция telegram-module и wappi-module на новые контракты

**Что НЕ входит:**
- Добавление новых capabilities, которых ещё нет (например, отправка медиа) — это отдельные задачи
- Изменение бизнес-логики существующих модулей — это чисто структурный рефакторинг
- Система интеграций (plan 032) — не трогаем

---

## Текущее состояние

### Что уже формализовано

| Контракт | Где лежит | Статус |
|----------|-----------|--------|
| `InboundEnvelope` | `libs/common/models/inbound.py` | ✅ Общий, оба модуля используют |
| `TransportDeliveryPayload` | Дублируется в `transport/models.py` каждого модуля | ⚠️ Идентичный, но продублирован |
| `BaseSyncProvider` (ABC) | `libs/common/sync/base.py` | ✅ Правильный ABC, wappi реализует |
| `SyncMessage`, `SyncBatchRequest` | `libs/common/contracts/sync.py` | ✅ Общие Pydantic-модели |
| `AudioConversionService` | `libs/common/services/audio_converter.py` | ✅ Общий сервис |

### Чего не хватает

| Gap | Последствия |
|-----|-------------|
| Нет `ConnectorCapability` enum | Программно нельзя узнать, что коннектор поддерживает |
| Нет `ConnectorTypeCatalogEntry` | Нет self-describing метаданных для UI/API |
| Нет `BaseTransportDeliveryService` | Outbound delivery реализован независимо, поведение расходится |
| Нет `BaseConnectorConfig` | Модели конфига дублируют общие поля без единого base |
| Нет `BaseConnectorManager` | Lifecycle management дублирован без общего интерфейса |
| Нет `BaseTransportBackendClient` | Общие методы (fetch connectors, upload artifact) дублированы |
| `TransportDeliveryPayload` продублирован | Может разойтись между модулями в будущем |

### Известные расхождения между telegram и wappi

Это конкретные места, где два модуля делают одно и то же по-разному. Часть из них стандартизируется через базовые классы, часть останется platform-specific:

| Поведение | Telegram | Wappi | Можно ли стандартизировать? |
|-----------|----------|-------|---------------------------|
| Извлечение получателя | `metadata.chat_id` или `metadata.extra.chat_id` | То же + fallback на `conversation_id` | ✅ Да — общий метод `resolve_recipient()` в base class |
| Текст-заглушка для голосового | Нет | `"[Голосовое сообщение]"` | ✅ Да — константа в common |
| Retry-стратегия | Hardcoded backoff | `5.0 * attempt`, max 30s | ✅ Да — конфигурируемый retry в base |
| Определение "менеджерского" сообщения | Не реализовано | `from_where != "api"` | ❌ Нет — это особенность Wappi API |
| Модель конфига | `BotConfig` | `WappiConnectorConfig` | ✅ Да — общий base + специфичные поля |

---

## Ключевые решения

### 1. ConnectorCapability как StrEnum

```python
class ConnectorCapability(StrEnum):
    INBOUND_TEXT = "inbound_text"
    INBOUND_VOICE = "inbound_voice"
    INBOUND_AUDIO = "inbound_audio"
    INBOUND_IMAGE = "inbound_image"
    INBOUND_VIDEO = "inbound_video"
    INBOUND_DOCUMENT = "inbound_document"
    OUTBOUND_TEXT = "outbound_text"
    OUTBOUND_MEDIA = "outbound_media"
    HISTORY_SYNC = "history_sync"
```

**Почему StrEnum, а не bitmask:** строки удобно сериализуются в JSON, читаются человеком, работают в API. Тот же паттерн, что у `Capability` в интеграциях — единообразие по проекту.

**Почему эти конкретные capabilities:** это описание текущего состояния. Enum перечисляет всё, что транспортные модули **могут** делать в принципе. Если ни один модуль пока не реализует `INBOUND_IMAGE` — значение всё равно есть в enum, оно задаёт "потолок" и ориентир для развития.

**Capabilities НЕ ограничивают создание коннектора.** Коннектор может поддерживать любое подмножество — даже только `INBOUND_TEXT` без `OUTBOUND_TEXT`. Это не ошибка, а честное описание его возможностей. Система не блокирует работу коннектора из-за "неполного" набора capabilities — она просто показывает, что он умеет, а что нет.

### 2. ConnectorTypeCatalogEntry (аналог ProviderCatalogEntry из интеграций)

```python
class ConnectorTypeCatalogEntry(BaseModel):
    connector_type: str                              # "telegram", "wappi-whatsapp", "wappi-telegram"
    display_name: str                                # "Telegram Bot"
    description: str = ""
    managed: bool = True
    supported_capabilities: list[ConnectorCapability] # что этот тип реально умеет
    config_fields: list[ConfigFieldSchema] = []      # описание полей конфига для UI (ConfigFieldSchema из integrations — переиспользуем или выносим в common)
```

**Зачем это нужно:** каждый тип коннектора описывает себя сам — какие capabilities поддерживает, какие поля конфига нужны. Фронт получает это через API и строит UI динамически, без хардкода "если telegram — показать одно, если wappi — другое".

**Compound catalog key:** Hub-style транспорты (wappi) обслуживают несколько платформ с **разными** capabilities. Ключ каталога — составной: `{transport_type}-{channel_type}` (например `wappi-whatsapp`, `wappi-telegram`). Для single-platform транспортов ключ совпадает с `type` (например `telegram`). Функция `resolve_catalog_key(connector_type, channel_type)` пробует составной ключ и fallback на простой.

**Как регистрируется:** канонические записи определены статически в `libs/common/transport/registry.py`. Функция `register_connector_type()` доступна для динамических/кастомных типов.

### 3. ABC-контракты — гарантия структуры

**Ключевая идея:** у нас уже есть `BaseSyncProvider` в `libs/common/sync/base.py` — это ABC, который wappi-module реализует для sync. Он работает хорошо: определяет абстрактные методы (`fetch_dialogs`, `fetch_messages`, `transform_message`), общий фреймворк (`SyncRunner`) оперирует через этот интерфейс. Мы берём этот же паттерн и применяем к остальным контрактным поверхностям.

**Что дают ABC для нового разработчика:**
- Создал `class MyDeliveryService(BaseTransportDeliveryService)` — IDE сразу подсветит, какие методы нужно реализовать
- Не нужно читать чужой код, чтобы понять интерфейс — он описан в абстрактном классе
- Общие utility-методы (например, `resolve_recipient`) уже реализованы в base — не нужно копировать

**Что ABC НЕ делают:** не диктуют бизнес-логику и не ограничивают набор capabilities. Telegram отправляет через aiogram `bot.send_message()`, wappi — через HTTP к Wappi API. Это остаётся внутри конкретной реализации. ABC гарантируют только **сигнатуры** и **наличие** методов. Коннектор, который не реализует sync — просто не наследует `BaseSyncProvider`, и это нормально.

### 4. BaseConnectorConfig — общий фундамент конфигурации

```python
class BaseConnectorConfig(BaseModel):
    connector_id: str
    company_id: str
    channel_type: str = "telegram"
    metadata: dict[str, Any] = Field(default_factory=dict)

class TelegramBotConfig(BaseConnectorConfig):
    bot_token: SecretStr
    mode: BotMode = BotMode.AUTO
    webhook_secret: SecretStr | None = None
    webhook_path: str | None = None

class WappiConnectorConfig(BaseConnectorConfig):
    wappi_token: SecretStr
    wappi_profile_id: str
```

**Почему это важно:** сейчас `BotConfig` (telegram) и `WappiConnectorConfig` (wappi) оба имеют `connector_id`, `company_id`, `channel_type` — но это совпадение, а не контракт. Если кто-то переименует поле в одном модуле — всё сломается незаметно. `BaseConnectorConfig` делает общие поля **гарантированными**.

**Замечание:** оба модуля используют `SecretStr` для токенов и `model_validator` для нормализации `connector_id`/`company_id`. Нормализацию стоит вынести в `BaseConnectorConfig`, чтобы не дублировать в каждом наследнике.

### 5. TransportDeliveryPayload → libs/common

**Проблема:** один и тот же Pydantic-класс `TransportDeliveryPayload` определён в двух файлах:
- `apps/telegram-module/src/telegram_module/transport/models.py`
- `apps/wappi-module/src/wappi_module/transport/models.py`

Сейчас они идентичны. Но это хрупко — достаточно одному разработчику добавить поле в одном модуле и забыть про другой.

**Решение:** перенести в `libs/common/models/transport.py`. Оба модуля импортируют из common. Drift становится невозможным — один источник правды.

### 6. Runtime-валидация capabilities при старте (Phase 5)

При старте транспортного модуля — проверить, что заявленные capabilities реально реализованы:

```python
def validate_connector_module(
    entry: ConnectorTypeCatalogEntry,
    delivery_service: BaseTransportDeliveryService,
    sync_provider: BaseSyncProvider | None,
):
    if ConnectorCapability.HISTORY_SYNC in entry.supported_capabilities:
        if sync_provider is None:
            raise ConnectorModuleError("Declared HISTORY_SYNC but no BaseSyncProvider")
```

**Зачем:** это safety net. ABC гарантирует, что методы реализованы. Но если модуль заявил `HISTORY_SYNC` в capabilities, а `BaseSyncProvider` вообще не создал — ABC это не поймает. Runtime-валидация ловит такие рассинхроны при старте, а не когда пользователь нажал "синхронизировать".

---

## Phase 1: Foundation — Общие контракты в `libs/common`

**Создаёт/изменяет:**
- `libs/common/src/common/connectors.py` — `ConnectorCapability` enum, `ConnectorTypeCatalogEntry`
- `libs/common/src/common/models/transport.py` — `TransportDeliveryPayload` (перенос из модулей)
- `libs/common/src/common/transport/__init__.py` — package init
- `libs/common/src/common/transport/base_config.py` — `BaseConnectorConfig`
- `libs/common/src/common/transport/base_delivery.py` — `BaseTransportDeliveryService` (ABC)
- `libs/common/src/common/transport/base_manager.py` — `BaseConnectorManager` (ABC)
- `libs/common/src/common/transport/base_backend_client.py` — `BaseTransportBackendClient` (ABC)
- `libs/common/src/common/transport/registry.py` — `CONNECTOR_TYPE_CATALOG`, `register_connector_type()`

**Зависит от:** ничего — фундамент.

### ConnectorCapability enum

```python
class ConnectorCapability(StrEnum):
    INBOUND_TEXT = "inbound_text"
    INBOUND_VOICE = "inbound_voice"
    INBOUND_AUDIO = "inbound_audio"
    INBOUND_IMAGE = "inbound_image"
    INBOUND_VIDEO = "inbound_video"
    INBOUND_DOCUMENT = "inbound_document"
    OUTBOUND_TEXT = "outbound_text"
    OUTBOUND_MEDIA = "outbound_media"
    HISTORY_SYNC = "history_sync"
```

### BaseTransportDeliveryService (ABC)

```python
class BaseTransportDeliveryService(ABC):
    @abstractmethod
    async def handle(
        self, *, payload: TransportDeliveryPayload, headers: Mapping[str, str]
    ) -> JSONResponse: ...

    def resolve_recipient(self, payload: TransportDeliveryPayload) -> str:
        """Стандартное извлечение получателя из metadata — общая логика для всех коннекторов."""
        meta = payload.metadata or {}
        chat_id = meta.get("chat_id") or (meta.get("extra") or {}).get("chat_id")
        return str(chat_id) if chat_id else payload.conversation_id
```

`resolve_recipient` — concrete-метод. Обa модуля сейчас делают это одинаково, но каждый по-своему. Теперь это будет в одном месте.

### BaseConnectorManager (ABC)

```python
class BaseConnectorManager(ABC, Generic[TConfig]):
    @abstractmethod
    async def reload(self) -> None: ...

    @abstractmethod
    def get(self, connector_id: str) -> TConfig | None: ...

    @abstractmethod
    async def shutdown(self) -> None: ...
```

Нет `load()` — оба модуля используют `reload()` и для первоначальной загрузки, и для обновления. Это текущее поведение, и менять его не нужно.

### BaseTransportBackendClient (ABC)

```python
class BaseTransportBackendClient(ABC, Generic[TConfig]):
    @abstractmethod
    async def fetch_connectors(self) -> list[TConfig]: ...

    async def upload_artifact(
        self, file_bytes: bytes, file_type: FileType | str, company_id: int, connector_id: str
    ) -> str:
        """Загрузка артефакта в S3 через backend — общая реализация для всех модулей."""
        ...
```

**Замечания:**
- В telegram-module метод называется `fetch_bots`, а не `fetch_connectors`. При миграции — переименовать в `fetch_connectors` (поведение не меняется, только имя).
- Wappi backend client имеет дополнительные sync-specific методы (`get_thread_by_conversation`, `mark_thread_history_synced`), которых нет в telegram. Они остаются в конкретном классе `WappiBackendClient` — в ABC их не выносим, это sync-специфика.

`upload_artifact` — concrete-метод (одинаковый для всех модулей, сигнатура: `file_type: FileType | str`, `company_id: int`). `fetch_connectors` — abstract (возвращает module-specific config type).

---

## Phase 2: Миграция telegram-module

**Изменяет:**
- `apps/telegram-module/src/telegram_module/transport/models.py` — удалить `TransportDeliveryPayload`, импортировать из common
- `apps/telegram-module/src/telegram_module/transport/service.py` — наследовать `BaseTransportDeliveryService`
- `apps/telegram-module/src/telegram_module/bots/models.py` — `BotConfig` наследует `BaseConnectorConfig`
- `apps/telegram-module/src/telegram_module/bots/manager.py` — `BotManager` наследует `BaseConnectorManager[BotConfig]`
- `apps/telegram-module/src/telegram_module/services/backend.py` — наследовать `BaseTransportBackendClient[BotConfig]`
- `apps/telegram-module/src/telegram_module/__init__.py` — регистрация `ConnectorTypeCatalogEntry`

**Зависит от:** Phase 1 — `BaseTransportDeliveryService`, `BaseConnectorConfig`, `BaseConnectorManager`, `BaseTransportBackendClient`, `TransportDeliveryPayload`, `ConnectorTypeCatalogEntry`, `register_connector_type()`.

**Важно:** это **рефакторинг, не изменение поведения**. Все тесты должны проходить до и после. Мы меняем структуру (наследование от базовых классов), а не логику.

Telegram capabilities:

```python
register_connector_type(ConnectorTypeCatalogEntry(
    connector_type="telegram",
    display_name="Telegram Bot",
    description="Telegram Bot API via aiogram",
    managed=True,
    supported_capabilities=[
        ConnectorCapability.INBOUND_TEXT,
        ConnectorCapability.INBOUND_VOICE,
        ConnectorCapability.INBOUND_AUDIO,
        ConnectorCapability.OUTBOUND_TEXT,
    ],
))
```

Обрати внимание: `INBOUND_IMAGE`, `INBOUND_VIDEO`, `INBOUND_DOCUMENT` **нет** в списке — потому что telegram-module их пока не обрабатывает. Это честное описание текущего состояния.

---

## Phase 3: Миграция wappi-module

**Изменяет:**
- `apps/wappi-module/src/wappi_module/transport/models.py` — удалить `TransportDeliveryPayload`, импортировать из common
- `apps/wappi-module/src/wappi_module/transport/service.py` — наследовать `BaseTransportDeliveryService`
- `apps/wappi-module/src/wappi_module/connectors/models.py` — `WappiConnectorConfig` наследует `BaseConnectorConfig`
- `apps/wappi-module/src/wappi_module/connectors/manager.py` — `ConnectorManager` наследует `BaseConnectorManager[WappiConnectorConfig]`
- `apps/wappi-module/src/wappi_module/services/backend.py` — наследовать `BaseTransportBackendClient[WappiConnectorConfig]`
- `apps/wappi-module/src/wappi_module/__init__.py` — регистрация `ConnectorTypeCatalogEntry`

**Зависит от:** Phase 1 — те же контракты, что и для Phase 2.

**Важно:** аналогично Phase 2 — чистый рефакторинг, без изменения поведения.

Wappi capabilities (два отдельных entry — hub-style транспорт):

```python
# libs/common/transport/registry.py — канонический источник
CONNECTOR_TYPE_CATALOG = {
    ...
    "wappi-whatsapp": ConnectorTypeCatalogEntry(
        connector_type="wappi-whatsapp",
        display_name="WhatsApp (Wappi)",
        description="WhatsApp через Wappi API",
        supported_capabilities=[...INBOUND_TEXT, INBOUND_VOICE, INBOUND_AUDIO, OUTBOUND_TEXT, HISTORY_SYNC],
    ),
    "wappi-telegram": ConnectorTypeCatalogEntry(
        connector_type="wappi-telegram",
        display_name="Telegram Personal (Wappi)",
        description="Telegram user-proxy через Wappi API",
        supported_capabilities=[...INBOUND_TEXT, INBOUND_VOICE, INBOUND_AUDIO, OUTBOUND_TEXT, HISTORY_SYNC],
    ),
}
```

Каждый вариант Wappi может иметь **разные** capabilities — например, следующий wappi-hub коннектор может поддерживать `OUTBOUND_MEDIA`, а предыдущие нет. Compound ключ (`wappi-whatsapp` vs `wappi-telegram`) гарантирует что каждый вариант описан независимо.

---

## Phase 4: Backend — Catalog API и Feature Gating

**Изменяет:**
- `apps/backend/src/backend/modules/transport/routers.py` — добавить `GET /api/v1/transport/catalog` (текущий router prefix: `/transport/connectors`, все routes за `require_service_api_key`)
- `apps/backend/src/backend/modules/transport/schemas.py` — response-схемы каталога
- `apps/backend/src/backend/modules/transport/service.py` (`ConnectorsService`) — методы для каталога

**Зависит от:** Phase 1 — `CONNECTOR_TYPE_CATALOG`, `ConnectorTypeCatalogEntry`.

### Catalog endpoint

```
GET /api/v1/transport/catalog
→ [
    {
      "connector_type": "telegram",
      "display_name": "Telegram Bot",
      "supported_capabilities": ["inbound_text", "inbound_voice", "inbound_audio", "outbound_text"],
      "config_fields": [...]
    },
    {
      "connector_type": "wappi",
      "display_name": "Wappi (WhatsApp/Telegram)",
      "supported_capabilities": ["inbound_text", "inbound_voice", "inbound_audio", "outbound_text", "history_sync"],
      "config_fields": [...]
    }
  ]
```

Фронт получает этот каталог и может:
- На странице каналов — показать capabilities конкретного коннектора (что он умеет)
- При создании коннектора — показать, какие возможности будут доступны для этого типа
- Полная сводка-матрица "все типы × все capabilities" — доступна только суперпользователям как дебаг-инструмент

### Feature gating (в TransportClient)

При отправке outbound — проверить capabilities:

```python
async def deliver(self, *, connector_id, connector_type, payload):
    catalog = CONNECTOR_TYPE_CATALOG.get(connector_type)
    if payload.get("attachments") and ConnectorCapability.OUTBOUND_MEDIA not in catalog.supported_capabilities:
        log.warning("connector.capability.missing", ...)
        # strip attachments or raise — решение по политике
```

Вместо молчаливого игнорирования — явная реакция.

---

## Phase 5: Runtime-валидация при старте

**Создаёт/изменяет:**
- `libs/common/src/common/transport/validation.py` — `validate_connector_module()`
- `apps/telegram-module/src/telegram_module/main.py` (lifespan) — вызов валидации при старте
- `apps/wappi-module/src/wappi_module/main.py` (lifespan) — вызов валидации при старте

**Зависит от:** Phase 1 (контракты) + Phase 2 и 3 (реализации).

При старте модуля проверяет, что заявленные capabilities соответствуют реальным реализациям. Это safety net от рассинхрона "заявил `HISTORY_SYNC` но `BaseSyncProvider` не создал". Ловит ошибку **при деплое**, а не когда пользователь нажал кнопку "синхронизировать".

Валидация **не блокирует** запуск коннектора с "неполным" набором capabilities. Она ловит только противоречия: capability заявлена, но реализация отсутствует.

---

## Risks / Open Questions

1. **`ConfigFieldSchema` живёт в backend** — сейчас `ConfigFieldSchema` определён в `apps/backend/src/backend/modules/integrations/schemas.py`. Если `ConnectorTypeCatalogEntry` в `libs/common` использует его — нужно либо вынести `ConfigFieldSchema` в `libs/common`, либо определить аналогичную схему в `connectors.py`. Рекомендация: вынести в common, чтобы и интеграции, и коннекторы использовали один тип.

2. **Гранулярность capabilities** — начинаем с крупных (`OUTBOUND_MEDIA` вместо отдельных `OUTBOUND_IMAGE`, `OUTBOUND_VIDEO`, `OUTBOUND_DOCUMENT`). Дробим позже, если появится реальная необходимость различать.

3. **Обратная совместимость** — миграция на ABC это рефакторинг. Тесты должны проходить идентично до и после. Конкретные переименования: telegram `fetch_bots` → `fetch_connectors`. Поведение не меняется.

4. **`BaseTransportBackendClient` shared `upload_artifact`** — оба модуля сейчас реализуют upload независимо с небольшими отличиями (retry-логика, имя файла). Консолидация = выбор одной стратегии. Рекомендация: взять более robust-вариант (retry-логика из wappi).

5. **Где регистрировать каталог** — ✅ Решено: каталог коннекторов определён статически в `libs/common/transport/registry.py`. Это единый источник правды для всех процессов (backend, transports). Common уже содержит `InboundEnvelope`, `TransportDeliveryPayload` и другие транспортные модели — каталог логично продолжает этот паттерн. Каталог — слой метаданных (строки и enum-значения, не логика); типы коннекторов добавляются редко, отличия ловятся быстро. `register_connector_type()` остаётся для кастомных/динамических типов.

6. **Compound catalog key для hub-style транспортов** — ✅ Решено: wappi обслуживает несколько платформ (WhatsApp, Telegram Personal) с потенциально разными capabilities. Ключ каталога — составной `{type}-{channel_type}` (например `wappi-whatsapp`). Функция `resolve_catalog_key(connector_type, channel_type)` в registry.py пробует compound → fallback на простой ключ. Backend `deliver()` принимает `channel_type` для корректного lookup.

### Вне scope

- **`custom` коннекторы** — на данный момент не существуют и не планируются к реализации в ближайшее время. Этот план их не затрагивает. Когда дойдём — будет отдельный план.

---

## Rollback Strategy

Каждая фаза откатывается независимо:
- Phase 1 добавляет новые файлы, не трогая существующий код
- Phase 2-3 — рефакторинг с идентичным внешним поведением
- Phase 4 — новый endpoint, не ломает существующие
- Phase 5 — валидация при старте, откатывается удалением вызова из lifespan
