# 029 — Simplify Tool Enablement: Drop Tool Tables, Use JSON Config

## Зачем это делаем

Сейчас инструменты агента (tools) — это **полностью code-defined** сущности: имя, схема параметров и handler живут в `sales-agent/core/tools/registry.py`. Но при этом они моделируются как DB-сущности (`Tool`, `CompanyTool`, `CategoryTool`) с FK-цепочкой из трёх таблиц. Это создаёт:

- **Sync burden**: добавление нового инструмента = код + DB insert + привязка к компании через curl (UI нет).
- **Ghost bugs**: забыл вставить строку в `Tool` → агент молча не использует инструмент, дебаг неочевиден.
- **Лишняя сложность**: целый CRUD-модуль (`ToolsService`, `ToolsRepository`, роутеры, тесты) для данных, которые дублируют код.

После упрощения:
- Администратор включает/выключает инструменты **чекбоксами в UI** — zero curl, zero DB seeding.
- Канонический список инструментов определяется одним enum в `libs/common` — backend и sales-agent ссылаются на один источник.
- Убирается ~400 строк мёртвого CRUD-кода и 3 таблицы.

## Problem

- `Tool` таблица хранит только `name + description`, оба имеют авторитетный источник в коде.
- `CompanyTool` / `CategoryTool` join-таблицы отвечают на единственный вопрос "включён ли tool X для company Y?" — это `set[str]` membership check.
- Добавление/удаление tool = code change + DB insert + привязка к компании через curl (UI не существует).
- Description override per company технически возможен, но на практике не используется.

## Chosen Design

Заменить три-таблицу FK-цепочку на `list[str]` JSON-поле на `Company` и `Category`:

- `Company.enabled_tools: list[str]` — инструменты, включённые на уровне компании
- `Category.enabled_tools: list[str]` — инструменты, включённые на уровне категории (расширяет/переопределяет company)
- Code registry остаётся единственным source of truth для доступных tool names
- Backend отдаёт канонический список tool names через endpoint (для фронтенда)
- Удаляются `Tool`, `CompanyTool`, `CategoryTool` таблицы

---

## Phase 1: Foundation — `AvailableTool` + `ToolGroup` + `TOOL_CATALOG` в `libs/common`

**Модуль:** `libs/common`

**Цель:** Единый source of truth для tool names и их группировки, используемый и backend, и sales-agent.

**Файлы:**
- **Создать** `libs/common/src/common/tools.py` — `AvailableTool(StrEnum)`, `ToolGroup(StrEnum)`, `TOOL_CATALOG`
- **Изменить** `libs/common/src/common/__init__.py` — реэкспорт `AvailableTool`, `ToolGroup`, `TOOL_CATALOG`
- **Изменить** `libs/common/src/common/models/outbound.py` — `AgentContext.enabled_tools: list[dict[str, Any]]` → `list[str]` (контракт backend↔sales-agent)

**Содержание:**
```python
class ToolGroup(StrEnum):
    ORDER_MANAGEMENT = "order_management"
    KNOWLEDGE = "knowledge"
    CUSTOMER = "customer"
    COMMUNICATION = "communication"

class AvailableTool(StrEnum):
    SET_CUSTOMER_FIELDS = "set_customer_fields"
    SEARCH_KB = "search_kb"
    GEO_METRICS = "geo_metrics"
    HANDOFF = "handoff"
    SCHEDULE_REMINDER = "schedule_reminder"
    SEARCH_PRODUCT = "search_product"
    UPDATE_ORDER_STAGE = "update_order_stage"
    UPDATE_ORDER_FIELDS = "update_order_fields"
    CLOSE_ORDER = "close_order"
    REQUEST_HANDOFF = "request_handoff"

TOOL_CATALOG: dict[ToolGroup, list[AvailableTool]] = {
    ToolGroup.ORDER_MANAGEMENT: [
        AvailableTool.UPDATE_ORDER_STAGE,
        AvailableTool.UPDATE_ORDER_FIELDS,
        AvailableTool.CLOSE_ORDER,
    ],
    ToolGroup.KNOWLEDGE: [
        AvailableTool.SEARCH_KB,
        AvailableTool.SEARCH_PRODUCT,
        AvailableTool.GEO_METRICS,
    ],
    ToolGroup.CUSTOMER: [
        AvailableTool.SET_CUSTOMER_FIELDS,
    ],
    ToolGroup.COMMUNICATION: [
        AvailableTool.HANDOFF,
        AvailableTool.REQUEST_HANDOFF,
        AvailableTool.SCHEDULE_REMINDER,
    ],
}

# Runtime assertion: every AvailableTool must belong to exactly one group.
_cataloged = {t for tools in TOOL_CATALOG.values() for t in tools}
_missing = set(AvailableTool) - _cataloged
assert not _missing, f"Tools missing from TOOL_CATALOG: {_missing}"
```

