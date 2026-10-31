# 015 — Field Level Separation: Customer vs Order Fields

## Objective

Расширить существующую модель `Field` для поддержки двух уровней полей:
- **Customer-level** — информация о клиенте (постоянная, переиспользуется между заказами)
- **Order-level** — информация о конкретном заказе/сделке

Подход: добавить `level` enum в существующую модель Field вместо создания двух отдельных моделей.

Это соответствует Phase 2 из плана V4 (yoolo-requirements-product-v4.md, раздел "Разделение полей: Customer vs Order").

---

## Current State

### Существующая модель Field

```python
# apps/backend/src/backend/modules/forms/models.py
class Field(BaseModel):
    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=255)
    question = fields.TextField()
    answer_type = fields.CharEnumField(AnswerType, max_length=255)
    required = fields.BooleanField(default=False)
    display_name = fields.CharField(max_length=255, null=True)
    
    company: fields.ForeignKeyRelation  # Company
    category: fields.ForeignKeyRelation  # Category (nullable)
    product: fields.ForeignKeyRelation   # Product (nullable)
    
    options: fields.ReverseRelation  # FieldOption
```

### Хранение значений

```python
# apps/backend/src/backend/modules/chat/models.py
class Customer(BaseModel):
    quiz_answers = fields.JSONField(default=dict)  # Все ответы вместе
```

### Проблема

Текущая система не различает:
1. **Информацию о клиенте** (телефон, email, город, предпочтения) — постоянная
2. **Информацию о заказе** (куда едет, бюджет, даты) — относится к конкретной сделке

Клиент может создавать несколько заказов, и каждый заказ имеет свои параметры.

---

## Target State

### Расширенная модель Field

```python
class FieldLevel(str, Enum):
    """Field level - determines where values are stored."""
    CUSTOMER = "customer"  # Stored in Customer.customer_fields
    ORDER = "order"        # Stored in Order.order_fields


class Field(BaseModel):
    """Field template for collecting customer or order information."""
    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=255)
    question = fields.TextField()
    answer_type = fields.CharEnumField(AnswerType, max_length=255)
    required = fields.BooleanField(default=False)
    display_name = fields.CharField(max_length=255, null=True)
    
    # NEW: Level determines storage location
    level = fields.CharEnumField(FieldLevel, max_length=20, default=FieldLevel.CUSTOMER)
    
    # NEW: System fields (only for customer-level, e.g. phone, email)
    is_system = fields.BooleanField(default=False)
    
    company: fields.ForeignKeyRelation  # Company
    category: fields.ForeignKeyRelation  # Category (nullable)
    product: fields.ForeignKeyRelation   # Product (nullable)
    
    options: fields.ReverseRelation  # FieldOption (unchanged)
```

### Системные customer fields

**Встроенные поля для всех компаний (level=CUSTOMER, is_system=True):**
- `phone` — телефон
- `telegram` — Telegram username или ID
- `whatsapp` — WhatsApp номер
- `instagram` — Instagram username
- `email` — email
- `preferences` — личные предпочтения клиента
- `source` — источник (UTM или канал)

**Constraint:** `is_system=True` допустим только при `level=CUSTOMER`.

### Хранение значений

```python
class Customer(BaseModel):
    customer_fields = fields.JSONField(default=dict)  # Customer-level поля
    quiz_answers = fields.JSONField(default=dict)      # Deprecated, для обратной совместимости

class Order(BaseModel):
    order_fields = fields.JSONField(default=dict)      # Order-level поля (уже существует)
```

---

## Implementation Plan

### Phase 1: Extend Field Model

**1.1. Добавить новые колонки в Field**
- [ ] Добавить `FieldLevel` enum в `apps/backend/src/backend/modules/forms/models.py`
- [ ] Добавить `level` колонку (default: `CUSTOMER`)
- [ ] Добавить `is_system` колонку (default: `False`)

