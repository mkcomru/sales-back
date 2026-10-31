# 023 — Remove Stage Result Field & Agent-Driven Order Closure

## Objective

Убрать поле `result` из модели `StageTemplate` и реализовать закрытие заказов через агента с помощью специальной тулзы, которая устанавливает `result` напрямую в модели `Order`.

---

## Context

Сейчас:
- У `StageTemplate` есть поле `result` (WON/LOST)
- При автопереходе на финальную стадию `result` копируется из стадии в заказ
- Это создает жесткую связку между стадиями и результатами

Проблема:
- Одна финальная стадия "Закрыто" не может одновременно быть и выигранной, и проигранной
- Невозможно написать условие автоперехода для финальной стадии (не знаем, когда выиграли, когда проиграли)

Решение:
- Убрать `result` из стадий полностью
- Агент сам решает, когда закрывать заказ и с каким результатом
- Агент использует тулзу для перевода на финальную стадию + установки результата

---

## Phase 1: Прекращение использования поля `result` в StageTemplate

**Важно:** Поле `result` остается в модели и БД, но больше не используется в бизнес-логике. Это обеспечивает обратную совместимость и позволяет избежать миграции данных.

### 1.1. Изменения в schemas

**Файл:** `apps/backend/src/backend/modules/stages/schemas.py`

Удалить из `StageTemplateBase`:
- Поле `result`
- Валидацию `validate_final_stage_fields` (проверка на обязательность `result` для `is_final`)

Удалить из `StageTemplateUpdateRequest`:
- Поле `result`
- Соответствующую валидацию

Удалить из `StageTemplateResponse`:
- Поле `result`
- В `from_model()` не передавать `result`

Оставить только валидацию:
- `auto_close` требует `is_final=True`
- Валидация `transition_condition` (синтаксис)

**Примечание:** В модели `StageTemplate` поле `result` остается, но не используется. Это сохраняет структуру БД и избегает breaking changes на уровне схемы.

### 1.2. Изменения в repository

**Файл:** `apps/backend/src/backend/modules/stages/repository.py`

- `create_stage()` - удалить параметр `result`, не передавать в создание модели
- `update_stage()` - удалить параметр `result`, не обновлять это поле

**Примечание:** Методы репозитория перестают работать с полем `result`, но само поле в модели остается нетронутым.

### 1.3. Изменения в service

**Файл:** `apps/backend/src/backend/modules/stages/service.py`

- `create_stage()` - удалить параметр `result` и валидацию `is_final → result required`
- `update_stage()` - удалить параметр `result` и валидацию
- `create_default_stages()` - не устанавливать `result` для дефолтных стадий (поле останется NULL)

### 1.4. Изменения в routers

**Файл:** `apps/backend/src/backend/modules/stages/routers.py`

- `create_stage()` - не передавать `result` в service
- `update_stage()` - не передавать `result` в service

### 1.5. Убрать автозакрытие через stage.result

**Файл:** `apps/backend/src/backend/modules/orders/service.py` (строки 218-230)

**Было:**
```python
if (furthest_matching_stage.is_final 
    and furthest_matching_stage.auto_close 
    and furthest_matching_stage.result):
    order = await self.orders_repo.close_order(order, furthest_matching_stage.result, ...)
```

**Станет:**
```python
# Убрать этот блок полностью
# Перевод на финальную стадию теперь НЕ закрывает заказ автоматически
# Агент сам должен вызвать тулзу close_order для закрытия
```

**Важно:** Автопереходы на финальную стадию теперь только меняют `order.stage`, но НЕ устанавливают `order.closed_at` и `order.result`. Закрытие — отдельное действие через тулзу агента.

### 1.6. Обновление тестов

Найти и обновить все тесты, которые:
- Проверяют `stage.result`
- Создают стадии с `result=OrderResult.WON/LOST`
- Проверяют автозакрытие через `stage.result`

Файлы:
- `tests/domains/stages/test_services.py`
- `tests/domains/stages/test_routers.py`
- `tests/domains/orders/test_auto_transitions.py`
- `tests/domains/orders/conftest.py`
- `tests/integration/stages/test_full_funnel_flow.py`

---

## Phase 2: Тулза для агента - закрытие заказа

