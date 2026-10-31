# 026 — Manager Work Schedule & Load Balancing

> **Это документ требований**, а не пошаговый план реализации. Здесь описано ЧТО мы строим и принятые решения, а не КАК писать код.

## Objective

Реализовать график работы менеджеров и распределение заказов по загрузке: расширить CompanyUser полями `work_schedule` и `is_available`, создать логику определения рабочего времени, алгоритм load balancing при handoff, и AI messaging когда никто не работает.

## Why We're Doing This

Сейчас заказы назначаются на менеджеров без учёта их рабочего графика и текущей загрузки. Это приводит к:
- **Неравномерному распределению** — один менеджер может получить 10 заказов, другой 2
- **Назначению в нерабочее время** — клиент ждёт ответа, а менеджер не на связи
- **Ручному перераспределению** — администратор вынужден мониторить и перекидывать заказы

После реализации:
- Клиент сразу получает корректные ожидания ("Менеджер ответит завтра с 09:00")
- Нагрузка распределяется справедливо — новые заказы идут тому, у кого меньше активных
- Менеджеры работают в своих часовых поясах и по своему графику

## Context

Задача является Phase 7 из общего плана V4 Product (`plans/yoolo-requirements-product-v4.md`).

**Зависимости:**
- Order модель уже реализована (`apps/backend/src/backend/modules/orders/models.py`)
- CompanyUser существует (`apps/backend/src/backend/modules/users/models.py`)
- Tool `handoff` уже существует (`apps/sales-agent/src/sales_agent/agents/tools.py`) — нужно расширить
- `handle_handoff` в backend уже деактивирует AI (`backend/modules/chat/service.py`)

**Текущее состояние CompanyUser:**
- `id`, `user`, `company`, `role`, `created_at`
- Нет полей для schedule и availability

**Текущее состояние назначения Orders:**
- Только ручное назначение через `update_assignee`
- Нет автоматического load balancing
- Мы ДОБАВЛЯЕМ автоназначение, не заменяем

---

## Scope (MVP)

### В scope
- Рабочие дни и часы по неделе (weekly schedule)
- Индивидуальное расписание у каждого менеджера
- Ручной флаг `is_available` (DND)
- Load balancing по количеству активных Orders
- AI messaging про рабочее время

### Вне scope (future)
- ❌ Праздники, страны, автоматические выходные
- ❌ UI-календарики и сложные правила
- ❌ Exceptions / vacations в schedule
- ❌ Split shifts (несколько слотов в день) — формат готов, логика нет
- ❌ Слоты пересекающие полночь

---

## What We're Building

### 1. Расширение модели CompanyUser

```python
class CompanyUser(BaseModel):
    # ... existing fields
    work_schedule: JSON | None  # nullable, Pydantic-validated
    is_available: bool = True   # manual DND flag
    last_assigned_at: datetime | None  # для tie-breaking, null = приоритет
```

### 2. Формат work_schedule

Строгая Pydantic-схема с обязательными полями:

```json
{
  "version": 1,
  "timezone": "Europe/Moscow",
  "weekly": {
    "mon": [{"start": "09:00", "end": "18:00"}],
    "tue": [{"start": "09:00", "end": "18:00"}],
    "wed": [{"start": "09:00", "end": "18:00"}],
    "thu": [{"start": "09:00", "end": "18:00"}],
    "fri": [{"start": "09:00", "end": "18:00"}],
    "sat": [],
    "sun": []
  }
}
```

**Правила:**
- `version` — обязательно, для будущих миграций
- `timezone` — обязательно, IANA timezone (валидация)
- `weekly` — все 7 дней обязательны, каждый день — массив слотов
- Пустой массив `[]` = выходной
- MVP: только один слот в день (валидация), формат готов к split shifts
- Слоты пересекающие полночь запрещены (start < end)

### 3. Schedule Service

```python
# Сервис расчётов рабочего времени
def is_manager_working_now(company_user: CompanyUser) -> bool
def get_next_working_time(company_user: CompanyUser) -> datetime | None
def get_available_managers(company: Company) -> list[CompanyUser]
```