**1.2. Создать миграцию через Aerich**
```bash
cd apps/backend
uv run aerich migrate --name add_field_level_and_is_system
```

После генерации добавить вручную constraint:
```sql
-- Add constraint: is_system only allowed for customer-level fields
ALTER TABLE "backend"."fields"
ADD CONSTRAINT "chk_is_system_customer_only" 
CHECK (level = 'customer' OR is_system = False);
```

**1.3. FieldOption остаётся без изменений**
- Опции работают для обоих уровней одинаково
- Нет необходимости в отдельных таблицах

---

### Phase 2: Mark Existing Fields as Customer-Level

**2.1. Обновить существующие поля**
- [ ] Все существующие Field автоматически получают `level=customer` (через default)
- [ ] Никакой миграции данных не требуется

**2.2. Обновить код модели**
- [ ] Добавить `FieldLevel` enum
- [ ] Добавить поля `level` и `is_system` в модель Field

---

### Phase 3: Create System Customer Fields

**3.1. Константа системных полей**
```python
# apps/backend/src/backend/modules/forms/constants.py
SYSTEM_CUSTOMER_FIELDS = [
    {
        "name": "phone",
        "question": "Phone number",
        "answer_type": AnswerType.STRING,
        "required": False,
        "display_name": "Phone",
        "level": FieldLevel.CUSTOMER,
        "is_system": True,
    },
    {
        "name": "telegram",
        "question": "Telegram username or ID",
        "answer_type": AnswerType.STRING,
        "required": False,
        "display_name": "Telegram",
        "level": FieldLevel.CUSTOMER,
        "is_system": True,
    },
    {
        "name": "whatsapp",
        "question": "WhatsApp number",
        "answer_type": AnswerType.STRING,
        "required": False,
        "display_name": "WhatsApp",
        "level": FieldLevel.CUSTOMER,
        "is_system": True,
    },
    {
        "name": "instagram",
        "question": "Instagram username",
        "answer_type": AnswerType.STRING,
        "required": False,
        "display_name": "Instagram",
        "level": FieldLevel.CUSTOMER,
        "is_system": True,
    },
    {
        "name": "email",
        "question": "Email address",
        "answer_type": AnswerType.STRING,
        "required": False,
        "display_name": "Email",
        "level": FieldLevel.CUSTOMER,
        "is_system": True,
    },
    {
        "name": "preferences",
        "question": "Customer preferences and notes",
        "answer_type": AnswerType.STRING,
        "required": False,
        "display_name": "Preferences",
        "level": FieldLevel.CUSTOMER,
        "is_system": True,
    },
    {
        "name": "source",
        "question": "Traffic source (UTM or channel)",
        "answer_type": AnswerType.STRING,
        "required": False,
        "display_name": "Source",
        "level": FieldLevel.CUSTOMER,
        "is_system": True,
    },
]
```

**3.2. Создание системных полей при создании компании**
- [ ] Обновить `CompanyService.create_company()`
- [ ] Автоматически создавать SYSTEM_CUSTOMER_FIELDS для каждой новой компании

**3.3. Создать системные поля для существующих компаний (опционально)**
- [ ] Создать скрипт для добавления системных полей всем существующим компаниям (для тестовых данных)
- [ ] **Note:** Не критично — нет production окружения, новые компании будут создаваться с системными полями автоматически через Phase 3.2

---

### Phase 4: Update Customer Model

**4.1. Добавить customer_fields в Customer**
```python
class Customer(BaseModel):
    customer_fields = fields.JSONField(default=dict)  # NEW
    quiz_answers = fields.JSONField(default=dict)      # DEPRECATED
```

**4.2. Создать миграцию через Aerich**
```bash
cd apps/backend
uv run aerich migrate --name add_customer_fields
```

**Note:** Data migration не требуется — нет production окружения, новые Customer будут создаваться с пустым `customer_fields`, существующие тестовые данные можно игнорировать.

