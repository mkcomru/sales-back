# Архитектура LLM

Этот документ описывает архитектуру LLM-интеграции Sales Agent, включая кастомный LLM клиент, tool loop и систему тулзов.

## Общая архитектура

Sales Agent использует **кастомный LLMClient** с собственным **tool loop** для оркестрации диалогов. Это обеспечивает полный контроль над вызовами LLM и выполнением тулзов.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          LLM Layer                                      │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐   │
│  │   LLMClient      │    │   run_tool_loop  │    │   ToolRegistry   │   │
│  │ (client.py)      │◄──►│   (loop.py)      │◄──►│   (registry.py)  │   │
│  └──────────────────┘    └──────────────────┘    └──────────────────┘   │
│           │                       │                       │             │
│           ▼                       ▼                       ▼             │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    OpenAI-compatible API                         │   │
│  │  • Chat Completions (GPT-4, Claude via OpenRouter)               │   │
│  │  • Responses API (GPT-5/o1/o3)                                   │   │
│  │  • Structured Outputs (json_schema)                              │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## LLMClient

Кастомный клиент для OpenAI-compatible Chat Completions API.

**Расположение:** `apps/sales-agent/src/sales_agent/core/llm/client.py`

### Возможности

- **Унифицированный интерфейс** для разных провайдеров (OpenAI, OpenRouter, etc.)
- **Поддержка GPT-5/o1/o3** через Responses API с `reasoning_effort` и `verbosity`
- **Structured outputs** через `chat_parse` с Pydantic-моделями
- **Langfuse интеграция** для автоматического трейсинга

### Методы

| Метод | Описание |
|-------|----------|
| `chat()` | Базовый вызов Chat Completions с поддержкой tools |
| `chat_stream()` | Стриминговый вызов (без tool calling) |
| `chat_parse()` | Structured output с Pydantic-валидацией |

### Пример использования

```python
from src.sales_agent.core.llm.client import LLMClient

# Создание из настроек
llm = LLMClient.from_settings(settings, model="gpt-4o")

# Обычный вызов
response = await llm.chat(
    messages=[{"role": "user", "content": "Привет"}],
    temperature=0.7,
)

# Structured output
decision = await llm.chat_parse(
    messages=messages,
    response_model=RouterDecision,
    temperature=0.1,
)
```

## Tool Loop

Реализация цикла вызова тулзов для function calling.

**Расположение:** `apps/sales-agent/src/sales_agent/core/llm/loop.py`

### Алгоритм

```
┌─────────────────┐
│ Входные данные  │
│ messages, tools │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  llm.chat()     │
│  с tools        │
└────────┬────────┘
         │
         ▼
    ┌────────────┐     Нет      ┌─────────────────┐
    │ tool_calls │─────────────►│ Вернуть текст   │
    │    есть?   │              │ final_text      │
    └────────────┘              └─────────────────┘
         │ Да
         ▼
┌─────────────────┐
│ Для каждого     │
│ tool_call:      │
│ • найти handler │
│ • выполнить     │
│ • добавить в    │
│   messages      │
└────────┬────────┘
         │
         ▼
    ┌────────────┐
    │ iterations │     Да      ┌─────────────────┐
    │ < max_calls│────────────►│ Повторить цикл  │
    └────────────┘              └─────────────────┘
         │ Нет
         ▼
┌─────────────────┐
│ ValueError:     │
│ max_calls       │
│ exceeded        │
└─────────────────┘
```

### Параметры

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `llm` | `LLMClient` | - | Клиент для LLM вызовов |
| `messages` | `list[dict]` | - | Начальные сообщения |
| `tools` | `list[ToolSpec]` | - | Доступные тулзы |
| `max_calls` | `int` | 6 | Максимум итераций |
| `temperature` | `float` | None | Температура сэмплирования |
| `reasoning_effort` | `str` | None | Для GPT-5: "minimal"/"low"/"medium"/"high" |
| `tracer` | `Tracer` | None | Для телеметрии |

### Пример использования

