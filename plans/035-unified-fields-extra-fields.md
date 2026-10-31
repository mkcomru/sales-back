# 035: Unified Fields Tool + Extra Fields

---

## Зачем это делаем

Сейчас `set_customer_fields` и `update_order_fields` — два отдельных тула с дублированным кодом валидации. При этом:

- **AI может записать произвольные ключи** в `customer_fields`, и они тихо сохраняются в БД рядом со схемными полями — нет разделения "определено компанией" vs "придумано агентом"
- **Менеджер не видит контекст** — если агент собрал доп. информацию (бюджет, срочность, комментарий), она либо теряется, либо засоряет схемные поля
- **Order fields не возвращаются в промпт** — агент не видит что уже заполнил в заказе

После реализации:
- Один тул `update_fields` — агент шлёт все поля одним вызовом, backend сам раскладывает по `customer_fields`, `order_fields`, `extra_fields`
- Extra fields хранятся на **заказе** (`Order.extra_fields`) — привязаны к конкретной сделке, не пачкают профиль клиента, сбрасываются с новым заказом
- Менеджер видит и может редактировать/удалять extra fields на фронте в отдельной секции "Дополнительно"
- Агент получает обратно в промпт и extra_fields, и order_fields — полная картина
- Тул строго ограничивает extra_fields: только ключевые данные, полезные менеджеру для продажи. Динамические, эфемерные или мусорные ключи не сохраняются

---

## Текущее состояние

### Что есть
- `set_customer_fields` tool (sales-agent) — валидирует только enum, всё остальное принимает as-is
- `update_order_fields` tool (sales-agent) — аналогичная копия для order-level полей
- `Customer.customer_fields` JSONField — плоский dict, без разделения схемных/произвольных ключей
- `Order.order_fields` JSONField — аналогичный плоский dict
- Backend `PATCH /internal/customers/{user_id}/fields` — слепо мержит `updates` в `customer_fields`
- Backend `PATCH /internal/orders/{order_id}/fields` — слепо мержит в `order_fields`
- Фронт `CustomerProfile.tsx` — рендерит схемные поля + fallback для неизвестных ключей (случайный, не намеренный)
- Промпт `agent.md` — содержит `{{ customer_answers }}`, но не `order_fields` и не extra

### Что нет
- Колонки `extra_fields` на модели `Order`
- Маршрутизации ключей по схеме на стороне backend
- Единого тула вместо двух
- Отображения extra_fields на фронте как отдельной секции
- Order fields в промпте агента

---

## Важные детали реализации

### Stage recalculation

Текущий `ChatService.update_customer_fields` вызывает `OrderService.recalculate_stage()` для всех активных не-frozen заказов клиента. `OrderService.update_order_fields` также вызывает `recalculate_stage`. Новый `update_fields_unified` **должен сохранить это поведение** — вызвать recalculate один раз после обновления полей (не дважды).

### Cross-module зависимость

Order fields обновляются через `OrderService` / `OrdersRepository` (`apps/backend/src/backend/modules/orders/`), а не через `ChatService`. Эндпоинт `PATCH /internal/orders/{order_id}/fields` живёт в orders-модуле. Unified метод в `ChatService` должен вызывать `OrderService.update_order_fields()` — это создаёт cross-module вызов. Альтернатива: вынести unified метод в отдельный сервис. Проще — импортировать `OrderService` в `ChatService` (уже делается для `recalculate_stage`).

### AvailableTool enum и TOOL_CATALOG

`libs/common/src/common/tools.py` содержит `AvailableTool(StrEnum)` с `SET_CUSTOMER_FIELDS` и `UPDATE_ORDER_FIELDS`. Нужно заменить на `UPDATE_FIELDS = "update_fields"`.

Также `TOOL_CATALOG` группирует тулы: `SET_CUSTOMER_FIELDS` в `ToolGroup.CUSTOMER`, `UPDATE_ORDER_FIELDS` в `ToolGroup.ORDER_MANAGEMENT`. Нужно убрать оба и добавить `UPDATE_FIELDS` (в `ORDER_MANAGEMENT` или `CUSTOMER` — решить при реализации).

### AgentContext в libs/common

`AgentContext` в `libs/common/src/common/models/outbound.py` не содержит `extra_fields` и `order_fields`. Нужно добавить оба поля в модель. Это затрагивает `libs/common` — дополнительный модуль.

### Context assembly не имеет доступа к Order

