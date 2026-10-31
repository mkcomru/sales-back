# Plan 022 — Custom Stages & Auto-Transitions Implementation

## Objective

Реализовать систему кастомных стадий воронки продаж с автоматическими переходами на основе условий, заданных в MongoDB-like синтаксисе. Каждая компания сможет создавать свои стадии и настраивать правила автоматического движения заказов по воронке.

---

## Current State

### Модель Order с фиксированными стадиями

```python
# apps/backend/src/backend/modules/orders/models.py
class OrderStage(str, Enum):
    NEW = "new"
    QUALIFICATION = "qualification"
    OFFER = "offer"
    NEGOTIATION = "negotiation"
    CLOSED = "closed"

class Order(BaseModel):
    stage = fields.CharEnumField(OrderStage, max_length=30, default=OrderStage.NEW)
    order_fields = fields.JSONField(default=dict)  # Заполняет AI/менеджер
    # ... другие поля
```

### Проблемы

1. **Жёсткие стадии для всех компаний** — нет возможности настроить свою воронку
2. **Ручное управление** — стадии меняются только вручную (менеджер или AI tool)
3. **Нет автоматизации** — система не может автоматически двигать заказ по воронке при заполнении полей
4. **Нет истории стадий для условий** — невозможно проверить "заказ был на стадии X"

---

## Target Architecture

### Концептуальная модель

```
Company (1) ──┬──→ (N) StageTemplate
              │       ├─ name, color, position
              │       ├─ is_final, result (WON/LOST)
              │       ├─ auto_close
              │       └─ transition_condition (JSON)
              │
              └──→ (N) Order
                      ├─ stage → StageTemplate (nullable)
                      ├─ frozen (bool)
                      ├─ order_fields (JSON)
                      └─ customer → Customer
                                    └─ customer_fields (JSON)

OrderLog ─┬─ STAGE_CHANGE (откуда/куда, trigger)
          ├─ FIELD_CHANGE
          └─ ...
```

### Ключевые инварианты

1. **Order.stage → StageTemplate FK** (nullable если стадию удалили)
2. **Автопереходы только вперёд** — `new_position > current_position`
3. **Frozen блокирует автопереходы** — Order.frozen = True
4. **Условия проверяются при:**
   - Изменении order_fields
   - Изменении customer_fields (все активные заказы клиента)
   - Создании заказа (определение начальной стадии)
5. **Приоритет по position** — первая подходящая стадия побеждает

---

## Implementation Plan

### Phase 0: Conditions Engine (Изолированный модуль)

**Goal:** Создать парсер и интерпретатор MongoDB-like условий.

#### 0.1. Создать модуль conditions

```
apps/backend/src/backend/core/conditions/
├── __init__.py
├── operators.py       # Базовые операторы ($and, $or, $eq, etc.)
├── custom_ops.py      # $stage_completed, $prev_stage_completed
├── parser.py          # Валидация синтаксиса JSON условий
├── interpreter.py     # Вычисление условий на Python объектах
└── exceptions.py      # ConditionSyntaxError, ConditionEvaluationError
```

- [ ] Создать структуру модуля
- [ ] Реализовать базовые операторы: `$and`, `$or`, `$not`, `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$exists`
- [ ] Реализовать кастомные операторы: `$stage_completed`, `$prev_stage_completed`, `$any` (fallback)
- [ ] Парсер должен валидировать JSON при сохранении стадии
- [ ] Интерпретатор принимает контекст: `{order_fields: {...}, customer_fields: {...}, completed_stages: [...]}`

**Пример условия:**
```json
{
  "$and": [
    {"order_fields.budget": {"$gte": 1000}},
    {"customer_fields.city": {"$exists": true}},
    {"$stage_completed": "stage_id_qualification"}
  ]
}
```

#### 0.2. Написать юнит-тесты для conditions

```
apps/backend/tests/domains/conditions/
├── test_basic_operators.py
├── test_custom_operators.py
├── test_parser.py
└── test_interpreter.py
```

