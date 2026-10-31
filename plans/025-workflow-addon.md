# 015 — Workflow Addon (Разные промпты для разных коннекторов)

> **Это документ требований**, не пошаговый план реализации. Детали имплементации остаются на усмотрение разработчика.

## Objective

Добавить возможность задавать отдельный qualification workflow для конкретных коннекторов.

## Why We're Doing This

- **Гибкость для клиентов**: разные бизнесы могут требовать разную логику для разных коннекторов — например, в Instagram сначала собрать контакт, а в Telegram сразу квалифицировать
- **Reusability**: один workflow addon можно переиспользовать для нескольких коннекторов
- **Fallback к стандарту**: если кастомный workflow не задан — используется обычный `company.qualification_workflow`
- **Sales-agent получает готовое**: минимум знаний о структуре, просто получает нужный workflow в CompanySpec

## Context

### Текущее состояние

```
Prompt (agent_type: QUALIFIER, ROUTER, CATEGORY_EXPERT)
    └── content (один шаблон на все компании/каналы)

Company
    ├── qualification_workflow (текст, подставляется в {{ company.qualification_workflow }})
    └── qualification_examples (текст)

Connector (в transport/models.py)
    ├── connector_id (unique)
    ├── company_id (FK)
    ├── type (telegram, wappi, custom)
    └── channel_type (строка)

Thread
    └── connector_id (ссылка на коннектор)
```

- Промпт qualifier содержит `{{ company.qualification_workflow }}`
- PromptFormatter подставляет `company.qualification_workflow` из CompanySpec
- Коннектор известен, но не влияет на выбор workflow

### Целевое состояние

```
Company
    └── qualification_workflow (стандартный, fallback)

WorkflowAddon (новая модель в modules/workflow_addons/)
    ├── id (PK)
    ├── company_id (FK)
    ├── name (для UI, например "Instagram Quick Contact")
    └── workflow (текст для подстановки)

Connector
    └── workflow_addon_id (FK → WorkflowAddon, nullable, ON DELETE SET NULL)
```

## What We're Building

### 1. Модель WorkflowAddon

Расположение: `apps/backend/src/backend/modules/workflow_addons/models.py`

```python
class WorkflowAddon(BaseModel):
    id = fields.IntField(primary_key=True)
    company = fields.ForeignKeyField("models.Company", related_name="workflow_addons")
    name = fields.CharField(max_length=255)  # "Instagram Quick Contact"
    workflow = fields.TextField()
```

### 2. FK в Connector

Добавить в `Connector`:

```python
workflow_addon = fields.ForeignKeyField(
    "models.WorkflowAddon",
    related_name="connectors",
    null=True,
    on_delete=fields.SET_NULL,
)
```

### 3. Логика выбора workflow (в backend)

При формировании CompanySpec:
1. Получаем connector по thread.connector_id
2. Если connector.workflow_addon существует → используем addon.workflow
3. Иначе → company.qualification_workflow

```python
def get_qualification_workflow(connector: Connector | None, company: Company) -> str:
    if connector and connector.workflow_addon:
        return connector.workflow_addon.workflow
    return company.qualification_workflow
```

### 4. Передача в sales-agent

Backend формирует CompanySpec с уже выбранным workflow. Sales-agent не знает о существовании addons — получает готовый `qualification_workflow`.

Изменения в chain:
- При invoke: backend определяет connector из thread
- Backend подставляет правильный workflow в CompanySpec
- Sales-agent использует `company_spec.qualification_workflow` как обычно

### 5. API endpoints

| Endpoint | Описание |
|----------|----------|
| `GET /companies/{id}/workflow-addons` | Список addon'ов компании |
| `POST /companies/{id}/workflow-addons` | Создать addon |
| `GET /companies/{id}/workflow-addons/{addon_id}` | Получить addon |
| `PUT /companies/{id}/workflow-addons/{addon_id}` | Обновить addon |
| `DELETE /companies/{id}/workflow-addons/{addon_id}` | Удалить addon |
| `PATCH /companies/{id}/connectors/{connector_id}` | Назначить/убрать addon (workflow_addon_id) |

## Decisions

| Вопрос | Решение |
|--------|---------|
| Название модели | `WorkflowAddon` (без "Channel") |
| Где хранить модель? | Отдельный модуль `modules/workflow_addons/` |
| Привязка к чему? | К Connector (не к channel_type) |
| Один addon — много коннекторов? | Да, FK от Connector к Addon |
| Что переопределяем? | Только workflow (MVP), остальное потом |
| Как sales-agent получает workflow? | Прокидываем в CompanySpec, без доп. запросов |
| Каскад при удалении addon | `SET_NULL` — коннекторы переключаются на fallback |

## Module Structure

| Компонент | Расположение |
|-----------|--------------|
| Модель WorkflowAddon | `apps/backend/src/backend/modules/workflow_addons/models.py` |
| Repository | `apps/backend/src/backend/modules/workflow_addons/repository.py` |
| Service | `apps/backend/src/backend/modules/workflow_addons/service.py` |
| Schemas | `apps/backend/src/backend/modules/workflow_addons/schemas.py` |
| Routers | `apps/backend/src/backend/modules/workflow_addons/routers.py` |
| Migration (FK в Connector) | `apps/backend/migrations/models/` |
| CompanySpec формирование | `apps/backend/src/backend/modules/companies/service.py` |

## Questions Addressed During Design

- Где хранить модель? → Отдельный модуль
- Привязка к channel_type или connector? → К connector
- Что кроме workflow переопределять? → Только workflow (MVP)
- Как передавать в sales-agent? → Прокидываем сразу в CompanySpec
- Название модели? → `WorkflowAddon`
- Каскад при удалении? → `SET_NULL`

## Scope

**В scope:**
- Модель WorkflowAddon
- FK в Connector (`workflow_addon_id`, nullable, SET_NULL)
- CRUD API для addons
- Логика fallback в CompanySpec
- Миграция

**Вне scope:**
- UI для управления workflow addons
- Сами тексты workflow (контент)
- Переопределение examples/tools/fields (future)
