# Plan 024 — Web Form Capture Implementation

## Objective

Реализовать механизм захвата лидов с веб-форм — создание Customer и Order на основе данных формы с API key аутентификацией и UTM tracking. Подготовка инфраструктуры для будущей отправки первого сообщения агентом (outbound).

---

## Зачем это делаем

- **Проблема пользователя**: клиенты CRM собирают заявки через формы на своих сайтах, но лиды не попадают в CRM автоматически — приходится создавать контакты вручную
- **Ценность для продукта**: единая точка входа для лидов с форм — они сразу появляются в CRM с заполненными полями
- **Стратегическая цель**: минимальная единица, требующая "инициации диалога агентом" (outbound). После этой задачи — Contact Registry и умный матчинг

---

## Current State

### Существующая инфраструктура

1. **fields/ модуль** — управление `Field` и `FieldOption` (customer_fields/order_fields)
2. **ConnectorApiKey** — готовый паттерн для API key: `sk_<random>`, sha256 hash, enabled флаг
3. **Order.order_fields** — JSON поле для хранения значений (уже реализовано)
4. **Customer** — модель клиента с customer_fields (уже реализовано)

### Паттерн ConnectorApiKey (будет вынесен в общую абстракцию)

```python
# apps/backend/src/backend/modules/transport/models.py
class ConnectorApiKey(BaseModel):
    key_hash = fields.CharField(max_length=64, unique=True)
    connector: ForeignKeyRelation[Connector] = ...
    enabled = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
```

---

## Target Architecture

### Концептуальная модель

```
Company (1) ──┬──→ (N) FormTemplate
              │       ├─ name, enabled
              │       ├─ api_key_hash (sha256)
              │       ├─ contact_field → Field FK (nullable)
              │       └─ template_fields → FormTemplateField[]
              │
              └──→ (N) Field (уже имеет level: customer|order)
                      ↑
FormTemplateField ────┤ (M:N связь)
    ├─ form_template → FormTemplate FK
    ├─ field → Field FK
    └─ position: int (порядок в форме)
```

### Ключевые инварианты

1. **FormTemplate.api_key** — генерируется явным action, показывается один раз, хранится hash
2. **FormTemplateField** — связь M:N между FormTemplate и Field; `field.level` определяет customer/order
3. **Capture endpoint** — валидация по `required` флагам полей, CORS для любых origins
4. **Response modes** — `full` (все данные) и `minimal` (sensitive как null, default)

---

## Implementation Plan

### Phase 0: Подготовка — завершить rename forms → fields

**Goal:** Исправить незавершённый rename перед созданием нового `forms/` модуля.

**Проблема:** `fields/` модуль создан, но импорты не обновлены:
- `fields/routers.py` импортирует из `src.backend.modules.forms.*`
- `modules/__init__.py` импортирует из `src.backend.modules.forms.routers`

- [ ] Обновить импорты в `fields/routers.py`: `forms.*` → `fields.*`
- [ ] Обновить импорт в `modules/__init__.py`: `forms.routers` → `fields.routers`
- [ ] Переименовать `forms_router` → `fields_router` в `modules/__init__.py`

---

### Phase 1: Структура модуля forms

**Goal:** Создать модуль для веб-форм.

```
apps/backend/src/backend/modules/forms/
├── __init__.py
├── models.py          # FormTemplate, FormTemplateField
├── schemas.py         # Pydantic schemas
├── repository.py      # FormsRepository
├── service.py         # FormsService
├── routers.py         # CRUD + capture endpoints
├── dependencies.py    # FormsServiceDep
└── exceptions.py      # FormNotFoundError, InvalidFormKeyError
```

- [ ] Создать структуру модуля
- [ ] Зарегистрировать router в `modules/__init__.py`

---

### Phase 2: Models (FormTemplate, FormTemplateField, FormSubmission)

**Goal:** Создать модели данных.

#### 2.1. FormTemplate модель

```python
class FormTemplate(BaseModel):
    id = fields.IntField(primary_key=True)
    company: ForeignKeyRelation = fields.ForeignKeyField(
        "models.Company", related_name="form_templates", on_delete=CASCADE
    )
    name = fields.CharField(max_length=255)
    api_key_hash = fields.CharField(max_length=64, unique=True, null=True)
    contact_field: ForeignKeyRelation = fields.ForeignKeyField(
        "models.Field", related_name="contact_for_forms", on_delete=RESTRICT
    )  # REQUIRED — без contact_field Customer не идентифицируем
    enabled = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    template_fields: fields.ReverseRelation

    class Meta(BaseModel.Meta):
        table = "form_templates"
        schema = "backend"
```