`AgentContextAssembler.build()` принимает `company_id`, `user_id`, `thread_id`, `conversation_id` — **без order_id**. Чтобы включить `order_fields` и `extra_fields` в контекст, нужно:
- Передать `order_id` в `build()`
- Загрузить Order и взять `order.order_fields` и `order.extra_fields`

### customer_store.update_customer_fields — не удалять

`customer_store.update_customer_fields()` используется НЕ ТОЛЬКО тулом `set_customer_fields`. Также вызывается:
- `message_processor.py` (~строка 252) — при ошибке LLM пишет `handoff_summary` в customer_fields
- Потенциально handoff-тулом

Эту функцию **нельзя удалять** из `customer_store.py`. Она продолжает вызывать `backend_client.update_customer_fields()`. Нужно адаптировать: `backend_client` должен уметь слать запрос без `order_id` (для системных записей в customer_fields).

### order_id в UpdateFieldsUnifiedRequest — опциональный

`message_processor.py` и handoff-путь вызывают `update_customer_fields` без контекста заказа. Поэтому `order_id` в `UpdateFieldsUnifiedRequest` должен быть **опциональным** (`int | None`). Поведение при `order_id=None`:
- customer-schema ключи → `customer_fields` (как обычно)
- order-schema ключи → **отклоняются** (некуда положить без заказа)
- extra ключи → **отбрасываются** (некуда положить без заказа)

### Тесты

`test_pipeline_e2e.py` (строки 188, 262, 301, 404) и `test_pipeline.py` (строка 297) ссылаются на `set_customer_fields`. Нужно обновить на `update_fields`.

---

## Фазы

### Phase 1: Foundation — модель, миграция и общие типы

**Модули:** `apps/backend`, `libs/common`
**Файлы:**
- `apps/backend/src/backend/modules/orders/models.py` — добавить `extra_fields = fields.JSONField(default=dict)` на `Order`
- `apps/backend/migrations/models/` — новая миграция
- `libs/common/src/common/tools.py` — заменить `SET_CUSTOMER_FIELDS` + `UPDATE_ORDER_FIELDS` на `UPDATE_FIELDS = "update_fields"` в `AvailableTool`, обновить `TOOL_CATALOG`
- `libs/common/src/common/models/outbound.py` — добавить `extra_fields: dict[str, Any] = Field(default_factory=dict)` и `order_fields: dict[str, Any] = Field(default_factory=dict)` в `AgentContext`

**Шаги:**
1. Добавить колонку `extra_fields` в модель `Order`
2. `uv run aerich migrate --name add_order_extra_fields`
3. Вручную добавить `"backend".` префикс к таблицам в миграции
4. Обновить `AvailableTool` enum и `TOOL_CATALOG` (убрать `SET_CUSTOMER_FIELDS` из `CUSTOMER`, `UPDATE_ORDER_FIELDS` из `ORDER_MANAGEMENT`, добавить `UPDATE_FIELDS`)
5. Расширить `AgentContext`

---

### Phase 2: Backend — репозиторий, сервис маршрутизации, эндпоинт

**Модуль:** `apps/backend`
**Зависимости:** Phase 1 — колонка `Order.extra_fields` существует, `AvailableTool.UPDATE_FIELDS` доступен
**Файлы:**
- `apps/backend/src/backend/modules/orders/repository.py` — новый метод `update_extra_fields(order, updates) -> tuple[Order, dict]`
- `apps/backend/src/backend/modules/chat/service.py` — новый метод `update_fields_unified(user_id, company_id, updates, order_id)`
- `apps/backend/src/backend/modules/chat/schemas.py`:
  - Новый `RejectedField(BaseModel)` — `key: str, value: Any, reason: str, allowed: list[str] | None`
  - Расширить `CustomerFieldsUpdateRequest` → `UpdateFieldsUnifiedRequest(company_id, order_id: int | None, updates)`
  - Новый `UpdateFieldsUnifiedResponse(updated_customer, updated_order, updated_extra, rejected)`
- `apps/backend/src/backend/modules/chat/routers.py` — обновить `PATCH /internal/customers/{user_id}/fields`: принимать `UpdateFieldsUnifiedRequest`, возвращать `UpdateFieldsUnifiedResponse`, HTTP 200 вместо 204