### 2.1. Создать новую тулзу `close_order`

**Файл:** `apps/sales-agent/src/sales_agent/agents/tools.py` (или новый файл)

```python
async def close_order(
    order_id: int,
    result: Literal["won", "lost"],
    reason: str | None = None
) -> dict:
    """Close order with result.
    
    Args:
        order_id: Order ID to close
        result: Order result - "won" or "lost"
        reason: Optional closure reason
        
    Returns:
        Updated order data
    """
    # 1. Получить заказ
    # 2. Проверить, что заказ не закрыт
    # 3. Получить финальную стадию компании (is_final=True)
    # 4. Перевести заказ на финальную стадию
    # 5. Создать OrderLog
    # 6. Установить order.result = result
    # 7. Создать OrderLog
    # 8. Установить order.closed_at = now()
    # 9. Сохранить
    # 10. Создать OrderLog
```

### 2.2. Зарегистрировать тулзу

Добавить в список доступных тулз для агента.

### 2.3. Обновить промпт агента

Объяснить агенту, когда использовать тулзу `close_order`:
- Когда клиент явно отказался → `result="lost"`
- Когда сделка успешно завершена → `result="won"`
- Агент должен явно вызвать тулзу, а не ждать автоперехода

### 2.4. Тесты для тулзы

- Проверить успешное закрытие с `won`
- Проверить успешное закрытие с `lost`
- Проверить, что нельзя закрыть уже закрытый заказ
- Проверить создание `OrderLog`

---

## Phase 3: Решение проблемы с position для финальной стадии

### Проблема

Дефолтные стадии:
- "Новый" → `position=0` ✅
- "Закрыто" → `position=?` ❓

Компания может создать произвольное количество промежуточных стадий:
- "Квалификация" → `position=1`
- "Предложение" → `position=2`
- "Переговоры" → `position=3`
- ... и так далее

Если установить `position=1` для "Закрыто", то промежуточные стадии окажутся после финальной.

### Варианты решения

#### Вариант A: Большой gap (текущая реализация)

```python
"Новый" → position=0
"Закрыто" → position=1000  # или 9999
```

**Плюсы:**
- ✅ Просто реализовать
- ✅ Промежуточные стадии автоматически встают между (1, 2, 3... 999)
- ✅ Не нужна дополнительная логика

**Минусы:**
- ❌ "Магическое число" 1000 в коде
- ❌ Если компания создаст 1000+ стадий, финальная окажется в середине
- ❌ Некрасиво выглядит в UI (position=1000)

#### Вариант B: Динамическое вычисление position

Не хранить реальный `position` для финальной стадии, а вычислять его динамически:

```python
# При получении списка стадий:
stages = await StageTemplate.filter(company_id=company_id).order_by("position").all()

# Пересчитать position для финальной стадии
max_position = max(s.position for s in stages if not s.is_final)
for stage in stages:
    if stage.is_final:
        stage.position = max_position + 1  # виртуальный position
```

**Плюсы:**
- ✅ Финальная стадия всегда последняя
- ✅ Работает при любом количестве стадий
- ✅ Красиво в UI (всегда следующий номер)

**Минусы:**
- ❌ Сложнее - нужно пересчитывать при каждом запросе
- ❌ Нужно обновлять в нескольких местах (list, get, API responses)
- ❌ Проблемы с сортировкой на уровне БД

#### Вариант C: Виртуальное поле в схемах

Хранить в БД любое значение (например, 1000), но в API responses заменять на правильное:

```python
# StageTemplateResponse.from_model()
@classmethod
def from_model(cls, stage: StageTemplate, computed_position: int | None = None):
    return cls(
        ...
        position=computed_position if computed_position is not None else stage.position,
        ...
    )
```

**Плюсы:**
- ✅ Простая реализация
- ✅ Не ломает БД
- ✅ Красиво в API

**Минусы:**
- ❌ Нужно передавать `computed_position` во все вызовы
- ❌ Дублирование логики

#### Вариант D: Отдельное поле `display_position`

Добавить новое поле `display_position` только для UI:

```python
# Модель
position = fields.IntField()  # реальная позиция в БД
display_position = fields.IntField(null=True)  # для отображения

# При получении списка:
if stage.is_final and stage.display_position is None:
    stage.display_position = max_position + 1
```