- [ ] Тесты на все базовые операторы
- [ ] Тесты на кастомные операторы
- [ ] Тесты на валидацию (некорректный JSON)
- [ ] Тесты на edge cases (пустые условия, вложенность)

---

### Phase 1: StageTemplate Model & CRUD

**Goal:** Создать модель и API для управления стадиями.

#### 1.1. Создать модуль stages

```
apps/backend/src/backend/modules/stages/
├── __init__.py
├── models.py          # StageTemplate
├── schemas.py         # Pydantic schemas
├── repository.py      # StagesRepository
├── service.py         # StagesService
├── routers.py         # CRUD endpoints
└── dependencies.py    # StagesServiceDep
```

**StageTemplate модель:**
```python
class StageTemplate(BaseModel):
    id = fields.IntField(primary_key=True)
    company: fields.ForeignKeyRelation  # → Company
    
    name = fields.CharField(max_length=255)
    color = fields.CharField(max_length=7, null=True)  # HEX color
    position = fields.IntField()  # Порядок в воронке
    
    is_final = fields.BooleanField(default=False)
    result = fields.CharEnumField(OrderResult, null=True)  # WON/LOST для финальных
    auto_close = fields.BooleanField(default=False)  # Автозакрытие при переходе
    
    transition_condition = fields.JSONField(null=True)  # MongoDB-like JSON
    
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "stage_templates"
        schema = "backend"
        unique_together = (("company", "position"),)
        indexes = (("company_id", "position"),)
```

**Constraints:**
- `result` должен быть заполнен если `is_final=True`
- `auto_close` допустим только если `is_final=True`

- [ ] Создать модель StageTemplate
- [ ] Создать миграцию через aerich
- [ ] Добавить constraints в миграцию вручную

#### 1.2. Валидация transition_condition при сохранении

- [ ] В `StagesService.create_stage()` — вызвать `conditions.parser.validate(transition_condition)`
- [ ] В `StagesService.update_stage()` — то же самое
- [ ] Если валидация не прошла — вернуть HTTP 400 с деталями ошибки

#### 1.3. CRUD endpoints для StageTemplate

```python
# apps/backend/src/backend/modules/stages/routers.py

GET    /companies/{company_id}/stages           # Список стадий (sorted by position)
POST   /companies/{company_id}/stages           # Создать стадию
PATCH  /companies/{company_id}/stages/{id}      # Обновить стадию
DELETE /companies/{company_id}/stages/{id}      # Удалить стадию
PUT    /companies/{company_id}/stages/reorder   # Изменить порядок (массив ID)
```

- [ ] Реализовать endpoints
- [ ] GET возвращает стадии отсортированные по position
- [ ] POST присваивает position = max(position) + 1
- [ ] PUT reorder принимает `{"stage_ids": [3, 1, 2]}` и присваивает position = index
- [ ] DELETE не каскадно удаляет Order (Order.stage = NULL)

---

### Phase 2: Изменить Order Model

**Goal:** Order ссылается на StageTemplate, добавить frozen флаг.

#### 2.1. Изменить Order.stage

```python
# apps/backend/src/backend/modules/orders/models.py

# УДАЛИТЬ enum OrderStage (перенести в stages/models.py если нужен для backward compat)

class Order(BaseModel):
    # Было:
    # stage = fields.CharEnumField(OrderStage, max_length=30, default=OrderStage.NEW)
    
    # Стало:
    stage: fields.ForeignKeyNullableRelation = fields.ForeignKeyField(
        "models.StageTemplate",
        related_name="orders",
        on_delete=fields.SET_NULL,
        null=True,
    )
    frozen = fields.BooleanField(default=False)  # Блокирует автопереходы
    
    # ... остальные поля без изменений
```

