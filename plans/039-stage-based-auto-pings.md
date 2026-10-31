# 039 — Stage-Based Auto-Pings (Follow-Up Цепочки)

## Objective

Автоматические follow-up сообщения ("пинги"), привязанные к стадиям воронки. Система сама пишет клиенту, если он замолчал, с контентом, зависящим от текущей стадии заказа.

## Зачем это делаем

**Проблема:** Когда клиент перестаёт отвечать, менеджеры забывают или не успевают делать follow-up. Лиды теряются на каждой стадии воронки.

**Ценность:** Автоматические цепочки пингов "дожимают" клиентов без участия менеджера. На стадии квалификации — мягкое напоминание ответить на вопрос. На стадии оффера — конкретный вопрос "что думаете про предложение?". Перед записью — напоминание о визите. Каждая стадия — свой тон, свой контент, свои тайминги.

**Что становится возможным:** Компании настраивают цепочки пингов на каждую стадию через UI. Система сама пишет клиенту в правильный момент с правильным сообщением. Менеджер вообще не участвует — или подключается только когда клиент ответил на пинг.

## Версионирование

### Level 1 (этот план): Время-Based Пинги
- Триггер: mongo-like condition `{"$customer_silent_seconds": {"$gte": 86400}}`
- Контент: AI-генерация через `reminder_instructions` injection в `agent.md` промпт
- Цепочка: до 5 пингов на стадию с разными задержками (delay в секундах)

### Level 2 (будущее): Field-Based Условия
- Триггер: расширение condition engine — `{"$and": [{"$customer_silent_seconds": {"$gte": 86400}}, {"order_fields.follow_up_date": {"$lte": "now"}}]}`
- Контент: контекстный — "у вас запись завтра", "спец-акция заканчивается"
- Condition engine уже поддерживает `order_fields.*` — нужен только evaluator context

---

## Ключевые архитектурные решения

### 1. Condition Engine — переиспользуем `core/conditions/`

Существующий движок (`core/conditions/interpreter.py`) уже поддерживает `$and/$or/$not`, field comparisons (`$eq/$gte/$lte`), custom operators. Для пингов добавляем один custom operator `$customer_silent_seconds` — проверяет `now - last_customer_message_at` в секундах.

Это даёт:
- Единый синтаксис условий для stage transitions и ping rules
- Валидация через `validate_condition()` бесплатно
- Detailed report через `evaluate_condition_detailed()` для UI
- Level 2 (field-based условия) — бесплатно, движок уже умеет `order_fields.*`

### 2. Prompt Injection — через существующий `reminder_instructions`

Базовый `agent.md` не меняется. `PingRule.prompt_override` передаётся как `reminder_instructions` и инжектится в `dynamic_context` (строка 236-237 `pipeline.py`). Пользователь пишет только дополнение к промпту ("напомни про оффер"), а не дублирует весь `agent.md`.

### 3. Worker Hub — единый entry point, конфигурация через `.env`

Вместо отдельных `task_scheduler.py` и `ping_evaluator.py` — один `workers/hub.py` с реестром воркеров. Каждый воркер — отдельная async coroutine с собственным poll interval.

Конфигурация через env var `WORKERS`:
```
WORKERS=all                              # dev: запустить все зарегистрированные воркеры
WORKERS=task_scheduler,ping_evaluator    # prod: конкретный набор для этого инстанса
WORKERS=task_scheduler                   # prod: только scheduler в этой реплике
```

Горизонтальный скейлинг — ответственность compose/k8s, не приложения. Hub просто выбирает нужные воркеры по env и запускает их. Idempotency через unique constraint + Redis SETNX lock.

### 4. schedule_reminder vs auto-pings — правило приоритета

**Агентский followup-reminder всегда приоритетнее авто-пингов.** Evaluator проверяет: есть ли для order pending Task с `auto_action=SEND_FOLLOWUP_MESSAGE AND ping_rule_id IS NULL`. Если да — evaluator пропускает этот order. Когда AI-reminder выполнен/отменён — авто-пинги снова работают.

Подавляют авто-пинги **только** followup-reminder-ы (`auto_action=SEND_FOLLOWUP_MESSAGE`), не другие типы задач. Если в будущем появятся другие `TaskAutoAction` (например, `SEND_UPSELL`, `NOTIFY_MANAGER`), они не должны влиять на цепочку пингов.