**Constraints:**
- `contact_field` обязателен — иначе Customer становится orphan (нет способа матчить)
- `on_delete=RESTRICT` — нельзя удалить Field пока он используется как contact_field

- [ ] Создать FormTemplate модель
- [ ] Формат ключа: `form_<random>` (консистентно с `sk_<random>`)

#### 2.2. FormTemplateField модель

```python
class FormTemplateField(BaseModel):
    id = fields.IntField(primary_key=True)
    form_template: ForeignKeyRelation = fields.ForeignKeyField(
        "models.FormTemplate", related_name="template_fields", on_delete=CASCADE
    )
    field: ForeignKeyRelation = fields.ForeignKeyField(
        "models.Field", related_name="form_template_fields", on_delete=CASCADE
    )
    position = fields.IntField(default=0)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta(BaseModel.Meta):
        table = "form_template_fields"
        schema = "backend"
        unique_together = (("form_template", "field"),)
```

**Note:** `field.level` (customer|order) определяет куда писать значение при capture.

- [ ] Создать FormTemplateField модель

---

### Phase 3: API Key Generation

**Goal:** Реализовать генерацию API ключей для FormTemplate.

**Note:** Общая абстракция `core/api_keys.py` и рефакторинг ConnectorApiKey — отдельный PR после MVP.

```python
# apps/backend/src/backend/modules/forms/utils.py
import secrets
import hashlib

def generate_form_api_key() -> tuple[str, str]:
    """Generate form API key. Returns (raw_key, key_hash)."""
    raw_key = f"form_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    return raw_key, key_hash

def hash_form_api_key(raw_key: str) -> str:
    """Hash API key for lookup."""
    return hashlib.sha256(raw_key.encode()).hexdigest()
```

- [ ] Создать `forms/utils.py` с функциями генерации ключей
- [ ] Формат: `form_<random>` (консистентно с `sk_<random>`)

#### 3.1. Regenerate key action

```python
# В service.py
async def regenerate_api_key(self, form_id: int, company_id: int) -> str:
    """Regenerate API key. Returns raw key (shown once)."""
    form = await self.repo.get_by_id_and_company(form_id, company_id)
    generated = generate_api_key(prefix="form")
    await self.repo.update_key_hash(form_id, generated.key_hash)
    return generated.raw_key
```

- [ ] Реализовать regenerate в service
- [ ] Ключ показывается ТОЛЬКО при regenerate, потом недоступен

---

### Phase 4: CRUD Endpoints

**Goal:** API для управления формами (требует auth, права от менеджера).

```python
# apps/backend/src/backend/modules/forms/routers.py

POST   /companies/{company_id}/forms              # Создать форму
GET    /companies/{company_id}/forms              # Список форм
GET    /companies/{company_id}/forms/{id}         # Получить форму со схемой полей
PATCH  /companies/{company_id}/forms/{id}         # Обновить
DELETE /companies/{company_id}/forms/{id}         # Удалить
POST   /companies/{company_id}/forms/{id}/regenerate-key  # Перегенерировать api_key
GET    /companies/{company_id}/forms/{id}/submissions     # Список submissions (с пагинацией)
```

#### 4.1. Schemas

```python
class FormTemplateFieldCreate(BaseModel):
    field_id: int
    position: int = 0

class FormTemplateCreate(BaseModel):
    name: str
    contact_field_id: int  # REQUIRED
    template_fields: list[FormTemplateFieldCreate]

class FormTemplateFieldResponse(BaseModel):
    id: int
    field_id: int
    field_level: FieldLevel  # from Field.level
    position: int

class FormTemplateResponse(BaseModel):
    id: int
    name: str
    enabled: bool
    has_api_key: bool
    contact_field_id: int  # REQUIRED
    template_fields: list[FormTemplateFieldResponse]
    created_at: datetime
    updated_at: datetime

class RegenerateKeyResponse(BaseModel):
    api_key: str  # Показывается один раз!

class FormSubmissionResponse(BaseModel):
    id: int
    customer_id: int | None
    order_id: int | None
    raw_fields: dict[str, Any]
    utm_data: dict[str, str] | None
    ip_address: str | None
    created_at: datetime
```