**Дизайн-решение:** Один плоский `AvailableTool` enum (валидация, DB storage, set membership) + `ToolGroup` enum + `TOOL_CATALOG` dict (только для display/UI). Runtime assert гарантирует, что при добавлении нового tool без группы — fail fast при импорте модуля.

**Зависимости:** Нет (фундамент для всех последующих фаз).

---

## Phase 2: Backend — Schema migration (добавление JSON-полей + data migration)

**Модуль:** `apps/backend`

**Цель:** Добавить `enabled_tools` JSON-поле на `Company` и `Category`, мигрировать данные из join-таблиц. **Чисто аддитивная фаза — ничего не удаляем, ничего не ломаем.**

**Файлы:**
- **Изменить** `apps/backend/src/backend/modules/companies/models.py` — добавить `enabled_tools = fields.JSONField(default=list)` на `Company` (старые helpers и reverse relations остаются — ими ещё пользуется service layer)
- **Изменить** `apps/backend/src/backend/modules/categories/models.py` — добавить `enabled_tools = fields.JSONField(default=list)` на `Category` (аналогично, всё старое остаётся)
- **Создать** `apps/backend/migrations/models/XXX_add_enabled_tools.py` — aerich migration:
  1. `ALTER TABLE` добавляет `enabled_tools` JSON-поле (default `[]`)
  2. Data migration: `SELECT` из `company_tools`/`category_tools` JOIN `tools` → `UPDATE` JSON-поля с массивом tool names

**Зависимости:** Phase 1 (`AvailableTool` enum для валидации при data migration).

**Rollback:** JSON-поля остаются, старые таблицы и код не тронуты — откат = revert migration.

---

## Phase 3: Backend — Service + API refactor

**Модуль:** `apps/backend`

**Цель:** Переключить всю логику на JSON-поля, обновить API-контракт, добавить endpoint для списка доступных tools.

**Файлы:**
- **Изменить** `apps/backend/src/backend/modules/companies/schemas.py`:
  - `CompanyRequest.tool_ids: list[int]` → `enabled_tools: list[str] = Field(default_factory=list)`
  - `CompanyPatch.tool_ids: list[int] | None` → `enabled_tools: list[str] | None = None`
  - `CompanyResponse.tools: list[ToolResponse]` → `enabled_tools: list[str]`
  - Добавить Pydantic `field_validator("enabled_tools")`: каждый элемент должен быть в `AvailableTool`, иначе `ValidationError` (fail fast на API input, не молча на LLM runtime)
- **Изменить** `apps/backend/src/backend/modules/categories/schemas.py`:
  - `CategoryRequest.tool_ids: list[int]` → `enabled_tools: list[str] = Field(default_factory=list)`
  - `CategoryPatch.tool_ids: list[int] | None` → `enabled_tools: list[str] | None = None`
  - `CategoryResponse.tools: list[ToolResponse]` → `enabled_tools: list[str]`
  - Добавить аналогичный `field_validator("enabled_tools")` против `AvailableTool`