- [ ] Изменить Order.stage на FK → StageTemplate
- [ ] Добавить Order.frozen
- [ ] Создать миграцию через aerich
- [ ] Добавить индекс на (company_id, stage_id, frozen, closed_at) для запросов автопереходов

#### 2.2. Обновить OrderLog.STAGE_CHANGE

```python
# data для STAGE_CHANGE теперь:
{
    "from_stage_id": int | None,
    "to_stage_id": int | None,
    "trigger": "manual" | "auto" | "system"
}
```

- [ ] Обновить `OrdersRepository.update_stage()` — теперь stage это StageTemplate
- [ ] Логировать stage_id вместо enum значения
- [ ] Добавить миграцию данных OrderLog если нужна (скорее всего нет, прод пустой)

---

### Phase 3: Дефолтные стадии при создании компании

**Goal:** При создании Company автоматически создаются стартовые стадии.

#### 3.1. Функция создания дефолтных стадий

```python
# apps/backend/src/backend/modules/stages/service.py

async def create_default_stages(self, company_id: int) -> list[StageTemplate]:
    """Create default stage funnel for new company."""
    defaults = [
        {"name": "Новый", "position": 0, "color": "#64748b", "transition_condition": {"$any": true}},
        {"name": "Квалификация", "position": 1, "color": "#3b82f6", "transition_condition": None},
        {"name": "Предложение", "position": 2, "color": "#f59e0b", "transition_condition": None},
        {"name": "Закрыто (успешно)", "position": 3, "color": "#10b981", "is_final": True, "result": "won", "auto_close": True, "transition_condition": None},
        {"name": "Отказ", "position": 4, "color": "#ef4444", "is_final": True, "result": "lost", "auto_close": True, "transition_condition": None},
    ]
    # ... создать стадии
```

- [ ] Реализовать `create_default_stages()`
- [ ] Вызвать из `CompanyService.create_company()`
- [ ] Первая стадия имеет `transition_condition: {"$any": true}` — fallback для новых заказов

---

### Phase 4: Логика автопереходов

**Goal:** Автоматически двигать заказы по воронке при изменении полей.

#### 4.1. Функция проверки и перехода

```python
# apps/backend/src/backend/modules/orders/service.py

async def recalculate_stage(self, order_id: int) -> Order:
    """
    Пересчитать стадию заказа на основе transition_condition всех стадий компании.
    
    Алгоритм:
    1. Если order.frozen — ничего не делать
    2. Загрузить все стадии компании (sorted by position)
    3. Загрузить completed_stages из OrderLog (type=STAGE_CHANGE)
    4. Собрать контекст: {order_fields, customer_fields, completed_stages}
    5. Проверить стадии от position > current_position
    6. Первая подходящая — переход
    7. Если is_final + auto_close — закрыть заказ
    """
    pass
```

- [ ] Реализовать `OrdersService.recalculate_stage()`
- [ ] Проверка frozen в начале функции
- [ ] Загрузка completed_stages из OrderLog
- [ ] Использовать `conditions.interpreter.evaluate(condition, context)`
- [ ] Переход только вперёд: `new_stage.position > current_stage.position`
- [ ] Логирование через OrderLog с trigger="auto"
- [ ] Если auto_close — вызвать `OrdersRepository.close_order()`

#### 4.2. Триггеры для автопереходов

```python
# apps/backend/src/backend/modules/orders/service.py

async def update_order_fields(
    self, order_id: int, fields_update: dict, author_id: int | None = None
) -> Order:
    """Update order fields and trigger stage recalculation."""
    order = await self.repo.update_fields(order, fields_update, author_id)
    
    # Trigger auto-transition
    if not order.frozen:
        order = await self.recalculate_stage(order.id)
    
    return order
```

- [ ] Добавить вызов `recalculate_stage()` после `update_order_fields()`
- [ ] Добавить вызов после изменения customer_fields для всех активных заказов клиента
- [ ] Добавить вызов при создании заказа (определение начальной стадии)

#### 4.3. Пересчёт при изменении customer_fields