Логика: агент контекстно умнее правил. Если клиент сказал "напишите завтра утром" — агент поставил reminder на утро. Автоматический пинг через 24ч тут не нужен.

### 5. Продуктовые решения

| Вопрос | Решение |
|---|---|
| Максимум пингов на стадию | 5 (жёсткий лимит в schema validation) |
| Пинги на финальных стадиях (`is_final=True`) | Блокировать создание ping rules |
| `assistant_active=False` | Замораживать пинги (evaluator пропускает) |
| Пинги от чьего имени | От бота (через AI pipeline) |
| Thread в состоянии `HANDOFF` | Замораживать пинги (evaluator пропускает) |

---

## Что уже есть (инфраструктура)

| Компонент | Статус | Файл |
|---|---|---|
| `Task` модель с `AI_SCHEDULED` + `send_followup_message` | ✅ Есть | `modules/tasks/models.py` |
| `TaskScheduler` — поллинг `due_date <= now` | ✅ Есть | `workers/task_scheduler.py` |
| `TaskExecutor` — собирает контекст, вызывает sales-agent | ✅ Есть | `workers/task_executor.py` |
| `TaskRepository` — CRUD + `get_due_tasks` | ✅ Есть | `modules/tasks/repository.py` |
| `schedule_reminder` tool в sales-agent | ✅ Есть | `core/tools/registry.py` |
| `StageTemplate` модель | ✅ Есть | `modules/stages/models.py` |
| `Order.order_fields` (динамические поля) | ✅ Есть | `modules/orders/models.py` |
| Condition engine (`core/conditions/`) | ✅ Есть | `core/conditions/interpreter.py` |
| `reminder_instructions` injection в pipeline | ✅ Есть | `agents/pipeline.py:236-237` |
| Поле "когда клиент последний раз писал" | ❌ Нет | Нужна миграция на `Thread` |
| Правила пингов на стадию | ❌ Нет | Новая модель `PingRule` |
| Ping Evaluator воркер | ❌ Нет | Новый воркер |
| Worker Hub | ❌ Нет | Обёртка над воркерами |
| Отмена пингов при ответе/смене стадии | ❌ Нет | Хуки в inbound + `update_stage` |

---

## Phase 1: Фундамент — Модели, Condition Engine, Миграция

**Модуль:** `apps/backend`

### Файлы

| Файл | Действие |
|---|---|
| `modules/pings/__init__.py` | **Создать** |
| `modules/pings/models.py` | **Создать** — модель `PingRule` |
| `modules/pings/enums.py` | **Создать** — `PingContentType` enum |
| `modules/pings/repository.py` | **Создать** — CRUD для правил пингов |
| `modules/pings/schemas.py` | **Создать** — Pydantic schemas для API |
| `modules/chat/models.py` | **Изменить** — добавить `last_customer_message_at` на `Thread` |
| `core/conditions/custom_ops.py` | **Изменить** — добавить `op_customer_silent_seconds` |
| `core/conditions/interpreter.py` | **Изменить** — зарегистрировать `$customer_silent_seconds` в `CUSTOM_OPERATORS` |
| `core/conditions/parser.py` | **Изменить** — добавить `$customer_silent_seconds` в `CUSTOM_OPERATORS` set |
| `modules/core/models.py` | **Изменить** — зарегистрировать `PingRule` |
| `migrations/models/` | **Создать** — Aerich миграция (не забыть `"backend".` префикс) |

### Модель `PingRule`

```python
class PingContentType(str, Enum):
    AI_GENERATED = "ai_generated"
    STATIC = "static"

class PingRule(BaseModel):
    id = fields.IntField(primary_key=True)
    company = fields.ForeignKeyField("models.Company", related_name="ping_rules", on_delete=fields.CASCADE)
    stage = fields.ForeignKeyField("models.StageTemplate", related_name="ping_rules", on_delete=fields.CASCADE)

    position = fields.IntField()  # порядок в цепочке: 1, 2, 3
    delay_seconds = fields.IntField()  # секунд после молчания клиента

    condition = fields.JSONField(null=True)  # mongo-like condition (same engine as stage transitions)

    content_type = fields.CharEnumField(PingContentType, max_length=20)
    static_content = fields.TextField(null=True)
    prompt_override = fields.TextField(null=True)

    is_active = fields.BooleanField(default=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta(BaseModel.Meta):
        table = "ping_rules"
        schema = "backend"
        unique_together = (("stage", "position"),)
        indexes = (("company_id", "stage_id"),)
```

