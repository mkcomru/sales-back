# 037 — Визуальный конструктор условий стадий + детальный отчёт

## Objective

Сделать настройку и мониторинг автопереходов стадий понятным для пользователя:
1. **Condition Builder** — визуальный конструктор условий в UI вместо ручного JSON
2. **Condition Report** — детальная оценка каждого условия с указанием, что выполнено, а что нет

## Зачем это делаем

**Проблема:** Сейчас `transition_condition` — это MongoDB-like JSON, который нигде в UI нельзя ни настроить, ни увидеть в человекочитаемом виде. Пользователь не может:
- Настроить автосмену стадий без помощи разработчика
- Понять, почему заказ не перешёл на следующую стадию
- Быстро увидеть, каких полей не хватает для перехода

**Ценность:**
- Менеджеры самостоятельно настраивают воронку продаж — без тикетов в разработку
- При просмотре заказа видно, что блокирует продвижение по воронке — мгновенная ориентация
- Упрощается отладка: JSON остаётся доступен команде через dropdown

**Что становится возможным:**
- Полноценный self-service по настройке автоматических переходов
- Визуальный прогресс-бар или чеклист условий по каждой стадии в UI

---

## Текущее состояние

### Backend (conditions engine)
- `evaluate_condition()` → возвращает **только `bool`**, без деталей
- `get_order_stage_requirements()` → `condition_status: "met" | "partial" | "blocked"` + `missing_fields` (имена полей, не значения)
- Endpoint: `POST /companies/{id}/orders/{id}/stage-requirements`
- Операторы: `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$exists`, `$and`, `$or`, `$not`, `$any`, `$stage_completed`, `$prev_stage_completed`

### Frontend
- `StageFormModal` — создание/редактирование стадии (имя, цвет, is_final, auto_close). **Нет поля для condition.**
- `StageDetailModal` — показывает `transition_condition` как raw JSON в `<pre>` блоке
- Типы: `StageTemplate.transition_condition: Record<string, unknown> | null`
- `CompanyField` — есть `name`, `display_name`, `type`, `level` (customer/order), `options` для enum

---

## Минимальная версия (MVP)

### Фаза 1 — Backend: `evaluate_condition_detailed`

**Модуль:** `apps/backend`

**Цель:** Новая функция, возвращающая результат по каждому подусловию.

**Файлы:**
- `src/backend/core/conditions/interpreter.py` — новая функция `evaluate_condition_detailed`
- `src/backend/core/conditions/operators.py` — импорт `_get_field_value` (для извлечения `actual` значений в report)
- `src/backend/core/conditions/__init__.py` — экспорт `evaluate_condition_detailed`
- `src/backend/modules/orders/schemas.py` — новые Pydantic-модели `ConditionClause`, `ConditionGroup`, `ConditionReport`
- `src/backend/modules/orders/service.py` — использование `evaluate_condition_detailed` в `get_order_stage_requirements`
- `tests/domains/conditions/test_interpreter.py` — тесты для `evaluate_condition_detailed` (файл уже существует, дополнить)

**Контракт (выход `evaluate_condition_detailed`):**

```python
class ConditionClause(BaseModel):
    """Leaf clause — single field check or custom operator."""
    type: Literal["clause"] = "clause"
    description: str          # "order_fields.budget ≥ 1000"
    field: str | None         # "order_fields.budget" или None для $any/$stage_completed
    operator: str             # "$gte", "$exists", "$any", "$stage_completed"
    expected: Any             # 1000, True, stage_id
    actual: Any | None        # 500, None (поле не задано)
    result: bool              # True/False

class ConditionGroup(BaseModel):
    """Logical group — $and / $or / $not с вложенными элементами."""
    type: Literal["group"] = "group"
    logic: str                # "and" | "or" | "not"
    children: list[ConditionClause | ConditionGroup]
    result: bool

ConditionNode = ConditionClause | ConditionGroup

class ConditionReport(BaseModel):
    """Full evaluation report — корень всегда group (implicit AND)."""
    overall: bool
    root: ConditionGroup
```

Рекурсивная структура: `ConditionGroup.children` может содержать как `ConditionClause` (лист), так и вложенные `ConditionGroup`. Backend уже поддерживает вложенность — `_evaluate_condition_dict` рекурсивен. `evaluate_condition_detailed` просто собирает дерево результатов вместо `bool`.

**Важно:** существующий `evaluate_condition` не трогаем — он используется в hot path (`recalculate_stage`). `evaluate_condition_detailed` — отдельная функция для UI-запросов.

**Влияние на `NextStageInfo`:**
```python
class NextStageInfo(BaseModel):
    stage: StageInfo
    missing_fields: list[str]
    condition_status: str                            # без изменений
    condition_report: ConditionReport | None = None  # новое поле
```