**Логика:**
- Учитывает timezone менеджера
- Учитывает weekly slots
- Учитывает `is_available` флаг
- Расчёты в Python (не SQL)
- Архитектурно готов к extensions (hooks для exceptions/holidays), но без реализации

### 4. Load Balancing

**Абстракция:**
```python
def load_score(manager: CompanyUser) -> int
```

**MVP реализация:**
- `load_score = count(active_orders)` где active = `closed_at IS NULL`

**Алгоритм выбора (двухуровневый):**

```
1. Найти работающих: is_available=True + work_schedule!=null + в рабочих часах
2. Если есть работающие:
   → Сортировка по load_score (ascending)
   → Tie-breaking: last_assigned_at (кто дольше без заказа)
   → Выбор первого
3. Если НЕТ работающих:
   → Взять всех с work_schedule!=null и is_available=True
   → Сортировка по load_score (ascending)
   → Tie-breaking: last_assigned_at
   → Выбор первого
4. Fallback: если у всех work_schedule=null → Order без assignee
```

**Ключевое правило:** "работает И меньше заказов" → если таких нет → "просто меньше заказов"

**Поведение в нерабочее время:**
- Order всё равно назначается менеджеру (по load_score среди неработающих)
- AI уведомляет клиента о передаче
- Ответ клиенту позже даст сам менеджер

**Future-proof:** интерфейс `load_score` позволит добавить SLA, приоритеты, skills, capacity без изменения алгоритма выбора.

### 4.1. Транзакционные операции (Repository Encapsulation)

**Принцип:** Все операции с зависимыми данными инкапсулированы в repository/service. Запрещено обновлять поля напрямую в обход этих методов.

| Операция | Зависимые изменения | Единственная точка входа |
|----------|---------------------|--------------------------|
| Назначить Order на менеджера | `Order.assignee_id` + `CompanyUser.last_assigned_at` | `OrdersRepository.update_assignee()` |
| Handoff (передача от AI) | `Order.assignee_id` + `last_assigned_at` + `Thread.assistant_active=False` + `Thread.state=HANDOFF` + system message | `ChatService.handle_handoff()` (использует `update_assignee()`) |
| Создать Order с assignee | `Order` creation + `CompanyUser.last_assigned_at` (если assignee) | `OrdersRepository.create()` |

**Реализация в `OrdersRepository.update_assignee()`:**
```python
async def update_assignee(self, order: Order, assignee_id: int | None, ...) -> ...:
    previous_assignee_id = order.assignee_id
    order.assignee_id = assignee_id
    await order.save(update_fields=["assignee_id"])
    
    # Автоматически обновляем last_assigned_at
    if assignee_id:
        await CompanyUser.filter(id=assignee_id).update(
            last_assigned_at=datetime.now(UTC)
        )
    
    # Логирование...
    return order, previous_assignee_id
```

**Аналогично в `OrdersRepository.create()`:**
```python
async def create(self, ..., assignee_id: int | None = None, ...) -> Order:
    order = await Order.create(...)
    
    if assignee_id:
        await CompanyUser.filter(id=assignee_id).update(
            last_assigned_at=datetime.now(UTC)
        )
    
    return order
```

### 5. Tool: request_handoff

**Response format (structured, readable keys):**

```python
class ManagerInfo:
    id: int
    name: str
    timezone: str

class AvailabilityInfo:
    is_working_now: bool
    next_available_at: datetime | None      # UTC
    next_available_at_local: str | None     # "2024-01-15 09:00" в TZ менеджера
    next_available_timezone: str | None     # "Europe/Moscow"
    schedule_description: str | None        # "Пн-Пт 09:00-18:00 (Europe/Moscow)"

class HandoffResult:
    success: bool
    manager: ManagerInfo | None
    availability: AvailabilityInfo
    message_hint: str | None  # "tomorrow at 09:00 Moscow time" — всегда с явным указанием города
```