```python
from src.sales_agent.core.llm.loop import run_tool_loop

final_messages, final_text = await run_tool_loop(
    llm=large_llm_client,
    messages=messages,
    tools=tools,
    temperature=0.6,
    max_completion_tokens=2048,
    tracer=tracer,
)
```

## ToolSpec

Спецификация тулзы для регистрации в системе.

**Расположение:** `apps/sales-agent/src/sales_agent/core/tools/spec.py`

### Структура

```python
@dataclass
class ToolSpec:
    name: str                           # Уникальное имя
    description: str                    # Описание для LLM
    parameters: dict[str, Any]          # JSON Schema параметров
    handler: Callable[[dict], Any]      # Функция-обработчик
```

### Регистрация тулзов

Тулзы собираются динамически в `ToolRegistry`:

```python
from src.sales_agent.core.tools.registry import build_category_expert_tools

tools = build_category_expert_tools(
    settings=settings,
    user_id=user_id,
    message=message,
    category_id=category_id,
)
```

## Тулзы

### search_product

Тулза поиска продуктов в категории с поддержкой фильтрации по атрибутам и fuzzy-поиска.

**Расположение:** `apps/sales-agent/src/sales_agent/agents/tools.py`

#### Параметры

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `filters` | `object` | Нет | Фильтры на основе собранных данных о клиенте (`customer_answers`) |
| `query` | `string` | Нет | Текстовый запрос для поиска по названию/описанию |
| `limit` | `integer` | Нет | Максимальное количество результатов (по умолчанию 10) |

#### Логика работы

```
┌───────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│ Входные данные│────►│ Фильтрация по       │────►│ Fuzzy-matching   │
│ (filters,     │     │ категории           │     │ (query)          │
│  query,       │     │ (category_id)       │     │                  │
│  limit)       │     └─────────────────────┘     └────────┬─────────┘
└───────────────┘                                          │
                                                           ▼
                      ┌─────────────────────┐     ┌──────────────────┐
                      │ Сортировка по       │◄────│ Attribute        │
                      │ релевантности       │     │ matching         │
                      │ (match_score)       │     │                  │
                      └─────────┬───────────┘     └──────────────────┘
                                │
                                ▼
                      ┌─────────────────────┐
                      │ Результат:          │
                      │ ProductSearchResult │
                      └─────────────────────┘
```

**Шаг 1: Фильтрация по категории**
- Отбираются только продукты с `category_id`, соответствующим текущей категории клиента

**Шаг 2: Attribute matching**
- Сравнение атрибутов продукта с ответами клиента
- Поддерживаемые типы:
  - **Списки**: проверка вхождения (`customer_value in product_attr`)
  - **Числа с `max_*`**: клиент ≤ продукт
  - **Числа с `min_*`**: клиент ≥ продукт
  - **Прочее**: точное совпадение
- Начисление очков за каждый совпавший атрибут

**Шаг 3: Fuzzy-matching (опционально)**
- Если передан `query` — применяется fuzzy-поиск
- Нормализация: lowercase, удаление диакритики, нормализация пробелов
- Методы:
  - Прямое вхождение подстроки
  - Посимвольное сравнение слов (threshold ≥ 0.6)
- Бонусы:
  - +3.0 за совпадение в названии
  - +1.5 за совпадение в описании

**Шаг 4: Сортировка и ограничение**
- Сортировка по `match_score` (убывание)
- Ограничение по `limit`

#### Возвращаемое значение

```python
class ProductSearchResult:
    id: int                    # ID продукта
    name: str                  # Название
    description: str           # Описание
    attributes: dict           # Атрибуты продукта
    fields: list[dict]         # Product-level поля для сбора
    match_score: float         # Релевантность (выше = лучше)

class SearchProductOutput:
    products: list[ProductSearchResult]  # Найденные продукты
    message: str                          # Сообщение о результатах
```

#### Пример использования

**Запрос:**
```json
{
  "filters": {
    "destination": "Кавказ",
    "budget": 40000
  },
  "query": "Эльбрус",
  "limit": 5
}
```

