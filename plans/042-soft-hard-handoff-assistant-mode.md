# 042 — Soft/Hard Handoff с AssistantMode

## Зачем это делаем

После handoff сейчас `assistant_active = False` — агент молчит, пока менеджер не ответит. Сообщения клиента сохраняются, но никто не отвечает.

**Результат:** `assistant_mode` вместо bool: soft handoff — агент ведёт диалог до первого сообщения менеджера; hard (`escalate=true`) — сразу молчит. `Thread.state` и `Order.assignee` не удаляем; routing к sales-agent опирается на `assistant_mode`, не на `state`.

## AS-IS (кратко)

| | `handoff` (notify) | `request_handoff` (order) |
|--|-------------------|---------------------------|
| Endpoint | `POST /internal/chat/threads/{id}/handoff` | `POST /internal/orders/{id}/handoff` |
| Назначает менеджера | Нет | Да (`select_manager` + `update_assignee`) |
| CRM-прокси / `handoff_summary` на клиенте | Да | Нет |
| Ответ агенту | `HandoffSummary` | `RequestHandoffResponse` (менеджер, расписание) |

`select_manager`: кандидаты из `schedule_service.get_available_managers` (компания, `is_available`, есть `work_schedule`, не `VIEWER`); предпочтение тем, кто **сейчас в смене** (`is_manager_working_now`); иначе все доступные. Сортировка по `(число открытых заказов на assignee, last_assigned_at)` — минимальная нагрузка, затем давно не назначали. Референс-тесты: `apps/backend/tests/domains/orders/test_load_balancing.py`.

`stage` в старом `handoff` попадал только в metadata системного сообщения и лог — **не** меняет стадию заказа. В TO-BE из тула и LLM-пути убрать.

## Решения

1. `assistant_active: bool` → `assistant_mode: StrEnum` (`active` | `shadowing` | `inactive`). Breaking API; фронт в том же PR.
2. Удалить `WAITING_ASSISTANT` из `ThreadState` (не используется).
3. Один тул `handoff`: всегда `POST /internal/orders/{order_id}/handoff` + персист `handoff_summary` + CRM-прокси как у старого `handoff`. Удалить `request_handoff` тул и `notify_handoff` client path.
4. Политика `escalate` — в **JSON Schema `description`** полей тула в `registry.py` (компании без handoff в `enabled_tools` тул не видят).
5. Параметр `stage` у handoff убрать; при необходимости данные для CRM — только с бэкенда (текущий контекст заказа), не от модели.

## TO-BE

### AssistantMode

```python
class AssistantMode(StrEnum):
    ACTIVE = "active"
    SHADOWING = "shadowing"
    INACTIVE = "inactive"
```

### Тул `handoff` (схема)

- `summary`, `reason` — required; продуктовые русские `description` в schema.
- `escalate: bool`, default `false` — в `description` явно: `false` = обычная передача, агент отвечает до менеджера; `true` = агрессия/эскалация, после вызова агент клиенту не пишет.

Поток: sales-agent → `POST /internal/orders/{order_id}/handoff` с `{summary, reason, escalate}` → `select_manager` → при успехе `update_assignee` → `handle_handoff(escalate)` → `state=HANDOFF`, `mode=shadowing|inactive`, system message, WS → ответ с инфо о менеджере. Плюс customer fields + CRM как сейчас у `handoff_commit`.

### Ingress (`messages/routers.py`)

- `assistant_mode == INACTIVE` → только сохранение, без sales-agent.
- `role == MANAGER` → `set_assistant_mode(INACTIVE, ...)`, без forward.
- `ACTIVE` или `SHADOWING` → forward (при прочих гейтах без изменений).

### Пары `(Thread.state, assistant_mode)` (ориентир)

| state | mode |
|-------|------|
| ACTIVE | обычно ACTIVE; INACTIVE если пауза |
| HANDOFF | SHADOWING (soft) или INACTIVE (hard) |
| WAITING_MANAGER | INACTIVE |
| CLOSED | INACTIVE |

---

## Покрытие тестами (AS-IS, до 042)