**Логика:**
- Вызывается AI когда нужно передать клиента менеджеру
- Всегда назначает assignee (либо работающего, либо того кто выйдет первым)
- **Деактивирует AI в треде** — вызывает существующий `handle_handoff` (см. ниже)
- Agent сам формирует текст клиенту на основе structured data

**Интеграция с существующим handoff:**
Функционал деактивации AI уже реализован в `backend/modules/chat/service.py`:
```python
# handle_handoff() делает:
# 1. thread.state = ThreadState.HANDOFF
# 2. thread.assistant_active = False
# 3. Создаёт системное сообщение
```
Новый `request_handoff` tool должен:
1. Выбрать менеджера через load balancing
2. Назначить Order.assignee
3. Вызвать `handle_handoff` для деактивации AI и создания системного сообщения

**schedule_description** — текстовый интерпретатор расписания:
- Возвращает человекочитаемую строку
- Примеры: "Пн-Пт 09:00-18:00", "Пн-Ср 10:00-19:00, Пт 10:00-15:00"
- Включает timezone

### 6. Notification Hook (future)

**Место для триггера уведомлений:**
- При назначении Order на менеджера вне его рабочего времени
- Hook вызывается, но в MVP ничего не делает
- Future: уведомление в момент начала рабочего времени

```python
async def on_order_assigned_outside_working_hours(
    order: Order, 
    manager: CompanyUser,
    next_working_time: datetime
) -> None:
    # MVP: pass (no-op)
    # Future: schedule notification for next_working_time
    pass
```

---

## Decisions

### Формат и валидация
1. **Формат schedule** — JSON с version, timezone, weekly (массивы слотов)
2. **Слоты как массивы** — future-proof для split shifts, MVP только 1 слот
3. **Строгая Pydantic валидация** — fail fast при невалидных данных
4. **Расчёты в Python** — не SQL, проще тестировать и расширять

### Schedule edge cases
5. **Null schedule** — менеджер не участвует в автораспределении (только manual assignment)
6. **Все дни пустые** — валидно, менеджер не работает по расписанию (manual only)

### Participation
7. **Кто участвует** — все CompanyUser кроме VIEWER
8. **Owner** — участвует как обычный менеджер, управляется через `is_available`

### Load balancing
9. **Load score абстракция** — MVP = active_orders_count, extensible
10. **Tie-breaking** — кто дольше без нового заказа (поле `last_assigned_at` на CompanyUser)
11. **last_assigned_at storage** — поле на CompanyUser, обновляется при ЛЮБОМ назначении (auto + manual)
12. **Начальное значение** — `null` означает "давно", приоритет над теми у кого есть дата

### Назначение вне рабочего времени
13. **Assignee всегда назначается** — даже в нерабочее время, по load_score среди неработающих
14. **Приоритет выбора** — "работает И меньше заказов" → если нет → "просто меньше заказов"
15. **AI messaging** — tool возвращает structured data, agent формирует текст под контекст
16. **Notification hook** — предусмотрен, но не реализован в MVP
17. **UI статус** — вне scope MVP, просто assignee без особой индикации

### Tool response
17. **Расширенный формат** — manager info + availability + message_hint + schedule_description
18. **schedule_description** — текстовый интерпретатор расписания ("Пн-Пт 09:00-18:00")

### Триггер и интеграция handoff
19. **Вызов handoff** — определяется промптингом компании, вне scope этой задачи
20. **Handoff = AI → человек** — переназначение между людьми только ручное
21. **Расширяем существующий tool** — `handoff` в sales-agent уже существует, добавляем load balancing
22. **Деактивация AI** — `handle_handoff` в backend уже делает `assistant_active=False`, переиспользуем

### DND и существующие Orders
21. **is_available влияет только на НОВЫЕ назначения** — текущие Orders остаются на менеджере

### Repository Encapsulation (консистентность данных)
22. **Зависимые данные через repository** — все операции с зависимыми полями инкапсулированы в repository/service
23. **Запрет прямого update** — нельзя менять `Order.assignee_id` напрямую, только через `update_assignee()`
24. **Автоматическое обновление** — `last_assigned_at` обновляется автоматически внутри `update_assignee()` и `create()`