- [ ] Создать Pydantic schemas
- [ ] Реализовать CRUD endpoints
- [ ] Требовать CompanyManagerDep для создания/изменения
- [ ] **Валидация:** contact_field и все template_fields.field_id должны принадлежать той же Company

---

### Phase 5: Capture Endpoints

**Goal:** Публичные endpoints для приёма заявок.

#### 5.1. Внешний capture endpoint

```python
POST /api/v1/forms/capture
Header: X-Form-Key: form_xxx
Body: {
    "fields": {
        "<field_id>": "value",
        ...
    },
    "utm": {
        "source": "google",
        "medium": "cpc",
        "campaign": "summer"
    }
}
Query: ?mode=full|minimal (default minimal)
```

**API Key Dependency:**
```python
# apps/backend/src/backend/modules/forms/dependencies.py

async def get_form_by_api_key(x_form_key: str = Header(...)) -> FormTemplate:
    """Validate X-Form-Key header and return FormTemplate."""
    key_hash = hash_api_key(x_form_key)
    form = await FormsRepository().get_by_key_hash(key_hash)
    if not form or not form.enabled:
        raise HTTPException(status_code=401, detail="Invalid or disabled form key")
    return form

FormByApiKeyDep = Annotated[FormTemplate, Depends(get_form_by_api_key)]
```

**CORS:** Глобальный CORS middleware. Если нужен `*` только для capture — добавить headers вручную в response.

- [ ] Создать `FormByApiKeyDep` в dependencies.py
- [ ] Реализовать capture endpoint
- [ ] Валидация api_key через hash lookup
- [ ] Добавить CORS headers в response (если глобальный CORS недостаточен)
- [ ] Строгая валидация по `required` флагам полей (400 если required пустое)

#### 5.2. Hosted/Internal endpoint

```python
POST /companies/{company_id}/forms/{form_id}/submit
# Auth: обычная JWT auth компании
Body: { same structure }
```

- [ ] Реализовать internal endpoint для in-CRM форм
- [ ] Требовать CompanyViewerDep (более мягкие права)

#### 5.3. Response modes

**Note:** `CustomerDetailResponse` требует дополнительные запросы для `fields_schema`. Для capture используем упрощённые схемы.

```python
class CaptureCustomerResponse(BaseModel):
    id: int
    user_id: str
    name: str | None
    customer_fields: dict[str, Any]

class CaptureOrderResponse(BaseModel):
    id: int
    order_number: int
    order_fields: dict[str, Any]

class CaptureResponse(BaseModel):
    customer: CaptureCustomerResponse
    order: CaptureOrderResponse

class CaptureMinimalResponse(BaseModel):
    customer_id: int
    order_id: int
    order_number: int
```

- [ ] `mode=full` — `CaptureResponse` с данными
- [ ] `mode=minimal` — `CaptureMinimalResponse` только id (default, для JS интеграций)

---

### Phase 6: Capture Logic

**Goal:** Обработка заявки — создание Customer и Order.

#### 6.1. Алгоритм обработки

**Существующие методы:**
- `ChatService.get_or_create(user_id, company_id, meta)` — создаёт/находит Customer
- `OrderService.create_order(company_id, customer_id, initial_channel)` — создаёт Order

```python
class CaptureResult(BaseModel):
    customer: Customer
    order: Order

async def process_capture(
    self,
    *,
    form: FormTemplate,
    fields_data: dict[str, Any],
    utm_data: dict[str, str] | None,
) -> CaptureResult:
    """
    1. Валидация api_key → получаем FormTemplate + Company
    2. Валидация данных по required флагам полей (400 если required пустое)
    3. Получить user_id из contact_field (REQUIRED, гарантирован моделью)
    4. ChatService.get_or_create(user_id, company_id) → Customer
    5. Обновить customer_fields значениями из формы
    6. OrderService.create_order(company_id, customer_id, initial_channel="form")
    7. Обновить order_fields значениями из формы
    8. Сохранить UTM в Order.utm_data (JSON)
    9. Логировать capture (metadata only, без raw fields)
    10. [Заглушка] место для future outbound message
    11. Return CaptureResult
    """
```