**Пример JSON-ответа `condition_report`:**
```json
{
  "overall": false,
  "root": {
    "type": "group",
    "logic": "and",
    "result": false,
    "children": [
      {"type": "clause", "description": "budget ≥ 1000", "field": "order_fields.budget", "operator": "$gte", "expected": 1000, "actual": 5000, "result": true},
      {
        "type": "group", "logic": "or", "result": false,
        "children": [
          {"type": "clause", "description": "city = Москва", "field": "customer_fields.city", "operator": "$eq", "expected": "Москва", "actual": null, "result": false},
          {"type": "clause", "description": "region = МО", "field": "customer_fields.region", "operator": "$eq", "expected": "МО", "actual": null, "result": false}
        ]
      }
    ]
  }
}
```

---

### Фаза 2 — Frontend: Condition Builder

**Модуль:** `sales-front`

**Цель:** Визуальный конструктор правил в `StageFormModal` — пользователь кликает, выбирает поле, оператор, значение. Конструктор конвертирует в JSON для API.

**Зависимости от Фазы 1:** нет (builder работает с JSON напрямую, не с report)

**Зависимости внутри frontend:**
- `CompanyField` — для списка доступных полей (name, display_name, type, level)
- API `companiesService.getFields(companyId)` — уже есть

**Файлы:**
- `components/condition-builder/ConditionBuilder.tsx` — **новый**, точка входа, верхнеуровневый компонент
- `components/condition-builder/ConditionGroupEditor.tsx` — **новый**, рекурсивный компонент группы (AND/OR)
- `components/condition-builder/ConditionRuleRow.tsx` — **новый**, одна строка-лист (поле + оператор + значение)
- `components/condition-builder/types.ts` — **новый**, внутренние типы builder state (дерево)
- `components/condition-builder/serializer.ts` — **новый**, JSON ↔ builder tree конвертация
- `components/StageFormModal.tsx` — интеграция builder + передача `transition_condition` при save
- `types/api.ts` — тип `ConditionNode` для API-ответа report

**Зависимость: `nanoid`** — отсутствует в `package.json`. Использовать `crypto.randomUUID()` (встроен в браузеры) для `RuleId` вместо `nanoid`.

**Внутренние типы builder (дерево):**

```typescript
type RuleId = string; // crypto.randomUUID() для React key

interface BuilderRule {
  id: RuleId;
  type: 'rule';
  field: string;         // "order_fields.budget" | "$stage_completed" | "$any" | ...
  operator: string;      // "$eq" | "$gte" | "$exists" | ...
  value: unknown;
}

interface BuilderGroup {
  id: RuleId;
  type: 'group';
  logic: 'and' | 'or';
  children: BuilderNode[];
}

type BuilderNode = BuilderRule | BuilderGroup;
```

**Архитектура builder:**

Рекурсивная структура. Каждый `ConditionGroupEditor` рендерит:

```
┌──────────────────────────────────────────────┐
│  [AND ▼ / OR]                                │
│                                              │
│  [Поле ▼]  [Оператор ▼]  [Значение ...]  [×]│
│  [Поле ▼]  [Оператор ▼]  [Значение ...]  [×]│
│                                              │
│  ┌─ вложенная группа ────────────────────┐   │
│  │  [OR ▼]                               │   │
│  │  [Поле ▼]  [Оператор ▼]  [...]   [×] │   │
│  │  [Поле ▼]  [Оператор ▼]  [...]   [×] │   │
│  │  [+ Условие]                          │   │
│  └───────────────────────────────[× Гр.]─┘   │
│                                              │
│  [+ Условие]  [+ Группа]                    │
└──────────────────────────────────────────────┘
```

Ограничение глубины: **макс 3 уровня** (root AND → вложенный OR → вложенный AND). При достижении лимита кнопка «+ Группа» не показывается.

**Специальные правила (без поля):**
- `$any` → переключатель «Любой заказ (всегда)» — на уровне root group, отключает остальные правила
- `$stage_completed` → тип правила в dropdown поля, вместо выбора поля — выбор стадии из списка
- `$prev_stage_completed` → тип правила в dropdown поля, чекбокс-значение

**Конвертация (serializer.ts):**
- `builderTreeToJson(root: BuilderGroup): Record<string, unknown>` — рекурсивно обходит дерево
- `jsonToBuilderTree(json: Record<string, unknown>): BuilderGroup | null` — парсит JSON, строит дерево
- Если JSON содержит конструкции, не покрытые builder-ом → `jsonToBuilderTree` возвращает `null` → fallback на raw editor с предупреждением

**Dropdown с raw JSON:** под конструктором — сворачиваемый блок «JSON (для отладки)» с `<textarea>`, read-only по умолчанию, с кнопкой «Редактировать вручную» (переключает в raw mode, отключает визуальный builder).

---

### Фаза 3 — Frontend: Condition Report в UI

**Модуль:** `sales-front`

**Зависимости от Фазы 1:** `ConditionReport` и `ConditionClause` в ответе `stage-requirements` API

**Цель:** Показать в `StageDetailModal` и на карточке заказа в воронке, какие условия выполнены.