> См. правило: `.cursor/rules/data-consistency.mdc`

### Permissions на schedule
22. **Менеджер** — может менять только своё расписание
23. **Admin/Owner** — могут менять расписание любого менеджера компании

### У всех null schedule
24. **Если никого нельзя назначить** — Order остаётся без assignee (ручное назначение)

### Timezone в tool response
25. **Возвращаем оба варианта** — UTC datetime + local string в TZ менеджера
26. **message_hint** — содержит явное указание timezone (город), agent использует как подсказку

---

## Module Structure

| Компонент | Модуль | Файл |
|-----------|--------|------|
| CompanyUser extension | backend | `apps/backend/src/backend/modules/users/models.py` |
| WorkSchedule schema | backend | `apps/backend/src/backend/modules/users/schemas.py` |
| Schedule service | backend | `apps/backend/src/backend/modules/users/schedule_service.py` |
| Load balancing service | backend | `apps/backend/src/backend/modules/orders/load_balancing.py` |
| Handoff endpoint | backend | `apps/backend/src/backend/modules/orders/routes.py` |
| handoff tool (расширение) | sales-agent | `apps/sales-agent/src/sales_agent/agents/tools.py` |
| Migration | backend | `apps/backend/migrations/` |

---

## API Endpoints

### Backend (новые/изменённые)

| Method | Endpoint | Описание | Модуль |
|--------|----------|----------|--------|
| PATCH | `/api/v1/company-users/{id}` | Обновить work_schedule, is_available | backend/users |
| GET | `/api/v1/company-users/{id}/schedule` | Получить расписание с интерпретацией | backend/users |
| POST | `/api/v1/orders/{id}/handoff` | Запросить передачу менеджеру | backend/orders |
| GET | `/api/v1/companies/{id}/available-managers` | Список доступных менеджеров | backend/users |

### Sales Agent (tools)

| Tool | Описание |
|------|----------|
| `handoff` (расширение) | Существующий tool — добавить load balancing для выбора assignee |

---

## Open Questions (требуют ответа)

*Все вопросы закрыты.*

---

## Questions Addressed During Design

- Пустой schedule — что делать?
- Все дни пустые — валидно или ошибка?
- Кто участвует в load balancing?
- Owner компании — участвует?
- Равная загрузка — как выбрать?
- Order без assignee — когда никто не работает?
- Формат AI сообщения — structured или готовый текст?
- Где хранить last_assigned_at?
- Начальное значение last_assigned_at?
- Уведомление менеджеру вне рабочего времени?
- UI статус для pending handoff?
- Структура ответа request_handoff?
- Когда AI вызывает request_handoff?
- Что такое handoff — AI→человек или между людьми тоже?
- Связь с текущим flow назначения?
- Менеджер уходит в DND — что с его Orders?
- Кто может менять schedule?
- UI scope для настройки schedule?
- last_assigned_at обновляется при manual assignment?
- Timezone в message_hint?
- Деактивация AI при handoff?
- Алгоритм выбора когда никто не работает? → по load_score среди всех с schedule

---

## Scope Summary

### MVP
- [x] `work_schedule` JSON поле на CompanyUser
- [x] `is_available` bool поле на CompanyUser
- [x] `last_assigned_at` datetime поле на CompanyUser
- [x] Pydantic схема с валидацией (version, timezone, weekly)
- [x] Schedule service (is_working_now, get_next_working_time, get_available_managers)
- [x] Load balancing (load_score, tie-breaking)
- [x] request_handoff tool с structured response
- [x] schedule_description — текстовое описание расписания
- [x] Notification hook (stub)

### Future
- [ ] Exceptions / vacations в schedule
- [ ] Split shifts (несколько слотов в день)
- [ ] Слоты пересекающие полночь
- [ ] UI-календарь
- [ ] Уведомления при назначении вне рабочего времени
- [ ] UI индикация "ожидает менеджера"

---

*Требования подготовлены совместно с продуктом.*