- **Изменить** `apps/backend/src/backend/modules/companies/service.py`:
  - `create_company()` — убрать `tool_ids` pop → `enabled_tools` записывается напрямую в модель через `**kwargs`
  - `update_company()` — убрать `tool_ids` pop → `enabled_tools` обновляется как обычное поле
  - `get_specification()` — убрать local imports `CompanyTool, CategoryTool`; читать `company.enabled_tools` напрямую; в spec dict переименовать ключ `"tools"` → `"enabled_tools"`; в `CategoryDetailResponse` аналогично `tools` → `enabled_tools`
  - `_to_response()` — убрать параметр `tools: list[Tool]`, читать `enabled_tools` из модели напрямую; обновить всех вызывающих (`create_company`, `update_company`, и т.д.)
  - Удалить `list_tools_paginated()`, `_serialize_tools()`; убрать top-level import `from tools.models import Tool`
- **Изменить** `apps/backend/src/backend/modules/categories/service.py`:
  - `create()` — убрать explicit arg `tool_ids: list[int] | None` → `enabled_tools` записывается напрямую при создании модели
  - `update()` — убрать `tool_ids` pop → `enabled_tools` обновляется как обычное поле
  - Убрать import `from tools.models import Tool`
- **Изменить** `apps/backend/src/backend/modules/companies/models.py` — удалить `get_tools()`, `add_tool()`, `clear_tools()` helpers и импорт `CompanyTool, Tool` (services больше ими не пользуются)
- **Изменить** `apps/backend/src/backend/modules/categories/models.py` — удалить `get_tools()`, `add_tool()`, `clear_tools()` helpers и импорт `CategoryTool, Tool`
- **Изменить** `apps/backend/src/backend/modules/messages/context_assembly.py`:
  - `_extract_enabled_tools()` — упростить: вместо `list[dict]` с name+description возвращать `list[str]` из `company_spec["enabled_tools"]` + каждой category `enabled_tools`
- **Изменить** `apps/backend/src/backend/modules/companies/routers.py`:
  - Удалить endpoint `GET /{company_id}/tools`
- **Изменить** `apps/backend/src/backend/modules/tools/routers.py`:
  - Заменить CRUD-роутеры одним: `GET /tools/available` → возвращает grouped structure из `TOOL_CATALOG`:
    ```json
    [
      {"group": "order_management", "tools": ["update_order_stage", "update_order_fields", "close_order"]},
      {"group": "knowledge", "tools": ["search_kb", "search_product", "geo_metrics"]},
      ...
    ]
    ```
- **Изменить** `apps/backend/src/backend/modules/tools/service.py` — удалить или упростить до одного метода `list_available()`
- **Удалить** `apps/backend/src/backend/modules/tools/repository.py`
- **Изменить** `apps/backend/src/backend/modules/tools/schemas.py` — удалить `ToolBase`, `ToolRequest`, `ToolResponse`, `ToolPatch`; добавить `ToolGroupResponse(group: str, tools: list[str])`
- **Изменить** `apps/backend/src/backend/modules/tools/dependencies.py` — упростить `ToolsServiceDep` под новый `ToolsService`

**Зависимости:** Phase 2 (JSON-поля должны существовать в БД).

---

## Phase 4: Backend — Drop old tables + cleanup

**Модуль:** `apps/backend`

**Цель:** Удалить `Tool`, `CompanyTool`, `CategoryTool` модели и таблицы.