- [ ] Реализовать process_capture в service
- [ ] Разделить fields по `field.level` (customer vs order)
- [ ] user_id = значение contact_field (обязательно заполнено, валидация в п.2)
- [ ] Использовать `ChatService.get_or_create` для Customer
- [ ] Использовать `OrderService.create_order` для Order

#### 6.2. UTM tracking

Добавить поле в Order модель (если нет):

```python
# Order model
utm_data = fields.JSONField(null=True)  # {"source": "...", "medium": "...", ...}
```

- [ ] Проверить наличие utm_data в Order (добавить если нет)
- [ ] Сохранять UTM при capture

#### 6.3. Хранение submissions (audit table)

**Отдельная таблица для анализа и отладки:**

```python
class FormSubmission(BaseModel):
    id = fields.IntField(primary_key=True)
    form_template: ForeignKeyRelation = fields.ForeignKeyField(
        "models.FormTemplate", related_name="submissions", on_delete=CASCADE
    )
    customer: ForeignKeyNullableRelation = fields.ForeignKeyField(
        "models.Customer", related_name="form_submissions", on_delete=SET_NULL, null=True
    )
    order: ForeignKeyNullableRelation = fields.ForeignKeyField(
        "models.Order", related_name="form_submissions", on_delete=SET_NULL, null=True
    )
    raw_fields = fields.JSONField()  # {"field_id": "value", ...}
    utm_data = fields.JSONField(null=True)
    ip_address = fields.CharField(max_length=45, null=True)  # IPv6 max length
    user_agent = fields.CharField(max_length=512, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta(BaseModel.Meta):
        table = "form_submissions"
        schema = "backend"
        indexes = (("form_template_id", "created_at"),)
```

**Value:**
- Анализ конверсии форм
- Debugging проблемных submissions
- Аудит для менеджеров

- [ ] Создать FormSubmission модель
- [ ] Сохранять submission при каждом capture
- [ ] GET endpoint для списка submissions (с пагинацией)

#### 6.4. Заглушка для outbound

```python
# AICODE-TODO: Implement outbound message sending after Contact Registry
# This is where we'll initiate first message to the customer
```

- [ ] Добавить место для будущей реализации outbound
- [ ] Оставить `AICODE-TODO` с описанием

---

### Phase 7: Testing

#### 7.1. Unit tests

```
apps/backend/tests/domains/forms/
├── __init__.py
├── test_models.py           # FormTemplate, FormTemplateField
├── test_api_key.py          # Генерация, хеширование, валидация (общий модуль)
├── test_capture_service.py  # process_capture логика
└── test_validation.py       # required fields validation
```

- [ ] Тесты создания FormTemplate
- [ ] Тесты FormTemplateField с Field FK
- [ ] Тесты общего модуля api_keys (core/api_keys.py)
- [ ] Тесты capture с валидными данными
- [ ] Тесты capture с missing required fields (expect 400)
- [ ] Тесты поиска существующего Customer

#### 7.2. Integration tests

```
apps/backend/tests/integration/forms/
├── __init__.py
├── test_crud_endpoints.py
├── test_capture_endpoints.py
└── test_full_flow.py
```

- [ ] Тест: создание формы → regenerate key → capture
- [ ] Тест: capture с UTM → проверка в Order
- [ ] Тест: capture → FormSubmission создан с raw_fields
- [ ] Тест: повторная заявка → новый Order для существующего Customer
- [ ] Тест: disabled form → 403
- [ ] Тест: invalid key → 401
- [ ] Тест: mode=minimal response
- [ ] Тест: submissions endpoint с пагинацией

---

### Phase 8: CORS и Security

#### 8.1. CORS

- [ ] Настроить CORS для capture endpoint (`*` origin)

#### 8.2. Rate Limiting

**Решение:** `slowapi` с Redis backend (уже есть в инфраструктуре).

```python
# apps/backend/src/backend/modules/forms/rate_limit.py
from slowapi import Limiter
from slowapi.util import get_remote_address
from redis import Redis

from src.backend.modules.core.settings import get_settings

settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis.url,  # redis://redis:6379
)
```

```python
# apps/backend/src/backend/modules/forms/routers.py
from src.backend.modules.forms.rate_limit import limiter

@router.post("/capture")
@limiter.limit("60/minute")
async def capture_form(...):
    ...
```