`condition` — опциональное mongo-like условие поверх базового `delay_seconds`. Level 1: `null` (только время). Level 2: `{"order_fields.follow_up_date": {"$lte": "now"}}`.

`delay_seconds` — всегда базовый триггер. Evaluator сначала проверяет `silence >= delay_seconds`, потом (если задан) `evaluate_condition(rule.condition, context)`.

### Custom operator `$customer_silent_seconds`

```python
def op_customer_silent_seconds(value: int, ctx: dict) -> bool:
    last_msg = ctx.get("last_customer_message_at")
    if not last_msg:
        return False
    silence = (now - last_msg).total_seconds()
    return silence >= value
```

Регистрируется в `CUSTOM_OPERATORS` и `parser.CUSTOM_OPERATORS`.

### Поле `last_customer_message_at` на `Thread`

```python
last_customer_message_at = fields.DatetimeField(null=True)
```

Обновляется в `inbound_message` роутере когда `role == USER` и `is_historical == False`.

### Зависимости для следующих фаз
- `PingRule` модель — Phase 2 (API), Phase 3 (evaluator)
- `Thread.last_customer_message_at` — Phase 3 (evaluator), Phase 4 (hooks)
- `$customer_silent_seconds` operator — Phase 3 (evaluator, если condition задан)

---

## Phase 2: CRUD API для правил пингов

**Модуль:** `apps/backend`

### Файлы

| Файл | Действие |
|---|---|
| `modules/pings/routers.py` | **Создать** — CRUD эндпоинты |
| `modules/pings/service.py` | **Создать** — бизнес-логика |
| `modules/pings/dependencies.py` | **Создать** — FastAPI Annotated dependencies |
| Файл регистрации роутеров | **Изменить** — подключить `pings` роутер |

### API Эндпоинты

```
GET    /companies/{company_id}/stages/{stage_id}/pings     — список правил стадии
POST   /companies/{company_id}/stages/{stage_id}/pings     — создать правило
PATCH  /companies/{company_id}/pings/{ping_id}             — обновить правило
DELETE /companies/{company_id}/pings/{ping_id}             — удалить правило
POST   /companies/{company_id}/stages/{stage_id}/pings/reorder — изменить порядок
```

### Валидации
- `stage.is_final == True` → 400, пинги на финальных стадиях запрещены
- `position` > 5 → 400, лимит 5 правил на стадию
- `condition` → `validate_condition()` из `core/conditions` (бесплатно)
- `content_type == STATIC` и `static_content is None` → 400
- `stage.company_id != company_id` → 404

### Зависимости
- Phase 1: `PingRule`, schemas, condition validation

---

## Phase 3: Worker Hub + Ping Evaluator

**Модуль:** `apps/backend`

### Файлы

| Файл | Действие |
|---|---|
| `workers/hub.py` | **Создать** — Worker Hub: единый entry point с реестром, читает `WORKERS` env var |
| `workers/base.py` | **Создать** — базовый класс `BaseWorker` (async loop + poll interval + name) |
| `workers/task_scheduler.py` | **Изменить** — рефакторинг под `BaseWorker` interface (сохранить `__main__` для обратной совместимости) |
| `workers/ping_evaluator.py` | **Создать** — Ping Evaluator воркер |
| `modules/pings/evaluator.py` | **Создать** — бизнес-логика evaluator |
| `modules/tasks/models.py` | **Изменить** — добавить `ping_rule_id` nullable FK на `Task` |
| `modules/tasks/repository.py` | **Изменить** — `has_pending_ping()`, `cancel_pending_pings_for_order()` |
| `docker-compose.yml` | **Изменить** — заменить сервис `task-scheduler` на `worker-hub` с `WORKERS=all` |
| `justfile` | **Изменить** — заменить `task-scheduler)` case на `workers)` → `WORKERS=all python -m src.backend.workers.hub` |

### BaseWorker