```python
# apps/backend/src/backend/modules/chat/service.py

async def update_customer_fields(
    self, customer_id: int, fields_update: dict
) -> Customer:
    """Update customer fields and recalculate stages for all active orders."""
    customer = await self.customers_repo.update_fields(customer_id, fields_update)
    
    # Trigger stage recalculation for all active orders
    active_orders = await Order.filter(
        customer_id=customer_id,
        closed_at__isnull=True
    ).all()
    
    for order in active_orders:
        if not order.frozen:
            await self.orders_service.recalculate_stage(order.id)
    
    return customer
```

- [ ] Реализовать пересчёт для всех активных заказов при изменении customer_fields
- [ ] Добавить в ChatService или создать отдельный CustomerService

---

### Phase 5: Управляющие Endpoints

**Goal:** Ручной контроль за автопереходами.

#### 5.1. Recalculate endpoints

```python
# apps/backend/src/backend/modules/orders/routers.py

POST /orders/{order_id}/recalculate-stage
# Пересчитать стадию для одного заказа

POST /companies/{company_id}/stages/recalculate
# Пересчитать стадии для всех активных заказов компании
```

- [ ] Реализовать `/orders/{id}/recalculate-stage` — вызывает `recalculate_stage()`
- [ ] Реализовать `/companies/{id}/stages/recalculate` — массовый пересчёт
- [ ] Требуется роль менеджера компании

#### 5.2. Stage requirements endpoint

```python
POST /orders/{order_id}/stage-requirements
Response: {
    "current_stage": {...},
    "next_stages": [
        {
            "stage": {...},
            "missing_fields": ["budget", "dates"],
            "condition_status": "partial"  # "met" | "partial" | "blocked"
        }
    ]
}
```

- [ ] Реализовать анализ условий следующих стадий
- [ ] Показать какие поля нужно заполнить для перехода
- [ ] Используется для UI подсказок менеджеру

#### 5.3. Freeze/Unfreeze order

```python
PATCH /orders/{order_id}/frozen
Body: {"frozen": true}
```

- [ ] Реализовать endpoint для изменения Order.frozen
- [ ] Требуется роль менеджера компании

---

### Phase 6: Integration with AI Agent

**Goal:** AI не управляет стадиями напрямую, только заполняет поля.

#### 6.1. Обновить AI tool update_order_fields

```python
# apps/sales-agent/src/sales_agent/agents/tools.py

async def set_order_fields(
    order_id: int,
    updates: dict[str, Any],
    company_id: int | None = None,
) -> OrderFieldsUpdateResponse:
    """
    Update order fields.
    
    AICODE-NOTE: Stage transitions happen automatically based on field values.
    AI does not control stage directly - just fill the fields.
    """
    # Call backend /orders/{id}/fields
    # Backend triggers recalculate_stage automatically
```

- [ ] AI не вызывает `update_stage` tool напрямую (можно deprecate)
- [ ] AI только заполняет поля через `set_order_fields`
- [ ] Backend автоматически пересчитает стадию

#### 6.2. Добавить текущую стадию в промпт

```python
# apps/sales-agent/src/sales_agent/agents/pipeline.py

# В context для AI добавить:
current_stage = order.stage.name if order.stage else "Без стадии"
```

- [ ] AI видит название текущей стадии
- [ ] AI НЕ видит условия переходов (не нужны ему)

---

### Phase 7: Testing

#### 7.1. Unit tests

```
apps/backend/tests/unit/stages/
├── test_stage_crud.py
├── test_default_stages.py
└── test_stage_validation.py

apps/backend/tests/unit/orders/
├── test_auto_transitions.py
├── test_frozen_orders.py
└── test_stage_requirements.py
```

- [ ] Тесты CRUD операций для StageTemplate
- [ ] Тесты валидации transition_condition
- [ ] Тесты автопереходов (простые сценарии)
- [ ] Тесты frozen блокирует переходы
- [ ] Тесты пересчёта при изменении customer_fields