**Логика `update_fields_unified(user_id, company_id, updates, order_id)`:**
```python
all_fields = await Field.filter(company_id=company_id).all()
customer_keys = {f.name for f in all_fields if f.level == FieldLevel.CUSTOMER}
order_keys = {f.name for f in all_fields if f.level == FieldLevel.ORDER}

# Enum-валидация для полей с type=enum
field_defs = {f.name: f for f in all_fields}
validated, rejected = _validate_enum_fields(updates, field_defs)

customer_updates, order_updates, extra_updates = {}, {}, {}
for key, value in validated.items():
    if key in customer_keys:
        customer_updates[key] = value
    elif key in order_keys:
        order_updates[key] = value
    else:
        extra_updates[key] = value

# Update customer_fields
customer, _ = await self.get_or_create_customer(user_id, company_id)
if customer_updates:
    await self.customers_repo.update_customer_fields(customer, customer_updates)

# Update order_fields + extra_fields (оба на Order)
order_service = OrderService()
if order_updates:
    await order_service.update_order_fields(order_id, order_updates, author_id=None)
if extra_updates:
    await orders_repo.update_extra_fields(order_id, extra_updates)

# Stage recalculation — один раз
# recalculate_stage уже вызывается внутри order_service.update_order_fields.
# Если были только customer_updates — вызвать recalculate отдельно для активных заказов.
# Если были order_updates — recalculate уже произошёл.
```

> **Внимание:** `OrderService.update_order_fields` вызывает `recalculate_stage` внутри. Если `customer_updates` тоже есть — текущая логика в `ChatService.update_customer_fields` делает отдельный `recalculate_stage`. Нужно либо передать флаг `skip_recalculate` в `OrderService`, либо вызвать `recalculate_stage` один раз в конце unified-метода.

---

### Phase 3: Backend — context assembly

**Модуль:** `apps/backend`
**Зависимости:** Phase 1 (колонка `Order.extra_fields`), Phase 2 не обязателен — assembly читает, не пишет
**Файлы:**
- `apps/backend/src/backend/modules/messages/context_assembly.py` — добавить `extra_fields` и `order_fields` в `AgentContext`

**Текущая проблема:** `AgentContextAssembler.build()` не принимает `order_id` и не имеет доступа к Order. Нужно:
1. Добавить `order_id: int | None = None` в сигнатуру `build()`
2. Если `order_id` передан — загрузить `Order` и взять `order.order_fields` и `order.extra_fields`

**Вызывающий код (2 места):**
1. `apps/backend/src/backend/modules/messages/routers.py` (~строка 265) — `order` уже доступен через `order_service.ensure_active_order(thread)`, передать `order_id=order.id`
2. `apps/backend/src/backend/workers/task_executor.py` (~строка 63) — `order` уже загружен через `self.order_service.get_order(...)`, передать `order_id=order.id`

---

### Phase 4: Sales-agent — единый тул

**Модуль:** `apps/sales-agent`
**Зависимости:** Phase 2 (новый формат `PATCH /internal/customers/{user_id}/fields` и `UpdateFieldsUnifiedResponse`)
**Файлы:**
- `apps/sales-agent/src/sales_agent/agents/tools.py`:
  - Удалить `set_customer_fields()` и `update_order_fields()`
  - Удалить `RejectedField`, `CustomerFieldsUpdateResponse`, `UpdateOrderFieldsResponse` (переехали на backend)
  - Добавить `update_fields(user_id, company_id, updates, order_id) -> UpdateFieldsResponse`
- `apps/sales-agent/src/sales_agent/core/tools/registry.py`:
  - Удалить `TOOL_SCHEMAS["set_customer_fields"]` и `TOOL_SCHEMAS["update_order_fields"]`
  - Удалить `_create_set_customer_fields_handler` и `_create_update_order_fields_handler`
  - Удалить `TOOL_DESCRIPTIONS["set_customer_fields"]` и `TOOL_DESCRIPTIONS["update_order_fields"]`
  - Добавить `TOOL_SCHEMAS["update_fields"]`, `TOOL_DESCRIPTIONS["update_fields"]`, `_create_update_fields_handler(user_id, company_id, order_id)`
- `apps/sales-agent/src/sales_agent/services/backend_client.py`:
  - Удалить `update_customer_fields()` и `update_order_fields()`
  - Добавить `update_fields(user_id, company_id, updates, order_id) -> dict`
- `apps/sales-agent/src/sales_agent/storage/customer_store.py` — `update_customer_fields()` **оставить** (используется message_processor и handoff). Удалить только `mark_rejected()` (unused).
- `apps/sales-agent/src/sales_agent/agents/types.py` — удалить `SetCustomerFieldsInput` если есть (использовалась для JSON-schema генерации)

