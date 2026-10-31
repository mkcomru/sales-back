# План: Импорт истории диалогов при подключении коннекторов

## Цель

Реализовать автоматический импорт истории диалогов при подключении коннекторов с соблюдением rate limits провайдера, идемпотентности и правильной обработки предыстории для ИИ. Архитектура должна быть абстрактной: бэкенд не знает о провайдерах, вся логика работы с провайдерами живет в коннекторах.

## Архитектурные принципы

1. **Разделение ответственностей**:
   - Бэкенд: абстрактная обработка синка, сохранение данных, управление статусами
   - Коннекторы (wappi-module, telegram-module): логика работы с провайдерами, подготовка батчей данных

2. **Абстракция**:
   - Бэкенд не знает о Wappi API, Telegram API и т.д.
   - Бэкенд работает только с коннекторами через стандартизированный API
   - Коннекторы сами определяют, поддерживают ли они синк (через наличие endpoint)

3. **Изоляция**:
   - Вся логика провайдеров изолирована в коннекторах
   - Легко добавлять новые коннекторы без изменения бэкенда

## Контекст

- При подключении коннектора нужно подтянуть всю историю из source-of-truth
- Первичный импорт должен быть быстрым для оперативного минимума (последние 20 диалогов)
- Остальная история догружается постепенно с rate limiting
- ИИ не должен отвечать в тредах с предысторией и во время догонки
- Не должно быть дублей сообщений (идемпотентность через message_id провайдера)

## Текущее состояние

### Существующая реализация
- `apps/wappi-module/src/wappi_module/api/routes.py:172` - есть endpoint `/sync/{connector_id}`, но он синхронный и не интегрирован с бэкендом
- `apps/backend/src/backend/modules/transport/sync_service.py` - содержит логику синхронизации, которую нужно перенести в wappi-module
- `apps/backend/src/backend/modules/transport/wappi_client.py` - клиент Wappi API в бэкенде, нужно перенести в wappi-module
- `InboundEnvelope.is_historical` - флаг для исторических сообщений
- `Thread.assistant_active` - управление активностью ИИ
- `ChatMessage.provider_message_id` - уникальный идентификатор от провайдера

## Этапы реализации

### Этап 1: Расширение модели Connector для отслеживания статуса синхронизации

**Файлы:**
- `apps/backend/src/backend/modules/transport/models.py`
- `apps/backend/migrations/models/XXX_YYYYMMDDHHMMSS_update.py`
- `apps/backend/src/backend/modules/transport/schemas.py`

**Задачи:**
1. Добавить поля в модель `Connector`:
   ```python
   sync_status: CharEnumField(SyncStatus, max_length=30, default=SyncStatus.IDLE)
   sync_started_at: DatetimeField(null=True)
   sync_completed_at: DatetimeField(null=True)
   sync_progress: JSONField(default=dict)  # {total_chats: int, processed_chats: int, total_messages: int, processed_messages: int}
   ```

2. Создать enum `SyncStatus`:
   ```python
   class SyncStatus(str, Enum):
       IDLE = "idle"           # Не синхронизируется
       INITIAL = "initial"     # Первичный импорт (быстрый минимум)
       BACKFILL = "backfill"   # Догонка остальной истории
       CATCHUP = "catchup"     # Догонка после обрыва
       COMPLETED = "completed" # Синхронизация завершена
       FAILED = "failed"       # Ошибка синхронизации
   ```

3. Создать миграцию Aerich

4. Обновить схемы для API

**Критерии готовности:**
- [ ] Модель обновлена
- [ ] Миграция создана и применена
- [ ] Enum добавлен в схемы

---

### Этап 2: Добавление идемпотентности через message_id провайдера

**Файлы:**
- `apps/backend/src/backend/modules/chat/models.py`
- `apps/backend/src/backend/modules/chat/repository.py`
- `apps/backend/src/backend/modules/chat/service.py`
- `apps/backend/migrations/models/XXX_YYYYMMDDHHMMSS_update.py`

**Задачи:**
1. Добавить поле `provider_message_id` в модель `ChatMessage` (если еще не добавлено)

2. Добавить уникальный индекс на `(thread_id, provider_message_id)` для предотвращения дублей

3. Модифицировать `ChatMessagesRepository.create_message()`:
   - Принимать `provider_message_id: str | None = None`
   - Перед созданием проверять существование по `provider_message_id` в рамках thread
   - Если существует - возвращать существующее сообщение (идемпотентность)