**Файлы:**
- `components/ConditionReportView.tsx` — **новый**, рекурсивный рендер дерева `ConditionGroup`/`ConditionClause`
- `components/StageDetailModal.tsx` — интеграция report (вместо raw JSON `<pre>`)
- `types/api.ts` — типы `ConditionClause`, `ConditionGroup`, `ConditionReport`, `NextStageInfo`
- `services/orders.ts` — добавить метод `getStageRequirements(companyId, orderId)`. Endpoint `API_ENDPOINTS.ORDERS.STAGE_REQUIREMENTS` уже определён в `endpoints.ts`, но метод в `ordersService` отсутствует.

**UI отчёта (рекурсивный):**
```
Условия перехода в «Квалификация»
  Все условия (AND):
    ✅ Бюджет ≥ 1000               (текущее: 5000)
    ❌ Любое из (OR):
       ✅ Город клиента = "Москва"   (текущее: "Москва")
       ❌ Регион = "МО"              (не заполнено)
    ✅ Пройдена стадия «Новый»
```

JSON dropdown: под списком условий, свёрнутый по умолчанию, `<details><summary>JSON</summary><pre>...</pre></details>`.

---

## Решения

| Вопрос | Решение |
|--------|---------|
| Где живёт builder state? | Локальный React state в `ConditionBuilder`, конвертируется в JSON при save |
| Как обрабатывать сложный ручной JSON? | Если парсинг в builder-формат падает → показываем raw editor с предупреждением |
| Nested $and/$or? | Поддержка вложенных групп до 3 уровней. Рекурсивный `ConditionGroupEditor`. |
| Откуда брать имена полей? | `companiesService.getFields(companyId)` → `CompanyField.name` + `display_name` |
| Откуда брать стадии для $stage_completed? | `useStages(companyId)` — уже используется |
| Типы значений в builder? | Определяются по `CompanyField.type`: string→текстовое поле, number→числовое, boolean→чекбокс, enum→select из options |
| Performance condition_detailed? | Вызывается только по запросу UI (stage-requirements endpoint), не на hot path |

---

## Edge cases и уточнения

### `$not` в builder
Backend поддерживает `$not` (логическая инверсия одного операнда). В builder `BuilderGroup.logic` — только `'and' | 'or'`.
**Решение:** `$not` не добавляем в визуальный builder — это редкий случай, покрывается raw JSON editor. Если builder встречает `$not` при парсинге JSON → fallback на raw mode.

### `$any` vs вложенные правила
`$any` — это "всегда true", конфликтует с другими правилами в той же группе. Если пользователь включает `$any`, остальные правила теряют смысл.
**Решение:** `$any` — toggle на уровне root. При включении визуально блокируем (disable) остальные правила и группы. Сохраняем как `{"$any": true}`.

### Implicit AND (несколько полей на верхнем уровне JSON)
Текущий движок трактует `{"field_a": {"$eq": 1}, "field_b": {"$eq": 2}}` как implicit AND — все ключи должны совпасть.
**Решение:** `jsonToBuilderTree` парсит такой JSON в `BuilderGroup { logic: "and", children: [...] }`. `builderTreeToJson` для AND-группы на root-уровне генерирует тот же плоский формат (без `$and` обёртки) для обратной совместимости.

### StageFormModal сейчас не передаёт `transition_condition`
Текущий `StageFormModal` вызывает `stagesService.update(companyId, stage.id, { name, color, is_final, auto_close })` — без `transition_condition`. Нужно добавить в save payload.
Backend `stages/service.py` уже принимает `transition_condition` и валидирует через `validate_condition`. Фронт-типы `UpdateStageRequest` и `CreateStageRequest` уже включают `transition_condition?: Record<string, unknown>`.

### File overlap между фазами
- `types/api.ts` — модифицируется в Фазе 2 (builder TS types) и Фазе 3 (report TS types). Если фазы выполняются одновременно — конфликт. **Рекомендация:** добавить все типы из обеих фаз в одном проходе в начале Фазы 2.
- `StageDetailModal.tsx` — только Фаза 3 (нет overlap).
- `StageFormModal.tsx` — только Фаза 2 (нет overlap).

---

## Вне скоупа

- Drag-and-drop правил внутри builder
- Кастомные формулы / expression language
- Real-time preview результата условий в builder (требует вызова API с контекстом)
- Визуальный прогресс-бар на карточке заказа в Kanban (можно добавить позже на базе report)

---

## Рекомендуемая модель для выполнения

**Claude Sonnet 4.6** — 2 модуля (backend + frontend), чёткий план с файлами и контрактами, умеренная сложность. Backend-часть — добавление одной функции + расширение схемы. Frontend — новый компонент со своей логикой конвертации JSON↔builder, но без архитектурных решений.

Фазы 1 и 2 можно выполнять параллельно (нет зависимости). Фаза 3 зависит от Фазы 1.