---

### Phase 5: Update Repositories & Services

**5.1. Обновить FieldsRepository**
```python
# apps/backend/src/backend/modules/forms/repository.py
class FieldsRepository(BaseRepository[Field]):
    # Existing methods stay unchanged
    
    async def list_by_company_and_level(
        self, company_id: int, level: FieldLevel
    ) -> list[Field]:
        """List fields filtered by level."""
        return await Field.filter(
            company_id=company_id, level=level
        ).prefetch_related("options").all()
    
    async def list_customer_fields(self, company_id: int) -> list[Field]:
        """List customer-level fields."""
        return await self.list_by_company_and_level(company_id, FieldLevel.CUSTOMER)
    
    async def list_order_fields(self, company_id: int) -> list[Field]:
        """List order-level fields."""
        return await self.list_by_company_and_level(company_id, FieldLevel.ORDER)
    
    async def get_system_fields(self, company_id: int) -> list[Field]:
        """Get system customer fields."""
        return await Field.filter(
            company_id=company_id,
            level=FieldLevel.CUSTOMER,
            is_system=True
        ).all()
```

**5.2. Обновить CustomersRepository**
```python
async def _ensure_all_fields_present(self, customer: Customer) -> bool:
    """Ensure customer has all customer-level fields in customer_fields."""
    fields = await Field.filter(
        company_id=customer.company_id, 
        level=FieldLevel.CUSTOMER
    ).all()
    customer_fields = customer.customer_fields or {}
    updated = False
    
    for field in fields:
        if field.name not in customer_fields:
            customer_fields[field.name] = None
            updated = True
    
    if updated:
        customer.customer_fields = customer_fields
    
    return updated
```

**5.3. Добавить OrdersRepository методы для order_fields backfill**
```python
async def _ensure_all_order_fields_present(self, order: Order) -> bool:
    """Ensure order has all order-level fields in order_fields."""
    fields = await Field.filter(
        company_id=order.company_id,
        level=FieldLevel.ORDER
    ).all()
    order_fields = order.order_fields or {}
    updated = False
    
    for field in fields:
        if field.name not in order_fields:
            order_fields[field.name] = None
            updated = True
    
    if updated:
        order.order_fields = order_fields
    
    return updated
```

**5.4. FieldsService остаётся единым**
- [ ] Добавить `level` параметр в методы создания/листинга
- [ ] Добавить валидацию: `is_system=True` только для `level=CUSTOMER`

---

### Phase 6: Update API Endpoints

**6.1. Расширить существующие endpoints**

Существующие endpoints остаются, добавляется query parameter `level`:
```
GET    /companies/{company_id}/fields?level=customer|order  # Filter by level
POST   /companies/{company_id}/fields                        # Include level in body
GET    /companies/{company_id}/fields/{field_id}
PATCH  /companies/{company_id}/fields/{field_id}
DELETE /companies/{company_id}/fields/{field_id}
```

Options endpoints без изменений (опции не зависят от level).

**6.2. Обновить схемы Pydantic**
```python
# apps/backend/src/backend/modules/forms/schemas.py

class FieldLevel(str, Enum):
    CUSTOMER = "customer"
    ORDER = "order"

class FieldRequest(BaseModel):
    name: str
    question: str
    type: str  # answer_type
    required: bool = False
    display_name: str | None = None
    level: FieldLevel = FieldLevel.CUSTOMER  # NEW
    is_system: bool = False  # NEW, only valid for CUSTOMER level
    category_id: int | None = None
    product_id: int | None = None

class FieldResponse(BaseModel):
    id: int
    name: str
    question: str
    type: str
    required: bool
    display_name: str | None
    level: FieldLevel  # NEW
    is_system: bool    # NEW
    category_id: int | None
    product_id: int | None
    options: list[FieldOptionResponse] = []
```