4. Обновить `ChatService.create_message()` - пробросить `provider_message_id`

5. Обновить `InboundEnvelope` (если нужно):
   - Убедиться, что `message_id` передается корректно

**Критерии готовности:**
- [ ] Модель обновлена с индексом
- [ ] Репозиторий проверяет дубли перед созданием
- [ ] Миграция создана
- [ ] Тесты на идемпотентность

---

### Этап 3: Абстрактный API синхронизации в бэкенде

**Файлы:**
- `apps/backend/src/backend/modules/transport/sync_service.py` (переписать - убрать логику провайдера)
- `apps/backend/src/backend/modules/transport/routers.py`

**Задачи:**
1. Переписать `HistorySyncService` в бэкенде - оставить только абстрактную логику:
   ```python
   class HistorySyncService:
       async def start_sync(connector_id: str, sync_type: SyncType, since: datetime | None = None) -> None
       async def get_sync_status(connector_id: str) -> SyncStatus
       async def cancel_sync(connector_id: str) -> None
   ```

2. Логика `start_sync`:
   - Получить коннектор по `connector_id`
   - Проверить `connector.type` - если не поддерживает синк (например, `type != "wappi"`), пропустить
   - Получить `transport_endpoint` из конфигурации коннектора
   - Вызвать `POST {transport_endpoint}/sync/start` с параметрами:
     - `connector_id`: идентификатор коннектора
     - `sync_type`: initial, backfill, catchup
     - `since`: для catchup (опционально)
   - Если коннектор вернул 404 - значит не поддерживает синк, установить статус и завершить
   - Если успешно - обновить `sync_status` коннектора в БД

3. Логика `get_sync_status`:
   - Получить коннектор по `connector_id`
   - Получить `transport_endpoint` из конфигурации
   - Вызвать `GET {transport_endpoint}/sync/status?connector_id={connector_id}`
   - Получить статус от коннектора
   - Обновить локальный статус в БД

4. Логика `cancel_sync`:
   - Получить коннектор по `connector_id`
   - Получить `transport_endpoint` из конфигурации
   - Вызвать `POST {transport_endpoint}/sync/cancel` с `connector_id`
   - Обновить статус на IDLE в БД

5. Удалить из бэкенда:
   - Всю логику работы с Wappi API
   - `WappiApiClient` (должен быть в wappi-module)
   - Логику формирования `InboundEnvelope` для синка
   - Логику обработки чатов и сообщений

6. Обработка батчей данных от коннектора:
   - Коннектор отправляет батчи на `POST {backend_url}/api/v1/messages/inbound` с `is_historical=True`
   - Бэкенд обрабатывает как обычные входящие сообщения
   - Идемпотентность обеспечивается через `provider_message_id`

**Критерии готовности:**
- [ ] Сервис переписан - только абстрактная логика вызова коннекторов
- [ ] Интеграция с коннекторами через HTTP
- [ ] Обработка 404 (коннектор не поддерживает синк)
- [ ] Обновление статусов в БД
- [ ] Удалена вся логика работы с Wappi API из бэкенда

---

### Этап 4: API endpoints для управления синхронизацией в бэкенде

**Файлы:**
- `apps/backend/src/backend/modules/transport/routers.py`
- `apps/backend/src/backend/modules/transport/schemas.py`

**Задачи:**
1. Добавить endpoint для запуска синхронизации:
   ```python
   @router.post("/connectors/{connector_id}/sync/start")
   async def start_sync(
       connector_id: str,
       sync_type: SyncTypeEnum = Query(...),
       since: datetime | None = Query(None),
   ) -> SyncJobResponse
   ```

2. Добавить endpoint для статуса:
   ```python
   @router.get("/connectors/{connector_id}/sync/status")
   async def get_sync_status(connector_id: str) -> SyncStatusResponse
   ```

3. Добавить endpoint для отмены:
   ```python
   @router.post("/connectors/{connector_id}/sync/cancel")
   async def cancel_sync(connector_id: str) -> dict
   ```

4. Обновить схему `ConnectorResponse` - включить поля синхронизации

**Критерии готовности:**
- [ ] Endpoints созданы и задокументированы
- [ ] Схемы ответов определены
- [ ] Интеграция с сервисом

---

### Этап 5: Реализация синхронизации в wappi-module

**Файлы:**
- `apps/wappi-module/src/wappi_module/api/routes.py`
- `apps/wappi-module/src/wappi_module/services/sync_service.py` (новый - перенести логику из бэкенда)
- `apps/wappi-module/src/wappi_module/services/wappi_api.py` (обновить или создать клиент)