| Область | Что уже есть | Пробелы |
|---------|----------------|--------|
| `ChatService.handle_handoff` + metadata | `tests/domains/chat/test_handoff.py` (service + часть роутера) | Нет веток `escalate` / `assistant_mode`; после смены API — обновить ожидания |
| `POST /internal/chat/threads/.../handoff` | Тот же файл | Роут будет удалён — тесты заменить на order handoff |
| `POST /internal/orders/.../handoff` | `tests/domains/orders/test_handoff_endpoint.py` | Нет `escalate`; сейчас всегда ожидается `assistant_active=False` — нужны кейсы soft→`shadowing` и hard→`inactive` |
| Ingress → sales-agent | `tests/domains/messages/test_routers.py` (mock `forward_inbound`, `assistant_active=True`) | **Нет** кейса `assistant_active=False` без вызова `forward_inbound`; **нет** менеджерского inbound и побочных эффектов |
| Репозиторий тредов | `test_threads_repo_set_assistant_active` | Нет `set_assistant_mode`; нет тестов фильтров AI/HUMAN в `repository.py` |
| `ThreadsService.set_assistant_active` | Только через `customers/test_services` (control) | Нет прямых тестов debounce cancel / инкапсуляции |
| Пинги | Нет `tests/.../pings/` | `pings/evaluator.py` по `assistant_mode` — новые unit/integration тесты |
| `TaskExecutor` | `tests/domains/tasks/test_task_executor.py` | Нет привязки к `assistant_active` / будет к `assistant_mode` |
| `notify_handoff` HTTP client | `tests/domains/services/test_backend_client_handoff.py` | После склейки — переписать под единый order-handoff client |
| `handoff_commit` / CRM | `tests/domains/agents/test_handoff_tool.py` | Нет тестов на `request_handoff` tool + `backend_client.request_handoff` |
| Pipeline envelope | `test_pipeline.py`, `test_pipeline_e2e.py` (`assistant_active` в фикстурах) | Обновить на `assistant_mode` + при необходимости сценарий shadowing |
| sales-front | `tests/workspaceReducer.test.ts` (`assistant_active` → `isAiManaged`) | Нет `shadowing`; нет маппинга WS payload; компоненты (`SalesFunnel`) без unit на три режима |

---

## Фазы

### Phase 0 — тестовая сетка (до миграции и смены модели)

**Цель:** зафиксировать наблюдаемое поведение сейчас и описать полный набор проверок для TO-BE, чтобы рефакторинг не менял контракт незаметно.

**Правило:** тесты на **текущее** поведение — зелёные до merge фазы 1. Тесты на **новое** (`shadowing`, `escalate`, менеджер при `SHADOWING` → `inactive`, ingress при `shadowing` → forward) — добавить в этом же PR блоком с `pytest.mark.xfail(..., strict=False)` (или отдельный файл `test_assistant_mode_to_be.py`), снять xfail по мере фаз 1–3; либо второй коммит сразу после Phase 0 только с xfail-тестами.

**Backend — добавить/расширить**

- `tests/domains/messages/test_routers.py` — customer inbound: при `assistant_active=False` **не** вызывается `forward_inbound` (сохранение сообщения при необходимости проверить по существующим ассертам).
- `tests/domains/messages/test_routers.py` — роль менеджера: первое сообщение после handoff снимает AI (сейчас — `assistant_active`; после 042 — `assistant_mode=inactive`).
- `tests/domains/orders/test_handoff_endpoint.py` — после появления `escalate` в API: матрица soft/hard и ожидаемый `assistant_mode` + `Thread.state`; кейс «менеджер не найден» без смены mode.
- `tests/domains/chat/test_handoff.py` — разделить сценарии service vs удаляемый internal route; для service — контракт metadata без `stage` (после 042).
- Новый узкий модуль при необходимости: `tests/domains/pings/test_evaluator_assistant_mode.py` или рядом с существующим кодом пингов — кандидаты при `ACTIVE`/`SHADOWING` vs `INACTIVE`, исключения по `state`.
- `tests/domains/tasks/test_task_executor.py` — явная проверка пропуска/выполнения AI-задачи в зависимости от флага ассистента (сейчас bool, потом enum).

**Sales-agent**

- Тесты на `backend_client.request_handoff` (если отсутствуют — добавить зеркально к `test_backend_client_handoff.py`).
- После объединения тулов — один набор тестов на единый handoff path (order + `escalate`), удалить дублирующие моки `notify_handoff` там, где путь станет только order.

**sales-front**

- Расширить reducer/WS тесты: `assistant_mode` → `isAiManaged` для `active`/`shadowing`/`inactive`; отдельный кейс для shadowing label (если выносится в чистую функцию — тест на неё).

**Критерий готовности Phase 0:** перечисленные пробелы из таблицы либо закрыты зелёными тестами (AS-IS), либо закрыты xfail-тестами с однозначным ожидаемым результатом из разделов TO-BE и Edge cases выше.

### Phase 1 — модель и миграция (backend)

- `apps/backend/src/backend/modules/chat/models.py` — `AssistantMode`, поле `assistant_mode`, убрать `assistant_active`; вычистить `WAITING_ASSISTANT` из enum.
- `apps/backend/src/backend/modules/chat/schemas.py` — ответы/API: `assistant_mode`, синхронизация `ThreadState`.
- `apps/backend/migrations/models/` — Aerich migrate + **schema prefix** `backend.` на все таблицы/индексы в SQL.

### Phase 2 — сервис и репозиторий (backend)