**Плюсы:**
- ✅ Разделение concerns
- ✅ Гибко

**Минусы:**
- ❌ Дополнительное поле в БД
- ❌ Усложнение модели

#### Вариант E: Reorder при создании промежуточных стадий

При создании новой стадии автоматически переставлять финальную в конец:

```python
async def create_stage(...):
    # Создать стадию с position = max_position + 1
    new_stage = await create(...)
    
    # Если есть финальные стадии, сдвинуть их в конец
    final_stages = await StageTemplate.filter(company_id=..., is_final=True).all()
    for final in final_stages:
        final.position = new_stage.position + 1
        await final.save()
```

**Плюсы:**
- ✅ Финальная стадия всегда последняя
- ✅ Реальные position в БД корректные

**Минусы:**
- ❌ Дополнительные UPDATE при каждом создании стадии
- ❌ Проблемы с UNIQUE constraint `(company_id, position)`
- ❌ Сложная логика

---

### Уточняющие вопросы

1. **Сколько финальных стадий может быть?**
   - Сейчас одна: "Закрыто"
   - Может ли компания создать несколько финальных стадий в будущем?
   - Если да, как их упорядочивать?

2. **Нужно ли переупорядочивание (reorder)?**
   - Будет ли у компании возможность менять порядок стадий через UI?
   - Если да, то как поведет себя финальная стадия при reorder?

3. **Максимальное количество стадий?**
   - Есть ли реальное ограничение на количество стадий?
   - 10? 50? 100?
   - Это влияет на выбор варианта A (gap)

4. **Важность реального position в БД?**
   - Используется ли `position` для сортировки только в UI?
   - Или есть бизнес-логика, которая опирается на реальные значения?

5. **Миграция существующих данных?**
   - Есть ли уже компании в продакшене?
   - Нужно ли сохранить их текущие position?

---

### Рекомендация

**Для MVP: Вариант A (большой gap) + position=9999**

```python
defaults = [
    {
        "name": "Новый",
        "position": 0,
        "is_system": True,
        ...
    },
    {
        "name": "Закрыто",
        "position": 9999,  # 👈 большой gap
        "is_final": True,
        "is_system": True,
        ...
    },
]
```

**Причины:**
- ✅ Работает прямо сейчас без изменений
- ✅ Покрывает 99% реальных кейсов (мало кто создаст >100 стадий)
- ✅ Не усложняет код
- ✅ Можно мигрировать на Вариант C позже, если нужно

**Для production: Вариант C (виртуальное поле в схемах)**

Когда станет важна красота API responses:
- Хранить `position=9999` в БД
- Вычислять правильный `position` при формировании API ответа
- Frontend всегда видит красивые последовательные номера

---

## Checklist

### Phase 1: Прекращение использования stage.result
- [ ] Обновить schemas (удалить поле + валидации)
- [ ] Обновить repository
- [ ] Обновить service
- [ ] Обновить routers
- [ ] Убрать автозакрытие через stage.result
- [ ] Обновить все тесты

### Phase 2: Тулза для агента
- [ ] Создать тулзу `close_order`
- [ ] Зарегистрировать в агенте
- [ ] Обновить промпт
- [ ] Написать тесты для тулзы

### Phase 3: Position для финальной стадии
- [ ] Принять решение по варианту
- [ ] Реализовать выбранный вариант
- [ ] Обновить create_default_stages()
- [ ] Протестировать создание/удаление/reorder стадий

---

## Risks

1. **Изменение API:** Удаление `stage.result` из API responses - breaking change для клиентов (но в модели БД остается)
2. **Автопереходы:** Финальная стадия больше не может иметь `transition_condition`
3. **Агент должен всегда закрывать:** Если агент забудет вызвать тулзу, заказ зависнет на финальной стадии
4. **Position overflow:** При варианте A есть теоретический лимит (9999 стадий)

---

## Follow-up Tasks

- Обновить документацию API
- Обновить `docs/architecture.md`
- Добавить метрики: сколько заказов закрыл агент vs вручную
- Рассмотреть добавление `close_reason: str` в Order для детализации