**Задачи:**
1. Перенести `WappiApiClient` из бэкенда в wappi-module (если еще не существует):
   - Методы: `get_chats_list()`, `get_chat_messages()`
   - Обработка ошибок Wappi API

2. Создать `WappiSyncService` в wappi-module:
   ```python
   class WappiSyncService:
       async def start_initial_sync(connector_id: str) -> None
       async def start_backfill_sync(connector_id: str) -> None
       async def start_catchup_sync(connector_id: str, since: datetime) -> None
       async def get_sync_status(connector_id: str) -> SyncStatus
       async def cancel_sync(connector_id: str) -> None
   ```

3. Логика синхронизации (перенести из бэкенда):
   - **Initial sync** (быстрый минимум):
     - Получить последние 20 диалогов через Wappi API
     - Обработать их с минимальными задержками
     - Для каждого чата получить сообщения (с пагинацией если нужно)
     - Сформировать `InboundEnvelope` для каждого сообщения
     - Отправить батчи на бэкенд через `POST {backend_url}/api/v1/messages/inbound`
   - **Backfill sync** (фоновая догонка):
     - Получить все остальные диалоги
     - Обрабатывать батчами с rate limiting (например, 10 чатов в минуту)
     - Использовать пагинацию для больших чатов
     - Отправлять батчи на бэкенд
   - **Catchup sync** (после обрыва):
     - Получить сообщения с определенной даты (`since`)
     - Обрабатывать с умеренным rate limiting
     - Отправлять батчи на бэкенд

4. Rate limiting:
   - Конфигурируемые параметры:
     - `initial_sync_rate`: чатов/сек для initial (например, 2/сек)
     - `backfill_sync_rate`: чатов/сек для backfill (например, 0.1/сек = 6/мин)
     - `messages_per_chat_batch`: количество сообщений за запрос (100 - лимит Wappi)
     - `delay_between_batches`: задержка между батчами (например, 1 сек)

5. Интеграция с Wappi API:
   - Использовать `WappiApiClient`
   - Обрабатывать ошибки (429, 500) с экспоненциальным backoff
   - Retry logic для временных ошибок

6. Формирование `InboundEnvelope`:
   - Для каждого сообщения создавать envelope с:
     - `is_historical=True`
     - `message_id` из провайдера (для идемпотентности)
     - Правильным `role` (USER/MANAGER на основе `fromMe`)
     - `conversation_id`, `user_id`, `text`, `ts` и т.д.
   - Отправлять на `POST {backend_url}/api/v1/messages/inbound` через HTTP клиент
   - Использовать `X-Service-Key` и `X-Connector-Id` для авторизации

7. Отслеживание прогресса:
   - Хранить прогресс локально (в памяти или Redis)
   - Отдавать статус через endpoint
   - Обновлять статус синхронизации

8. Пагинация для больших чатов:
   - Wappi API возвращает максимум 100 сообщений за запрос
   - Использовать параметры `offset` и `date` для получения следующих батчей
   - Обрабатывать от старых к новым (`order=asc`)
   - Сохранять прогресс для возможности продолжения

9. Endpoints в wappi-module:
   ```python
   @router.post("/sync/start")
   async def start_sync(
       connector_id: str = Query(...),
       sync_type: SyncTypeEnum = Query(...),
       since: datetime | None = Query(None),
   ) -> dict
   
   @router.get("/sync/status")
   async def get_sync_status(connector_id: str = Query(...)) -> SyncStatusResponse
   
   @router.post("/sync/cancel")
   async def cancel_sync(connector_id: str = Query(...)) -> dict
   ```

10. Обработка ошибок:
    - `429 Too Many Requests`: экспоненциальный backoff, увеличить задержки
    - `500 Internal Server Error`: retry с backoff
    - `401/403 Unauthorized`: остановить синхронизацию, установить `sync_status=FAILED`
    - `404 Not Found`: пропустить чат, логировать
    - Таймауты: retry с backoff

**Критерии готовности:**
- [ ] Сервис создан с методами start/status/cancel
- [ ] Реализован initial sync (быстрый минимум)
- [ ] Реализован backfill sync с rate limiting
- [ ] Реализован catchup sync
- [ ] Обработка ошибок с retry logic
- [ ] Пагинация для больших чатов
- [ ] Endpoints для управления синком
- [ ] Отправка батчей на бэкенд
- [ ] Вся логика работы с Wappi API изолирована в wappi-module

---