**Файлы:**
- **Создать** `apps/backend/migrations/models/XXX_drop_tool_tables.py` — `DROP TABLE` для `company_tools`, `category_tools`, `tools`
- **Удалить** модели `Tool`, `CompanyTool`, `CategoryTool` из `apps/backend/src/backend/modules/tools/models.py`
- **Изменить** `apps/backend/src/backend/modules/core/models.py` — убрать импорт `Tool`, `CompanyTool`, `CategoryTool`
- **Изменить** `apps/backend/src/backend/modules/companies/models.py` — убрать `company_tool_relations: fields.ReverseRelation` (FK source удалён вместе с `CompanyTool`)
- **Изменить** `apps/backend/src/backend/modules/categories/models.py` — убрать `category_tool_relations: fields.ReverseRelation`
- **Изменить** тесты:
  - `apps/backend/tests/domains/tools/test_routers.py` — переписать: тестировать `GET /tools/available` вместо CRUD
  - `apps/backend/tests/domains/tools/test_services.py` — удалить или переписать
  - `apps/backend/tests/domains/tools/test_repositories.py` — удалить (repository больше нет)
  - `apps/backend/tests/domains/tools/test_models.py` — удалить (модели удалены)
  - `apps/backend/tests/domains/companies/test_services.py` — обновить: imports `Tool`, использует `tool_ids`
  - `apps/backend/tests/domains/categories/test_routers.py` — обновить: `tool_ids` в payloads
  - `apps/backend/tests/domains/categories/test_services.py` — обновить: imports `Tool`, использует `tool_ids`
  - Обновить фабрики/фикстуры, которые создают `Tool`/`CompanyTool`/`CategoryTool`

**Зависимости:** Phase 3 (весь код уже переключён на JSON-поля, старые таблицы не читаются).

---

## Phase 5: Sales Agent — Simplify `build_tools()`

**Модуль:** `apps/sales-agent`

**Цель:** Упростить `build_tools()` — принимать `list[str]` вместо `list[dict]`, убрать description fallback.

**Файлы:**
- **Изменить** `apps/sales-agent/src/sales_agent/core/tools/registry.py`:
  - `build_tools(enabled_tools: list[dict])` → `build_tools(enabled_tools: list[str])`
  - Убрать `desc_map` / `_desc()` — описания hardcoded в коде, DB-override больше не нужен
  - Использовать `AvailableTool` enum для type safety при проверке `if AvailableTool.SEARCH_KB in enabled_names`
- **Изменить** `apps/sales-agent/src/sales_agent/agents/pipeline.py`:
  - Обновить вызов `build_tools()` под новую сигнатуру
- **Изменить** `apps/sales-agent/src/sales_agent/services/prompt_formatter.py`:
  - Переименовать ключи доступа к spec dict: `company_data.get("tools")` → `company_data.get("enabled_tools")`, `current_category.get("tools")` → `current_category.get("enabled_tools")`
  - `_format_tools(tools: list[dict])` → `_format_tools(tools: list[str])` — брать descriptions из `TOOL_SCHEMAS`, а не из dict
  - `merge_tools()` вызов — упростить под `list[str]`
- **Изменить** `apps/sales-agent/src/sales_agent/core/tools/utils.py`:
  - `merge_tools(company_tools: list[dict], category_tools: list[dict])` → `merge_tools(company_tools: list[str], category_tools: list[str]) -> list[str]` (set union вместо dict merge by name)
- **Изменить** тесты sales-agent:
  - `tests/domains/api/test_internal.py` — `enabled_tools` в фикстурах: `list[dict]` → `list[str]`
  - `tests/domains/agents/test_pipeline.py` — аналогично
  - `tests/domains/agents/test_pipeline_e2e.py` — аналогично

**Зависимости:** Phase 1 (`AgentContext.enabled_tools` тип уже `list[str]`), Phase 3 (`_extract_enabled_tools()` уже возвращает `list[str]`, spec dict ключи переименованы в `"enabled_tools"`).

---

## Phase 6: Frontend — Tool configuration UI

**Модуль:** `sales-front`

**Цель:** Чекбоксы для включения/выключения tools в AgentSettings и ProductCatalog.

**Файлы:**
- **Создать** `sales-front/services/toolsService.ts` — `getAvailableTools()` → `GET /api/v1/tools/available`
- **Изменить** `sales-front/services/api/endpoints.ts` — добавить `TOOLS.AVAILABLE`
- **Изменить** `sales-front/types/api.ts` — добавить `ToolGroupResponse { group: string; tools: string[] }`; добавить `enabled_tools: string[]` к `Company` (в `types.ts`) и `CategoryBackend`
- **Изменить** `sales-front/services/products.ts` — расширить `updateCategory()` payload: сейчас принимает только `{ name: string }`, нужно поддержать `enabled_tools`
- **Изменить** `sales-front/components/AgentSettings.tsx`:
  - Добавить вкладку "Инструменты"
  - Рендерить группы из `getAvailableTools()` как collapsible-секции с чекбоксами внутри
  - Текущее состояние из `company.enabled_tools`, сохранение через `PATCH /companies/{id}` с `enabled_tools: string[]`