- [ ] Добавить `slowapi` в зависимости backend
- [ ] Создать `forms/rate_limit.py` с конфигурацией из `settings.redis.url`
- [ ] Применить rate limit к capture endpoint (60/min per IP)
- [ ] Зарегистрировать limiter в FastAPI app (error handler)

---

## Scope Summary

**Prerequisites (Phase 0):**
- Завершить rename `forms/` → `fields/` (обновить импорты)

**В scope:**
- FormTemplate, FormTemplateField, FormSubmission модели
- API key generation в `forms/utils.py`
- Добавить `Order.utm_data` JSON field
- CRUD endpoints с auth и company validation
- Submissions list endpoint для аналитики
- Два capture endpoints (внешний + hosted)
- UTM tracking
- Response modes (full/minimal, default minimal)
- Rate limiting (`slowapi` + Redis, 60/min per IP)

**Out of scope:**
- UI (фронтенд concern)
- Отправка первого сообщения (заглушка)
- Contact Registry / склейка контактов
- Общая абстракция `core/api_keys.py` (отдельный PR)

---

## Decisions Log

| Вопрос | Решение |
|--------|---------|
| Название модуля | `forms/` (старый `forms/` переименован в `fields/`) |
| Формат api_key | `form_<random>` (консистентно с `sk_<random>`) |
| API key логика | `forms/utils.py` для MVP; общая абстракция — отдельный PR |
| Связь FormTemplateField → Field | FK, не int; `field.level` определяет customer/order |
| Порядок полей в форме | `position` (не `order`, чтобы не путать с моделью Order) |
| Источник формы | Оба: hosted + внешняя интеграция |
| Контакт обязателен? | **Да** — без него Customer orphan |
| Выбор мессенджера | Явное поле в форме (dropdown) — out of scope |
| Повторная заявка | Новый Order для существующего Customer |
| Поиск Customer | По contact_field из FormTemplate (обязателен) |
| user_id для Customer | Значение contact_field (UUID fallback убран) |
| Валидация company | Field-ы должны принадлежать той же Company что и FormTemplate |
| Хранение полей формы | Отдельная модель FormTemplateField с FK на Field |
| Генерация ключа | Явный action (regenerate) |
| Валидация | По `required` флагу полей |
| UTM | JSON поле `Order.utm_data` |
| Response | Полный объект, два режима (full/minimal, default minimal) |
| Права на создание | CompanyManagerDep |
| Миграции | Выполняются пользователем через aerich |
| Rate limiting | `slowapi` 60/min per IP, Redis backend (`settings.redis.url`) |
| Хранение submissions | DB таблица `FormSubmission` для аудита и аналитики |

---

## Risks & Open Questions

### Risks

1. **Data leak в minimal mode** — определить какие поля считать sensitive
   - Mitigation: Minimal mode возвращает только id-шники, никаких полей

2. **Удаление contact_field** — FK с RESTRICT, удаление заблокировано пока Field используется
   - Status: Решено через `on_delete=RESTRICT`

3. **Удаление Field из template_fields** — FK с CASCADE удалит FormTemplateField
   - Mitigation: Показывать warning в UI при удалении Field, если он используется в формах

### Open Questions

*Все вопросы решены.*

---

## Success Criteria

- [ ] Импорты `forms/*` → `fields/*` исправлены, код компилируется
- [ ] Компания может создавать FormTemplate через API
- [ ] contact_field обязателен при создании формы
- [ ] Валидация: все Field-ы принадлежат той же Company
- [ ] Можно добавлять поля (через FK на Field) в форму с указанием position
- [ ] API key генерируется и показывается один раз
- [ ] Capture endpoint принимает заявки по X-Form-Key
- [ ] Rate limiting работает (60/min per IP)
- [ ] Required поля валидируются, возвращается 400 при отсутствии
- [ ] Customer создаётся или находится по contact_field value
- [ ] Order создаётся с заполненными полями и UTM
- [ ] Response modes работают (full/minimal, default minimal)
- [ ] Disabled form возвращает 403
- [ ] FormSubmission сохраняется при каждом capture
- [ ] Submissions endpoint возвращает историю с пагинацией
- [ ] Все операции покрыты тестами