### Этап 6: Автоматический запуск синхронизации при подключении

**Файлы:**
- `apps/backend/src/backend/modules/transport/service.py`

**Задачи:**
1. В `ConnectorsService.create_connector()`:
   - После создания коннектора проверить `connector.type`
   - Если `type == "wappi"` (или другой поддерживающий синк):
     - Запускать `initial_sync` в фоне через `HistorySyncService.start_sync()`
     - Не блокировать ответ на создание коннектора
   - Если коннектор не поддерживает синк (404) - просто логировать

2. В `ConnectorsService.update_connector()`:
   - Если коннектор переключен с `enabled=False` на `enabled=True`:
     - Проверить `connector.type` - если поддерживает синк
     - Проверить, была ли синхронизация (`sync_completed_at is None`)
     - Если нет - запустить `initial_sync`

**Критерии готовности:**
- [ ] Автозапуск при создании коннектора (только для поддерживающих типов)
- [ ] Автозапуск при включении коннектора
- [ ] Не блокирует основной поток
- [ ] Корректная обработка коннекторов без поддержки синка

---

### Этап 7: Управление assistant_active на основе предыстории

**Файлы:**
- `apps/backend/src/backend/modules/chat/service.py`
- `apps/backend/src/backend/modules/chat/repository.py`

**Задачи:**
1. Модифицировать `ChatService.get_or_create_thread()`:
   - При создании нового thread из исторического сообщения:
     - Устанавливать `assistant_active=False`
     - Добавлять в `metadata`: `{"has_history": True, "history_synced_at": datetime}`

2. Модифицировать `ChatService.create_message()`:
   - Если сообщение историческое (`is_historical=True`) и thread только что создан:
     - Устанавливать `assistant_active=False`
     - Логировать причину

3. Обновить логику в `apps/backend/src/backend/modules/messages/routers.py`:
   - После сохранения исторического сообщения проверять `thread.assistant_active`
   - Если `False` - логировать, что ИИ отключен из-за предыстории

**Критерии готовности:**
- [ ] Thread с предысторией автоматически получает `assistant_active=False`
- [ ] Логирование причин отключения ИИ

---

### Этап 8: Пауза ИИ во время синхронизации

**Файлы:**
- `apps/backend/src/backend/modules/messages/routers.py`

**Задачи:**
1. В `inbound_message()` добавить проверку статуса коннектора:
   - Если `connector.sync_status in (INITIAL, BACKFILL, CATCHUP)`:
     - Не форвардить в Sales Agent (даже если `assistant_active=True`)
     - Логировать: "AI paused due to sync in progress"

2. Добавить проверку в `ChatService`:
   - Метод `can_process_with_ai(thread_id: str, connector_id: str) -> bool`:
     - Проверяет `thread.assistant_active`
     - Проверяет `connector.sync_status`
     - Возвращает `True` только если оба условия OK

3. После завершения синхронизации:
   - wappi-module обновляет свой статус
   - Бэкенд получает обновление через `get_sync_status`
   - ИИ возобновляет работу

**Критерии готовности:**
- [ ] ИИ не отвечает во время синхронизации
- [ ] ИИ возобновляет работу после завершения синхронизации
- [ ] Логирование причин паузы

---

### Этап 9: Тестирование

**Файлы:**
- `apps/backend/tests/domains/transport/test_sync_service.py` (переписать - убрать логику провайдера)
- `apps/backend/tests/domains/transport/test_sync_routers.py`
- `apps/backend/tests/domains/chat/test_idempotency.py`
- `apps/wappi-module/tests/test_sync_service.py` (новый)

**Задачи:**
1. Unit тесты для `HistorySyncService` в бэкенде:
   - Тест вызова коннектора для синка
   - Тест обработки 404 (коннектор не поддерживает синк)
   - Тест обновления статусов
   - Тест проверки типа коннектора

2. Unit тесты для `WappiSyncService` в wappi-module:
   - Тест initial sync (быстрый минимум)
   - Тест backfill sync с rate limiting
   - Тест catchup sync
   - Тест обработки ошибок и retry
   - Тест пагинации
   - Тест формирования и отправки батчей

3. Unit тесты для идемпотентности:
   - Создание сообщения с одинаковым `provider_message_id` дважды
   - Проверка, что дубль не создается

4. Integration тесты:
   - Полный цикл: создание коннектора → автоматический запуск sync → проверка результатов
   - Проверка `assistant_active=False` для threads с предысторией
   - Проверка паузы ИИ во время синхронизации
   - Проверка отправки батчей от коннектора в бэкенд
   - Проверка вызова бэкендом wappi-module