**Тул `update_fields`:**
- Принимает `updates: dict[str, Any]` — agent передаёт все ключи без разделения
- `order_id` инжектится из контекста closure (как сейчас у `update_order_fields`)
- Блокирует `stage`/`stage_id`/`qualifier_done` если form pending (контекстная логика остаётся agent-side)
- Без локальной enum-валидации — backend отвечает за схему
- Вызывает `backend_client.update_fields(user_id, company_id, updates, order_id)`
- Парсит и возвращает агенту `UpdateFieldsResponse` (что обновлено, что отклонено)

**Tool description (для LLM) должен чётко ограничивать extra_fields:**
> Обновляет поля клиента и заказа. Используй ключи из списка полей компании.
> Если информация не вписывается ни в одно из существующих полей, но **критически важна для менеджера при продаже** — можешь добавить произвольный ключ. Это допустимо ТОЛЬКО для стабильных фактов: бюджет, конкретные требования, ограничения клиента, ключевое возражение.
> НЕ записывай: эмоции, настроение, временные состояния, даты первых/последних контактов, внутренние пометки. Всё что не поможет менеджеру закрыть сделку — не записывай.

---

### Phase 5: Sales-agent — промпт и тесты

**Модуль:** `apps/sales-agent`
**Зависимости:** Phase 3 (`extra_fields` и `order_fields` в `AgentContext` envelope)
**Файлы:**
- `apps/sales-agent/src/sales_agent/agents/prompts/agent.md` — добавить секции `{{ extra_fields }}` и `{{ order_fields }}`
- `apps/sales-agent/src/sales_agent/services/prompt_formatter.py` — прокинуть `extra_fields` и `order_fields` в Jinja2-контекст через `_prepare_data()`
- `apps/sales-agent/src/sales_agent/agents/pipeline.py` — извлечь `extra_fields` и `order_fields` из `agent_ctx` и передать в formatter
- `apps/sales-agent/src/sales_agent/services/company_context.py` — добавить ContextVars `_extra_fields` и `_order_fields` с getter/setter
- `apps/sales-agent/tests/test_pipeline_e2e.py` — обновить mock tool calls с `set_customer_fields` → `update_fields` (строки 188, 262, 301, 404)
- `apps/sales-agent/tests/test_pipeline.py` — обновить mock tool calls (строка 297)

---

### Phase 6: Frontend — типы и отображение

**Модуль:** `sales-front`
**Зависимости:** Phase 2 (backend возвращает `extra_fields` в ответах на заказе)
**Файлы:**
- `types/api.ts` — добавить `extra_fields: Record<string, string | number | boolean | null>` в `OrderResponse` (строка ~184)
- `components/CustomerProfile.tsx` — убрать случайный fallback для неизвестных ключей в customer_fields (строки 357–374, секция "Extra fields not in company schema")
- `components/OrderDetailPanel.tsx` — добавить секцию "Дополнительно" рендерящую `order.extra_fields` после существующей секции "Данные заказа" (строка ~166)
- `services/` — метод для PATCH extra_fields на заказе (или расширить существующий `ordersService`)

**Текущее состояние frontend:**
- `OrderSummary` (в списке тредов) — **не содержит** `order_fields`. Только `id`, `order_number`, `stage`, `assignee`
- `OrderResponse` (полная загрузка через `ordersService.getById()`) — **содержит** `order_fields`. Сюда добавить `extra_fields`
- `OrderDetailPanel` уже рендерит `order_fields` как `InfoRow`
- `CustomerProfile` рендерит customer-level поля по схеме + fallback для лишних

**UI секция "Дополнительно" в `OrderDetailPanel`:**
- Рендерится после секции "Данные заказа"
- Каждая строка: humanized key (read-only label), GhostInput для значения (editable), кнопка удаления
- Пустая секция скрыта

---

## Backward Compatibility

Нет прод-клиентов — полный переезд без оглядки на обратную совместимость. Dead code вырезаем:
- Старый `PATCH /internal/orders/{order_id}/fields` — удалить после создания unified-эндпоинта
- `CustomerFieldsUpdateRequest` — заменить на `UpdateFieldsUnifiedRequest`, старую схему удалить
- `update_customer_fields` / `update_order_fields` в `backend_client.py` и `customer_store.py` — удалить

---

## Рекомендуемая модель для выполнения

**Claude Opus 4.6** — 3+ модуля (backend, sales-agent, frontend), новая архитектура маршрутизации, миграция БД, удаление/замена тулов, изменение промпта. Высокий риск регрессии при неправильном разделении ключей.