- `threads_service.py` — `set_assistant_mode`; debounce cancel только при `INACTIVE`.
- `repository.py` — `set_assistant_mode`; фильтры `AI` = active или shadowing, `HUMAN` = inactive.
- `service.py` — `handle_handoff(..., escalate: bool)` → mode; без `stage` в сигнатуре и в metadata сообщения; `control_thread_assistant` → `control_thread_mode`.
- `thread_control.py` — маппинг действий UI на `(state, assistant_mode)`.

### Phase 3 — routing и endpoints (backend)

- `messages/routers.py` — gate по `assistant_mode`; менеджер при `SHADOWING` → `INACTIVE`.
- `orders/routers.py` + `orders/schemas.py` — `HandoffRequest.escalate`, прокид в `handle_handoff`; поле **`assistant_active` на DTO заказа** (берётся с треда в list/detail) заменить на **`assistant_mode`** и проброс с `Thread`.
- `chat/routers.py` — удалить internal `notify_handoff` (замена единым order handoff).
- `chat/websocket.py` — payload событий: `assistant_active` → `assistant_mode` (breaking для клиента).
- `pings/evaluator.py` — кандидаты с `assistant_mode` in (ACTIVE, SHADOWING); исключения по `state` как сейчас.
- `workers/task_executor.py` — вместо `not assistant_active` проверять `assistant_mode == INACTIVE` (и при необходимости оставить проверки `state` для ping-guard).

### Phase 4 — sales-agent

- `core/tools/registry.py` — один `handoff` в `TOOL_PARAMS` и в handler map; финальные `description` для полей.
- `agents/tools.py` — единая реализация handoff (order endpoint + customer fields + CRM).
- `services/backend_client.py` — один метод handoff по order с `escalate`; без `notify_handoff`.

### Phase 5 — фронт (sales-front)

- Заменить `assistant_active` на `assistant_mode`; фильтры и WS: `isAiManaged` = active или shadowing; подпись для shadowing (например «AI, ожидает менеджера»).

### Phase 6 — регрессия и снятие xfail

- Выполнить после фаз 1–5: все тесты из **Phase 0** зелёные; снять `xfail` у TO-BE сценариев.
- `tests/domains/chat/test_handoff.py` — `handle_handoff(...)` под **`escalate` / `assistant_mode` / без `stage` в metadata**; HTTP-тесты internal chat handoff удалить или заменить на order.
- `tests/domains/messages/test_routers.py` — forward/block по `assistant_mode` (в т.ч. `SHADOWING`).
- `tests/domains/customers/test_repositories.py`, `test_services.py`, `test_routers.py` — `assistant_mode`, `set_assistant_mode`.
- `apps/sales-agent/tests/...` — единый handoff client + `escalate`; актуализировать `test_backend_client_handoff.py` / `test_handoff_tool.py`.

---

## Edge cases

| Ситуация | Ожидание |
|----------|----------|
| Нет менеджера (`select_manager` → None) | `success=False`, тред/mode без handoff-смены, AI продолжает |
| Менеджер пишет при SHADOWING | `INACTIVE`, дальше без AI |
| Повторный soft handoff | Уже SHADOWING — идемпотентно по смыслу |
| Race manager vs AI | Исходящий ответ может уйти; следующий inbound без AI при `INACTIVE` |

## Миграция данных

| Было | Стало |
|------|--------|
| `assistant_active=True` | `assistant_mode=active` |
| `assistant_active=False` | `assistant_mode=inactive` |

## Модель для выполнения

**Opus** (или эквивалент): три модуля, миграция, breaking API, склейка тулов.

## Валидация против кода (gaps закрыты в фазах выше)

| Находка | Действие |
|---------|----------|
| Файла `tests/domains/chat/test_thread_control.py` нет | Тесты control — в `tests/domains/customers/*` |
| `Order` list/detail отдаёт `assistant_active` с треда (`orders/schemas.py`, `orders/routers.py`) | Явно в Phase 3: `assistant_mode` |
| После удаления `notify_handoff_internal` ломаются тесты в `test_handoff.py` | Phase 6: перецелить на order endpoint |
| Registry `handoff` → `agents/tools.py::handoff_commit` с `user_message`/`operator` — в плане явно только `stage` | Зафиксировать: оставить в LLM-schema или захардкодить в `handoff_commit` для CRM |
| `Thread.state == HANDOFF` по-прежнему режет пинги (`pings/evaluator.py`) | Soft handoff остаётся в `HANDOFF` — пинги не идут; иначе нужен отдельный продуктовый шаг (вне 042) |
| `libs/common` не содержит модель Thread | `AssistantMode` только backend + дублирование enum в schema sales-agent при необходимости контракта |
| WS / thread list шлют `assistant_active` в sales-front (`useWebSocket`, `useThreads`, reducer) | Phase 5 + backend WS schema: заменить на `assistant_mode` и правило `isAiManaged = mode in {active, shadowing}` |

**Пересечение фаз:** `chat/service.py` — Phase 2 и вызовы из `orders/routers.py` (Phase 3); нормально, порядок фаз сохранить.