**6.3. Валидация в API**
- [ ] При создании: если `is_system=True`, то `level` должен быть `CUSTOMER`
- [ ] Системные поля (`is_system=True`) нельзя удалять
- [ ] При изменении level существующего поля — предупреждение (данные в старом storage останутся)

---

### Phase 7: Update Sales-Agent Integration

**7.1. Обновить company_spec**

Backend должен возвращать fields с указанием level:
```python
# Company spec response
{
    "fields": [
        {"name": "phone", "level": "customer", "is_system": true, ...},
        {"name": "city", "level": "customer", ...},
        {"name": "destination", "level": "order", ...},
        {"name": "budget", "level": "order", ...},
    ]
}
```

**7.2. Обновить валидацию в set_customer_fields**
```python
# apps/sales-agent/src/sales_agent/agents/tools.py

async def set_customer_fields(...):
    """Update customer-level fields (persistent across orders)."""
    # Фильтровать field_defs по level=customer
    customer_field_defs = {
        f.get("name"): f for f in all_fields 
        if f.get("level") == "customer"
    }
    # Валидировать только customer-level поля
    ...
```

**7.3. Добавить валидацию в update_order_fields**
```python
async def update_order_fields(order_id: int, fields: dict[str, Any]):
    """Update order-level fields (specific to current deal)."""
    # NEW: Валидировать против order-level field definitions
    order_field_defs = {
        f.get("name"): f for f in all_fields 
        if f.get("level") == "order"
    }
    # Применить ту же логику валидации enum что и для customer fields
    ...
```

**7.4. Обновить промпты**
- [ ] Добавить инструкции: customer fields = постоянная инфо о клиенте, order fields = детали текущего запроса
- [ ] Примеры: phone/email → customer, destination/budget/dates → order

---

### Phase 8: Update Tests

**8.1. Обновить существующие тесты**
- [ ] `test_fields_initialization.py` → добавить тесты для level filtering
- [ ] `test_routers.py` → добавить `?level=` query param тесты
- [ ] Обновить `quiz_answers` → `customer_fields` в fixtures

**8.2. Новые тесты для level separation**
- [ ] `test_field_level_constraint.py` — is_system только для customer level
- [ ] `test_order_fields_backfill.py` — backfill для order-level полей

**8.3. Тесты для системных полей**
- [ ] `test_system_customer_fields.py` — автосоздание при создании компании
- [ ] Тест: is_system=True нельзя удалить
- [ ] Тест: is_system=True нельзя установить для level=order

**8.4. Manual testing script**
- [ ] Создать `scripts/manual_testing/test_field_level_separation.py` (см. раздел "Manual Testing Script" ниже)

---

## Migration Strategy

### Database Migration Order (via Aerich)

1. `aerich migrate --name add_field_level_and_is_system` → добавить constraint вручную
2. `aerich migrate --name add_customer_fields` → миграция готова (data migration не требуется)
3. **Data script:** Создать системные поля для всех существующих компаний (опционально, для тестовых данных)

**Note:** Data migrations пропущены для упрощения — нет production окружения, поэтому:
- Существующие тестовые Customer могут иметь пустой `customer_fields` (не критично)
- Новые Customer будут создаваться с правильной структурой автоматически
- Системные поля будут создаваться для новых компаний автоматически

### Code Migration Order

1. Добавить `FieldLevel` enum и новые поля в модель Field
2. Обновить FieldsRepository с методами фильтрации по level
3. Обновить API endpoints (добавить `level` query param)
4. Обновить sales-agent: валидация с учётом level
5. Обновить промпты AI

### Обратная совместимость

- Существующие поля автоматически получают `level=customer` (default)
- `quiz_answers` остаётся как deprecated alias для `customer_fields`
- Existing endpoints работают без изменений (default `level=customer`)

---

## Risks & Open Questions

### Риски

1. **Обратная совместимость** — старый код может ломаться при переходе
   - Митигация: default `level=customer`, существующие поля не меняются
   