```python
class BaseWorker(ABC):
    name: str
    poll_interval_seconds: int

    @abstractmethod
    async def tick(self) -> None: ...

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception(f"{self.name}.tick.error")
            await asyncio.sleep(self.poll_interval_seconds)
```

### Worker Hub

```python
WORKER_REGISTRY: dict[str, type[BaseWorker]] = {
    "task_scheduler": TaskSchedulerWorker,
    "ping_evaluator": PingEvaluatorWorker,
}

async def main():
    worker_names = parse_workers_env()  # WORKERS env var: "all" or comma-separated
    # shared bootstrap: db init, services
    workers = [WORKER_REGISTRY[name](...) for name in worker_names]
    await asyncio.gather(*(w.run() for w in workers))
```

Конфигурация через `WORKERS` env var (default: `"all"`). Пример `.env`:
```
WORKERS=all                    # dev
WORKERS=task_scheduler         # prod replica 1
WORKERS=ping_evaluator         # prod replica 2
```

docker-compose (dev): один сервис `worker-hub` с `WORKERS=all` и command `python -m src.backend.workers.hub`, заменяет текущий `task-scheduler` сервис. В prod/staging — отдельные сервисы или k8s Deployment-ы с разными `WORKERS` значениями и независимыми replicas.

justfile: `just dev workers` запускает hub с `WORKERS=all`. Замена текущего `just dev task-scheduler`.

### Алгоритм Ping Evaluator (`evaluator.py`)

```
poll interval: 60 секунд

1. Найти активные threads:
   Thread.filter(
     active_order__isnull=False,
     active_order__closed_at__isnull=True,
     active_order__frozen=False,
     last_customer_message_at__isnull=False,
     state__not_in=[CLOSED, HANDOFF],
     assistant_active=True,
   ).select_related("active_order__stage")

2. Для каждого thread (батчами по 100):
   order = thread.active_order
   if not order.stage_id: continue

   # Правило приоритета: если есть агентский followup reminder — skip
   if await task_repo.has_pending_agent_followup(order.id): continue

   rules = PingRule.filter(stage_id=order.stage_id, is_active=True).order_by("position")
   silence_seconds = (now - thread.last_customer_message_at).total_seconds()

   for rule in rules:
     if silence_seconds < rule.delay_seconds: continue
     if await task_repo.has_pending_ping(order.id, rule.id): continue

     # Опциональная condition check (Level 2)
     if rule.condition:
       ctx = build_condition_context(order, thread)
       if not evaluate_condition(rule.condition, ctx): continue

     await task_repo.create_order_task(
       company_id=order.company_id,
       order_id=order.id,
       title=f"Auto-ping #{rule.position} for stage '{order.stage.name}'",
       due_date=now,
       type=TaskType.AI_SCHEDULED,
       auto_action="send_followup_message",
       ping_rule_id=rule.id,
     )
```

### `has_pending_agent_followup(order_id)` — ключевой метод

```python
async def has_pending_agent_followup(self, order_id: int) -> bool:
    """Check if order has a pending followup reminder created by agent (not auto-ping).

    Only SEND_FOLLOWUP_MESSAGE tasks suppress auto-pings.
    Other auto_action types (future) do not affect the ping chain.
    """
    return await self.model.filter(
        subject_type=TaskSubjectType.ORDER,
        subject_id=order_id,
        type=TaskType.AI_SCHEDULED,
        auto_action=TaskAutoAction.SEND_FOLLOWUP_MESSAGE,
        ping_rule_id__isnull=True,  # agent-created, not auto-ping
        completed=False,
        cancelled_at__isnull=True,
    ).exists()
```

### Дедупликация
- `has_pending_ping(order_id, rule_id)` — `Task.filter(subject_id=order_id, ping_rule_id=rule_id, completed=False, cancelled_at__isnull=True).exists()`
- Индекс: `(subject_id, ping_rule_id)` на таблице `tasks`

### Зависимости
- Phase 1: `PingRule`, `Thread.last_customer_message_at`, condition engine
- Phase 2: правила существуют в БД

---

## Phase 4: Lifecycle Hooks (Отмена пингов)

**Модуль:** `apps/backend`

### Файлы