5. E2E тесты (опционально):
   - Подключение реального коннектора
   - Проверка импорта истории
   - Проверка отсутствия дублей

**Критерии готовности:**
- [ ] Unit тесты покрывают основную логику
- [ ] Integration тесты проверяют ключевые сценарии
- [ ] Все тесты проходят

---

### Этап 10: Документация и мониторинг

**Файлы:**
- `docs/features/history-sync.md` (новый)
- `apps/backend/README.md` (обновить)
- `apps/wappi-module/README.md` (обновить)

**Задачи:**
1. Документация API:
   - Описание endpoints синхронизации в бэкенде
   - Описание endpoints синхронизации в wappi-module
   - Примеры запросов/ответов
   - Описание статусов синхронизации

2. Документация процесса:
   - Как работает автоматический импорт
   - Как работает догонка
   - Как управлять синхронизацией вручную
   - Архитектура: разделение ответственностей между бэкендом и коннекторами

3. Мониторинг:
   - Метрики: количество синхронизированных чатов/сообщений
   - Метрики: время синхронизации
   - Алерты на ошибки синхронизации

4. Логирование:
   - Структурированные логи с контекстом
   - Уровни: INFO для прогресса, WARNING для ошибок, ERROR для критических

**Критерии готовности:**
- [ ] Документация написана
- [ ] Метрики настроены
- [ ] Логирование структурировано

---

## Порядок выполнения

1. **Этап 1** - Расширение модели (фундамент)
2. **Этап 2** - Идемпотентность (критично для предотвращения дублей)
3. **Этап 3** - Абстрактный API синхронизации в бэкенде (упростить, убрать логику провайдера)
4. **Этап 4** - API endpoints в бэкенде (публичный интерфейс)
5. **Этап 5** - Реализация синхронизации в wappi-module (перенести всю логику из бэкенда)
6. **Этап 6** - Автозапуск (интеграция, проверка типа коннектора)
7. **Этап 7** - Управление assistant_active (бизнес-логика)
8. **Этап 8** - Пауза ИИ (бизнес-логика)
9. **Этап 9** - Тестирование (качество)
10. **Этап 10** - Документация (поддержка)

## Риски и митигация

### Риск 1: Превышение rate limits провайдера
**Митигация:**
- Консервативные настройки rate limiting по умолчанию в коннекторах
- Мониторинг ошибок 429
- Автоматическое увеличение задержек при получении 429

### Риск 2: Долгая синхронизация больших аккаунтов
**Митигация:**
- Приоритизация: сначала быстрый минимум (20 диалогов)
- Фоновая догонка не блокирует работу
- Прогресс виден в UI

### Риск 3: Потеря сообщений при обрыве
**Митигация:**
- Отслеживание последнего синхронизированного сообщения в коннекторах
- Автоматический catchup при восстановлении
- Gap detection

### Риск 4: Дубли сообщений
**Митигация:**
- Уникальный индекс на `(thread_id, provider_message_id)` в бэкенде
- Проверка перед созданием
- Тесты на идемпотентность

### Риск 5: Несовместимость API коннекторов
**Митигация:**
- Стандартизированный интерфейс синка
- Обработка 404 для коннекторов без поддержки синка
- Документация интерфейса

### Риск 6: Миграция логики из бэкенда в wappi-module
**Митигация:**
- Поэтапная миграция
- Сохранение тестов
- Тщательное тестирование после миграции

## Критерии приемки (DoD)

- [ ] После подключения коннектора автоматически запускается синхронизация (только для поддерживающих типов)
- [ ] Последние 20 диалогов появляются в UI быстро (< 1 минуты)
- [ ] Остальная история догружается в фоне с соблюдением rate limits
- [ ] Нет дублей сообщений при повторных запусках синхронизации
- [ ] Threads с предысторией имеют `assistant_active=False`
- [ ] ИИ не отвечает во время синхронизации
- [ ] ИИ возобновляет работу после завершения initial sync
- [ ] Бэкенд не знает о провайдерах, только о коннекторах
- [ ] Коннекторы изолированы, легко добавлять новые
- [ ] Вся логика работы с Wappi API находится в wappi-module
- [ ] Бэкенд вызывает коннекторы только если `type` поддерживает синк
- [ ] Все ошибки обрабатываются с retry logic
- [ ] Прогресс синхронизации виден через API
- [ ] Документация обновлена
