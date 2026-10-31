# 034: WebSocket E2E — Ticket-Based Auth + Company-Level WS

**Linear:** [DEVS-126](https://linear.app/pulsefirst/issue/DEVS-126/sdelat-vebsoket-soobshenij-e2e)
**Supersedes:** Plan 025 (WebSocket Frontend Integration)

---

## Зачем это делаем

Сейчас фронтенд вынужден поллить `GET /chat/threads` каждые ~10 секунд, чтобы увидеть новые сообщения, изменения unread count, новые треды и смену состояний. Это:

- **Задержка для оператора** — до 10 секунд пока менеджер увидит новое сообщение клиента в списке тредов
- **Лишняя нагрузка** — каждый открытый таб = запрос каждые 10 секунд, большинство из которых возвращают те же данные
- **Плохой UX** — нет typing-индикаторов, нет мгновенных уведомлений, интерфейс "дёргается" при обновлении списка

После реализации:
- Мгновенные обновления списка тредов и сообщений (< 100ms)
- Один WS на вкладку вместо постоянных HTTP-запросов
- Безопасная авторизация без утечки JWT в логи
- Фундамент для typing-индикаторов, online-статусов, push-уведомлений

---

## Текущее состояние

### Что есть
- Per-thread WS: `GET /companies/{company_id}/threads/{thread_id}/ws` (routers.py:798)
- `WebSocketManager` — in-memory, broadcast по `thread_id` (websocket.py)
- JWT auth: header или `?token=` query param
- 11 точек broadcast в routers.py (MESSAGE, CONTROL, NOTE, THREAD_UPDATED)
- Redis async client (для event streams, не для general storage)

### Что нет
- Company-level WS — нет push-уведомлений для списка тредов
- Ticket-based auth — JWT летит в URL (утечка через логи)
- Механизма subscribe/unsubscribe на конкретные треды

---

## Архитектура решения

### Один WS на компанию с подписками

```
wss://host/api/v1/ws/companies/{company_id}?ticket=<uuid>
```

Клиент получает:
- **Всегда:** thread-list события (новый тред, обновление превью/unread/state)
- **По подписке:** полные MESSAGE/CONTROL/NOTE события для конкретного треда

Клиент отправляет:
- `{"type": "subscribe", "thread_id": "..."}` — подписка на тред
- `{"type": "unsubscribe", "thread_id": "..."}` — отписка
- `{"type": "message", "thread_id": "...", "payload": {...}}` — отправка сообщения
- `{"type": "control", "thread_id": "...", "payload": {...}}` — control action

### Ticket-Based Auth

```
1. POST /api/v1/auth/ws-ticket  (Bearer JWT)
   → { "ticket": "uuid", "expires_in": 30 }

2. new WebSocket("wss://host/api/v1/ws/companies/{company_id}?ticket=<uuid>")
   → Бэк: Redis GET + DEL ticket → accept / reject
```

---

## План реализации

### Шаг 1: Redis KV-клиент для тикетов

**Контекст:** Redis уже есть в инфре (Redis 7 Alpine, `REDIS__URL`). Используется только для Event Bus (Redis Streams через `RedisStreamsBroker` в `libs/common`). Существующий брокер работает в binary mode и заточен под Streams — для KV-операций нужен отдельный лёгкий клиент к тому же инстансу.

**Файлы:**
- `apps/backend/src/backend/services/redis.py` — новый файл, синглтон Redis KV-клиента
- `apps/backend/src/backend/main.py` — инициализация в lifespan

**Что делаем:**
- Создать `RedisKVClient` класс-обёртку с методами `set_with_ttl(key, value, ttl)`, `get_and_delete(key)` (атомарный GETDEL)
- Подключается к тому же `settings.redis.url` но с `decode_responses=True`
- Инициализировать в `lifespan` рядом с event publisher
- Module-level singleton (по аналогии с `BackendEventPublisher`)

**Зависимости:** `redis.asyncio` (уже в зависимостях через common), тот же Redis инстанс

---

### Шаг 2: Эндпоинт выдачи тикетов

**Файлы:**
- `apps/backend/src/backend/modules/auth/routers.py` — новый эндпоинт
- `apps/backend/src/backend/modules/auth/schemas.py` — схемы запроса/ответа

**Эндпоинт:** `POST /api/v1/auth/ws-ticket`

**Логика:**
```python
@router.post("/ws-ticket")
async def create_ws_ticket(user: CurrentUserDep, company_user: CompanyViewerDep):
    ticket_id = str(uuid4())
    payload = {"user_id": user.id, "company_id": company_user.company_id, "role": company_user.role}
    await redis.set_with_ttl(f"ws:ticket:{ticket_id}", json.dumps(payload), ttl=30)
    return {"ticket": ticket_id, "expires_in": 30}
```

**Схемы:**
```python
class WsTicketResponse(BaseModel):
    ticket: str
    expires_in: int
```

---

### Шаг 3: Company-Level WebSocketManager

**Файлы:**
- `apps/backend/src/backend/modules/chat/websocket.py` — рефакторинг

**Что делаем:**

Расширить `WebSocketManager` двумя уровнями:

```python
class WebSocketManager:
    # Company-level: все соединения компании
    company_connections: dict[int, set[WebSocket]]
    # Thread-level: подписки на конкретные треды
    thread_subscriptions: dict[str, set[WebSocket]]
    # Обратный маппинг: ws → (company_id, set[thread_id])
    connection_meta: dict[WebSocket, ConnectionMeta]
```

**Новые методы:**
- `connect_company(ws, company_id, user_id, role)` — регистрация company-level
- `disconnect_company(ws)` — полная очистка
- `subscribe_thread(ws, thread_id)` — подписка на тред (с проверкой доступа)
- `unsubscribe_thread(ws, thread_id)` — отписка
- `broadcast_to_company(company_id, event)` — thread-list события всем в компании
- `broadcast_to_thread(thread_id, event)` — детальные события подписчикам треда (уже есть, адаптировать)

---

### Шаг 4: Новый WS-эндпоинт (company-level)

**Файлы:**
- `apps/backend/src/backend/modules/chat/routers.py` — новый эндпоинт

**Эндпоинт:** `WS /api/v1/ws/companies/{company_id}`

**Логика подключения:**
1. Извлечь `ticket` из query param
2. `redis.get_and_delete(f"ws:ticket:{ticket}")` — атомарно забрать и удалить
3. Если нет или expired → `close(1008)`
4. Проверить `company_id` из тикета совпадает с URL
5. `websocket_manager.connect_company(ws, company_id, user_id, role)`
6. Отправить ACK

**Цикл обработки сообщений:**
```python
while True:
    data = await websocket.receive_json()
    match data["type"]:
        case "subscribe":
            # Проверить доступ к треду (role-based)
            await manager.subscribe_thread(ws, data["thread_id"])
        case "unsubscribe":
            await manager.unsubscribe_thread(ws, data["thread_id"])
        case "message":
            # Создать сообщение через chat_service (как в текущем per-thread WS)
        case "control":
            # Применить control action
```

---

### Шаг 5: Company-Level события в точках broadcast

**Файлы:**
- `apps/backend/src/backend/modules/chat/routers.py` — все 11 точек broadcast

**Что делаем:**

В каждой точке, где вызывается `broadcast_to_thread`, добавить `broadcast_to_company` с компактным событием для обновления списка тредов:

```python
# Пример: при создании сообщения (ingest_messages)
await websocket_manager.broadcast_to_thread(thread_id, message_event)

# Новое: уведомить всех в компании об обновлении треда
thread_list_event = RealtimeEvent(
    event_type=RealtimeEventType.THREAD_LIST_UPDATE,
    thread_id=thread_id,
    payload={
        "last_message_preview": content[:100],
        "last_message_at": message.created_at.isoformat(),
        "unread_count_delta": 1,
        "state": thread.state.value,
    },
)
await websocket_manager.broadcast_to_company(company_id, thread_list_event)
```

**Новые RealtimeEventType:**
- `THREAD_LIST_UPDATE` — обновление превью/unread/state для списка
- `THREAD_CREATED` — новый тред появился

**Точки добавления company broadcast:**

| # | Триггер | Company Event |
|---|---------|---------------|
| 1 | Новое сообщение (ingest) | THREAD_LIST_UPDATE: preview + unread_delta |
| 2 | Сообщение от менеджера | THREAD_LIST_UPDATE: preview |
| 3 | Control action | THREAD_LIST_UPDATE: state + assistant_active |
| 4 | Handoff | THREAD_LIST_UPDATE: state |
| 5 | Assignee changed | THREAD_LIST_UPDATE: assignee |
| 6 | Thread state update | THREAD_LIST_UPDATE: state |
| 7 | New thread created | THREAD_CREATED: full ChatThreadSummary |

Notes и custom fields updates НЕ требуют company-level broadcast (не влияют на список тредов).

---

### Шаг 6: Удаление старого per-thread WS

**Файлы:**
- `apps/backend/src/backend/modules/chat/routers.py`
- `apps/backend/src/backend/modules/chat/websocket.py`

**Контекст:** Фронт не использует старый WS — нет пользователей, нет backward compat проблемы. Удаляем сразу.

**Что делаем:**
- Удалить эндпоинт `GET /companies/{company_id}/threads/{thread_id}/ws` из routers.py
- Удалить `websocket_router` если он использовался только для этого эндпоинта
- Оставить `WebSocketManager` и `websocket_manager` синглтон — они нужны для нового company-level WS

---

### Шаг 7: WS-Contract эндпоинт (обновление)

**Файлы:**
- `apps/backend/src/backend/modules/chat/routers.py` — обновить `describe_ws_contract`

**Что делаем:**
- Обновить `/threads/{thread_id}/ws-contract` с новым протоколом
- Документировать ticket auth flow
- Документировать subscribe/unsubscribe
- Документировать новые event types

---

## Порядок реализации

```
Шаг 1 (Redis client)          → нет зависимостей
Шаг 2 (Ticket endpoint)       → зависит от Шага 1
Шаг 3 (WebSocketManager v2)   → нет зависимостей
Шаг 4 (Company WS endpoint)   → зависит от Шагов 1, 2, 3
Шаг 5 (Company broadcasts)    → зависит от Шага 3
Шаг 6 (Deprecation)           → зависит от Шага 4
Шаг 7 (Contract update)       → зависит от Шага 4
```

Шаги 1 и 3 можно делать параллельно.
Шаги 5, 6 и 7 можно делать параллельно после Шага 4.

---

## Что НЕ входит в scope

- **Redis pub/sub для multi-instance** — текущий деплой single-instance, добавим когда понадобится
- **Typing indicators** — протокол поддерживает (TYPING event type уже есть), но реализация отдельной задачей
- **Фронтенд-реализация** — этот план только про бэкенд; фронт использует WS-contract для интеграции
- **Миграция с polling на WS на фронте** — отдельная задача после деплоя бэкенда

---

## Риски

| Риск | Митигация |
|------|-----------|
| In-memory WS manager теряет соединения при рестарте | Фронт реконнектится с exponential backoff; не блокер для MVP |
| Много соединений на одну компанию | asyncio.Lock + лимит на max connections per company (100?) |
| Race condition при subscribe/unsubscribe | Все операции через asyncio.Lock (уже есть паттерн) |
| Тикет используется дважды | GETDEL атомарный — второе использование получит None |