| Файл | Действие |
|---|---|
| `modules/messages/routers.py` | **Изменить** — при `role=USER`: обновить `last_customer_message_at` + отменить pending пинги |
| `modules/orders/repository.py` | **Изменить** — в `update_stage()`: отменить pending пинги старой стадии |
| `modules/pings/service.py` | **Изменить** — `cancel_pending_pings(order_id, stage_id=None)` |
| `workers/task_executor.py` | **Изменить** — guard: перед отправкой пинга проверить что клиент всё ещё молчит |

### Триггеры отмены

1. **Клиент ответил** → в `inbound_message` после сохранения сообщения:
   ```python
   if envelope.role == MessageRole.USER and not envelope.is_historical:
       await Thread.filter(id=thread.id).update(last_customer_message_at=datetime.now(UTC))
       if thread.active_order_id:
           await ping_service.cancel_pending_pings(order_id=thread.active_order_id)
   ```

2. **Стадия изменилась** → в `OrdersRepository.update_stage()`:
   ```python
   await ping_service.cancel_pending_pings(order_id=order.id, stage_id=previous_stage_id)
   ```

3. **Guard в executor** — перед отправкой пинга (если `task.ping_rule_id` is not None):
   - Проверить `thread.last_customer_message_at > task.created_at` → клиент ответил после постановки → cancel
   - Проверить `thread.assistant_active == False` → бот отключён → cancel
   - Проверить `thread.state in (HANDOFF, CLOSED)` → не отправлять → cancel

### Зависимости
- Phase 1: `last_customer_message_at`
- Phase 3: `ping_rule_id` на Task, `cancel_pending_pings`

---

## Phase 5: AI-Генерация контента пинга (Sales Agent)

**Модуль:** `apps/sales-agent` + `apps/backend`

### Файлы

| Файл | Действие |
|---|---|
| `apps/backend/workers/task_executor.py` | **Изменить** — для ping-задач: загрузить `PingRule`, передать `prompt_override` и `content_type` |
| `apps/backend/modules/pings/service.py` | **Изменить** — метод `get_rule_for_task(ping_rule_id)` |
| `libs/common/src/common/models/outbound.py` | **Изменить** — добавить `ping_context` (опционально) в `TaskExecutionRequest` |

### Два режима контента

1. **`AI_GENERATED`** — executor передаёт `prompt_override` (или дефолтный промт) как `title`/`description` в `TaskExecutionRequest`. На стороне sales-agent это уже работает: `format_reminder_prompt(title, description)` → `reminder_instructions` → инжектится в `dynamic_context`. Базовый `agent.md` не меняется.

2. **`STATIC`** — executor отправляет `PingRule.static_content` напрямую через transport (`POST /internal/messages/outbound`), **минуя sales-agent**. Экономия на LLM-вызове.

### Зависимости
- Phase 3: `ping_rule_id` на Task
- Phase 1: `PingRule.content_type`, `static_content`, `prompt_override`

---

## Технические риски

| Риск | Митигация |
|---|---|
| Race condition: несколько реплик evaluator ставят один пинг дважды | Unique partial index `(subject_id, ping_rule_id) WHERE completed=FALSE AND cancelled_at IS NULL` + Redis SETNX lock на evaluator tick |
| Клиент ответил между созданием Task и выполнением | Guard в executor: `last_customer_message_at > task.created_at` → cancel |
| Evaluator тяжёлый при 10k+ активных тредов | Курсорная пагинация батчами по 100, prefetch правил по `stage_id` |
| Пинг уходит на закрытый/frozen заказ | Фильтры в evaluator + guard в executor |
| `reminder.md` был случайно удалён | Восстановлен из git history (commit `1473b58`, удалён в `7e44ed3`) |

---

## Рекомендуемая модель для выполнения

**Claude Opus 4.6**

Обоснование:
- **3+ модуля затронуты**: `apps/backend` (модели, миграции, condition engine, воркер, API, lifecycle hooks), `apps/sales-agent` (промт-контекст), `libs/common` (shared models)
- **Новая архитектура**: Worker Hub — рефакторинг существующего scheduler + новый evaluator
- **Risk level высокий**: миграция БД, race conditions, lifecycle hooks в критических путях (inbound message, stage change)
- **Расширение condition engine**: добавление custom operator в существующий движок требует аккуратности