2. **Тестовые данные** — существующие Customer могут иметь пустой `customer_fields`
   - Митигация: не критично, нет production окружения, новые Customer создаются правильно

3. **Existing order_fields data** — уже есть данные без schema
   - Митигация: order_fields остаётся schemaless пока, templates добавляются постепенно

### Открытые вопросы

1. **Системные поля** — можно ли их редактировать/удалять?
   - Решение: `is_system=True` нельзя удалить, можно редактировать display_name/question

2. **Валидация order_fields** — добавлять ли validation как для customer fields?
   - Предложение: да, использовать ту же логику enum validation

3. **Category/Product scoping для order fields** — нужно ли?
   - Предложение: да, оставить — позволяет иметь разные поля для разных типов заказов

4. **Изменение level у существующего поля** — что делать с данными?
   - Предложение: запретить изменение level после создания (или предупреждать о потере данных)

---

## Acceptance Criteria

### Must Have

- [ ] Field модель расширена: `level` и `is_system` колонки добавлены
- [ ] Aerich миграции сгенерированы и применены без потери данных
- [ ] Системные customer fields создаются автоматически при создании компании
- [ ] Customer.customer_fields работает
- [ ] Order.order_fields backfill работает (для order-level полей)
- [ ] API endpoints поддерживают `?level=` filter
- [ ] Все существующие тесты проходят
- [ ] Constraint: is_system=True только для level=customer

### Should Have

- [ ] AI tools обновлены с валидацией по level
- [ ] Промпты обновлены с инструкциями (customer vs order fields)
- [ ] Новые тесты написаны и проходят

### Nice to Have

- [ ] Документация API обновлена
- [ ] Валидация order_fields (как для customer fields)

---

## Manual Testing Script (Ручное тестирование)

**Создать интерактивный тестовый скрипт:** `scripts/manual_testing/test_field_level_separation.py`

Следовать проверенному формату из `test_billing_migration.py` и `test_orders.py`:

**Сценарии для тестирования:**

1. **Создание системных полей** — проверить автосоздание системных customer fields при создании компании
2. **Фильтрация по level** — создать customer и order поля, проверить работу фильтрации
3. **Backfill customer fields** — создать customer, добавить новое customer-level поле, проверить backfill
4. **Backfill order fields** — создать order, добавить новое order-level поле, проверить backfill
5. **API фильтрация** — протестировать `?level=customer|order` query param на fields endpoint
6. **is_system constraint** — проверить что is_system=True допустим только для customer level
7. **Защита системных полей** — проверить что системные поля нельзя удалить
8. **Sales-Agent интеграция** — проверить что company_spec включает level info, tools валидируют корректно
9. **Обновление customer_fields** — обновить customer_fields через API, проверить сохранение
10. **Обновление order_fields** — обновить order_fields через API, проверить сохранение

**Структура скрипта:**
- Класс `FieldLevelTestClient` с методами для API вызовов
- `setup_environment()` — логин, создание/получение компании
- Отдельные функции сценариев (`scenario_1_system_fields`, и т.д.)
- Интерактивное меню с rich console выводом
- Форматированные таблицы для отображения полей/ответов
- Опция "Run All" для пакетного тестирования

**Использование:**
```bash
cd scripts/manual_testing
python test_field_level_separation.py
```

---

## References

- Plan 014: V4 Product Requirements (yoolo-requirements-product-v4.md) — Phase 2
- Current Field model: `apps/backend/src/backend/modules/forms/models.py`
- Current FieldsRepository: `apps/backend/src/backend/modules/forms/repository.py`
- Customer.quiz_answers usage: `apps/backend/src/backend/modules/chat/repository.py`
- Order.order_fields: `apps/backend/src/backend/modules/orders/models.py`
- AI tools: `apps/sales-agent/src/sales_agent/agents/tools.py`