#### 7.2. Integration tests

```
apps/backend/tests/integration/stages/
├── test_full_funnel_flow.py
├── test_complex_conditions.py
└── test_stage_history.py
```

- [ ] Тест: создание компании → дефолтные стадии
- [ ] Тест: создание заказа → попадает на начальную стадию
- [ ] Тест: заполнение полей → автопереход
- [ ] Тест: условие с $stage_completed
- [ ] Тест: условие с $prev_stage_completed
- [ ] Тест: финальная стадия с auto_close
- [ ] Тест: удаление стадии → order.stage = NULL

---

### Phase 8: Documentation

#### 8.1. Обновить docs/

- [ ] Создать `docs/stages-system.md` — описание системы стадий
- [ ] Создать `docs/transition-conditions.md` — синтаксис условий с примерами
- [ ] Обновить `docs/architecture.md` — добавить раздел про StageTemplate

#### 8.2. API Documentation

- [ ] OpenAPI схемы для всех новых endpoints
- [ ] Примеры transition_condition в документации

---

## Migration Strategy

### Существующие Order с enum stage

**Проблема:** Order.stage сейчас enum, а станет FK → StageTemplate

**Решение:**
1. При создании компании создаются дефолтные стадии
2. Существующие Order получают `stage=NULL` после миграции
3. Ручной скрипт для назначения стадий (если прод не пустой):
   ```python
   # Для каждого Order найти соответствующую StageTemplate по старому enum значению
   # Назначить stage_id
   ```

- [ ] Создать миграционный скрипт `scripts/migrate_order_stages.py`
- [ ] Запустить после деплоя миграций БД
- [ ] Протестировать на staging

---

## Risks & Open Questions

### Risks

1. **Performance:** Пересчёт стадий при каждом изменении customer_fields может быть медленным
   - Mitigation: Индексы, ограничить только на активные заказы
   
2. **Сложность условий:** Пользователи могут создавать противоречивые условия
   - Mitigation: Превалидация в UI, документация с примерами
   
3. **Race conditions:** Параллельные обновления order_fields могут вызвать конфликты
   - Mitigation: Использовать SELECT FOR UPDATE при recalculate

### Open Questions

- [ ] **UI для создания условий:** Визуальный редактор или JSON editor?
  - Решение: Backend даёт API, UI на усмотрение фронтенда
  
- [ ] **Лимит на количество стадий:** Ограничивать ли количество стадий на компанию?
  - Решение: Нет лимита, но рекомендация в документации (5-10 стадий)

- [ ] **Кеширование стадий:** Стадии редко меняются, нужно ли кешировать?
  - Решение: Пока нет, добавить при необходимости

---

## Success Criteria

- [ ] Компания может создавать/редактировать свои стадии
- [ ] Условия валидируются при сохранении
- [ ] Заказы автоматически двигаются по воронке при заполнении полей
- [ ] Менеджер может заморозить заказ (отключить автопереходы)
- [ ] Финальные стадии с auto_close закрывают заказ
- [ ] История переходов логируется в OrderLog
- [ ] Endpoint показывает недостающие поля для следующих стадий
- [ ] AI заполняет поля, система сама меняет стадии
- [ ] Все операции покрыты тестами
- [ ] Документация описывает синтаксис условий и примеры

---

## Timeline Estimate

- Phase 0 (Conditions Engine): **2-3 дня**
- Phase 1 (StageTemplate CRUD): **2 дня**
- Phase 2 (Order Model Changes): **1 день**
- Phase 3 (Default Stages): **1 день**
- Phase 4 (Auto-transitions Logic): **3-4 дня**
- Phase 5 (Management Endpoints): **2 дня**
- Phase 6 (AI Integration): **1 день**
- Phase 7 (Testing): **3-4 дня**
- Phase 8 (Documentation): **1 день**

**Total: ~15-20 рабочих дней**