**Ответ:**
```json
{
  "products": [
    {
      "id": 1,
      "name": "Восхождение на Эльбрус",
      "description": "Классический маршрут...",
      "attributes": {
        "destination": ["Кавказ", "Эльбрус"],
        "max_price": 45000
      },
      "fields": [
        {"name": "preferred_date", "label": "Предпочтительная дата"}
      ],
      "match_score": 5.0
    }
  ],
  "message": "Найдено 1 подходящих вариантов."
}
```

### set_customer_fields

Сохранение данных о клиенте.

#### Параметры

| Параметр | Тип | Описание |
|----------|-----|----------|
| `updates` | `object` | Словарь полей для обновления |

#### Пример

```json
{
  "updates": {
    "selected_product_id": 3,
    "preferred_date": "2025-07-15"
  }
}
```

## Промпты

### Расположение

Промпты хранятся в базе данных и загружаются через `PromptService`:

```python
from src.sales_agent.services.prompt_service import PromptService, PromptType

prompt_service = PromptService(backend_client=backend_client)
prompt = await prompt_service.load_prompt(PromptType.QUALIFIER)
```

### Форматирование

`PromptFormatter` заполняет плейсхолдеры данными компании:

```python
from src.sales_agent.services.prompt_formatter import PromptFormatter

formatter = PromptFormatter()
filled_prompt = formatter.format_prompt(
    template=prompt_template,
    company_data=company_spec,
    customer_answers=answers,
)
```

### Плейсхолдеры

| Плейсхолдер | Описание |
|-------------|----------|
| `{customer_answers}` | JSON с собранными ответами |
| `{stage_rules}` | Правила текущего этапа |
| `{company.name}` | Название компании |
| `{company.category.fields}` | Поля категории для сбора |
| `{company.selected_product.name}` | Название выбранного продукта |
| `{company.selected_product.fields}` | Product-level поля |

## Конфигурация тулзов

### Регистрация в базе данных

Тулзы регистрируются в таблице `tools`:

```sql
INSERT INTO tools (name, description, enabled_by_default) VALUES
('search_product', 'Подбирает продукты по атрибутам и текстовому запросу', true);
```

### Привязка к компании

Компания может переопределить описание или отключить тулзу:

```sql
INSERT INTO company_tools (company_id, tool_id, enabled, custom_description) VALUES
(1, 17, true, 'Поиск туров по критериям клиента');
```

## Мониторинг и телеметрия

### Langfuse

При наличии ключей Langfuse автоматически трейсит:
- Вызовы LLM через `AsyncOpenAI` wrapper
- Использование тулзов через `Tracer.start_span`
- Latency и token usage

### Tracer

Кастомный трейсер для структурированной телеметрии:

```python
from src.sales_agent.core.telemetry import Tracer

with tracer.start_trace(
    name="chat.process",
    input=text[:200],
    tags=["sales-agent"],
    user_id=str(user_id),
):
    with tracer.start_span(name="qualifier.invoke", input={"text": text}):
        # ... обработка
        tracer.update_current_span(output=reply)
```

### Логирование

Структурированные логи через `structlog`:
```python
log.info(
    "tool_executed",
    tool_name="search_product",
    category_id=3,
    results_count=5,
    duration_ms=120,
)
```

## Модели LLM

### Конфигурация

Настраивается через `SalesAgentSettings.llm`:

```yaml
llm:
  base_url: "https://api.openai.com/v1"  # или OpenRouter
  api_key: "${LLM__API_KEY}"             # из переменной окружения
  light_model: "gpt-4o-mini"             # для Router
  large_model: "gpt-4o"                  # для Qualifier/CategoryExpert
```

### Два клиента

В пайплайне используются два клиента:
- **light_llm_client** — для быстрых решений Router (structured output)
- **large_llm_client** — для Qualifier и Category Expert (tool loop)

```python
light_llm_client = LLMClient.from_settings(settings, model=settings.llm.light_model)
large_llm_client = LLMClient.from_settings(settings, model=settings.llm.large_model)
```

## См. также

- [schema.md](schema.md) — схема диалогового пайплайна
- [tech.md](tech.md) — технологический стек
- [product.md](product.md) — обзор продукта