- **Изменить** `sales-front/components/ProductCatalog.tsx`:
  - В модалке редактирования категории добавить grouped checkbox-секцию для `enabled_tools`
  - Отображать только tools, не включённые на уровне компании (или все, с пометкой "включён на уровне компании")

**Зависимости:** Phase 3 (новый API-контракт с `enabled_tools: list[str]` и endpoint `GET /tools/available`).

---

## Migration Path (краткий чеклист)

1. [ ] Phase 1: `AvailableTool` enum в `libs/common`
2. [ ] Phase 2: Aerich migration — добавить JSON-поля, data migration из join-таблиц
3. [ ] Phase 3: Переключить service/API на JSON-поля, новый `GET /tools/available`
4. [ ] Phase 4: Drop `Tool`, `CompanyTool`, `CategoryTool` таблиц и моделей
5. [ ] Phase 5: Упростить `build_tools()` в sales-agent
6. [ ] Phase 6: Frontend — чекбоксы в AgentSettings и ProductCatalog

## Conventions to Document

После завершения — добавить правило в `AGENTS.md` или `docs/`:

> **Adding a new tool checklist:**
> 1. Add member to `AvailableTool` enum in `libs/common/src/common/tools.py`
> 2. Add to a `ToolGroup` in `TOOL_CATALOG` (runtime assert catches forgotten)
> 3. Add schema to `TOOL_SCHEMAS` in `sales-agent/core/tools/registry.py`
> 4. Add handler block in `build_tools()`
>
> Frontend `GET /tools/available` endpoint is the ground truth for the UI. If a tool is missing from the enum but present in `TOOL_SCHEMAS`, it simply won't appear in the UI — easy to spot and fix.

## Risks / Open Questions

- **Data migration atomicity**: JSON-поле заполняется из join-таблиц в миграции — если компания имеет tool, не совпадающий с `AvailableTool` enum (мусор в DB), он будет проигнорирован. Нужно логировать такие случаи.
- **API breaking change**: `tool_ids: list[int]` → `enabled_tools: list[str]` — фронтенд должен обновиться синхронно с backend. Координировать деплой Phase 3 + Phase 6.
- **Category tool override semantics**: текущая логика — category tools расширяют company tools (union). Сохраняем это поведение или даём category возможность *сужать* company-level набор? Текущий план сохраняет union.
- **Deploy ordering Phase 1 vs Phase 5**: `AgentContext.enabled_tools` тип меняется в Phase 1 (`list[str]`), но sales-agent начнёт получать `list[str]` только после Phase 3 (backend). Между Phase 1 и Phase 3 sales-agent должен корректно обрабатывать **оба формата** (`list[dict]` от текущего backend, `list[str]` после Phase 3). Решение: деплоить Phase 1 + Phase 2 + Phase 3 + Phase 5 атомарно, либо сделать `AgentContext.enabled_tools` Union-типом на переходный период.
- **Spec dict key rename**: `get_specification()` возвращает `"tools"` key, `prompt_formatter.py` читает `company_data.get("tools")`. Переименование на `"enabled_tools"` должно быть синхронным в Phase 3 (backend) и Phase 5 (sales-agent). Sales-agent при развёртывании должен получить обновлённый spec.

## Rollback Strategy

- Phase 2 миграция обратима: `DROP COLUMN enabled_tools` возвращает к join-таблицам (они ещё не удалены до Phase 4).
- Phase 4 (drop tables) — point of no return. Перед выполнением убедиться, что всё работает на JSON-полях.
- Фронтенд: откат к коммиту до Phase 6 безопасен, если backend ещё принимает старый формат (window между Phase 3 и Phase 4).
