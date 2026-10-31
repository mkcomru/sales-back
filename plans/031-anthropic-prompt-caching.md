# Plan 031 — Anthropic Prompt Caching через OpenRouter

## Зачем это делаем

System prompt для каждого запроса — это ~15-25k токенов (агентная логика + конфиг компании + workflow + примеры + FAQ). Из них динамических данных (ответы клиента, форма, стадия) — менее 500 токенов. Каждый запрос пересчитывает весь prefix.

Anthropic поддерживает prefix caching: если начало запроса идентично токен-в-токен, кешированная часть стоит ~10% от обычной цены. Через OpenRouter это работает через `cache_control` в content blocks.

**Результат:** снижение стоимости input токенов на ~90% для повторных запросов в рамках одной компании (TTL кеша 5 минут).

---

## Анализ текущей архитектуры

### Как формируется system prompt сейчас

```
pipeline.py:202-212
  → PromptFormatter.format_prompt(template, company_spec, customer_answers, form, ...)
  → Jinja2 рендерит ВСЕ данные в один текст
  → _build_messages() кладёт его как {"role": "system", "content": "<text>"}
```

**Проблема:** `customer_answers` и `form_unified` вставляются ВНУТРЬ шаблона через Jinja2. Каждый запрос даёт другой system prompt → кеш никогда не попадает.

### Что статическое (не меняется между запросами одной компании)

| Блок | Источник |
|------|----------|
| Роль, Цель | prompt_template (DB) |
| Информация о компании | company_spec: name, description, tone_of_voice |
| Правила | company_spec: rules |
| Инструменты | company_spec: enabled_tools → TOOL_SCHEMAS/TOOL_DESCRIPTIONS |
| Поля для сбора | company_spec: fields |
| Workflow | company_spec: qualification_workflow |
| Примеры диалогов | company_spec: qualification_examples |
| Категория (если выбрана) | company_spec: categories → current_category.* |
| Стадии | company_spec: stages_config |

### Что динамическое (меняется каждый запрос)

| Блок | Источник |
|------|----------|
| customer_answers | agent_context.customer_answers — JSON с текущими значениями полей |
| form_unified | agent_context.form_data — данные формы |
| current_stage | metadata.order_stage.name — текущая стадия заказа |
| reminder_instructions | Текст напоминания (редко, только для task execution) |

### Структура шаблонов

Шаблоны (qualifier.md, category_expert.md) имеют чёткую структуру:
- Строки 1–N: статика (роль, компания, правила, инструменты, поля, workflow, примеры)
- Последний раздел `# Текущий контекст`: динамика (customer_answers, form_unified)

Это идеальный паттерн для кеширования — динамика УЖЕ в конце.

### Tools (OpenAI function calling)

Tools формируются в `build_tools()` из `enabled_tools` списка. Для одной компании этот список стабилен. OpenRouter кеширует tools как часть prefix → tools не ломают кеш.

### LLM Client

`AsyncOpenAI` с `base_url=openrouter`. Метод `chat()` передаёт `messages` как `list[dict]`. OpenAI SDK поддерживает content blocks в system message нативно.

---

## Решение

### Архитектура кеширования

```
SYSTEM MESSAGE (content blocks):
  ┌─────────────────────────────────────────────┐
  │ Block 1: STATIC PREFIX                      │
  │ - Rendered template БЕЗ dynamic данных      │
  │ - cache_control: {"type": "ephemeral"}      │
  │ (кешируется — одинаков для всех запросов    │
  │  одной компании)                            │
  └─────────────────────────────────────────────┘
  ┌─────────────────────────────────────────────┐
  │ Block 2: DYNAMIC CONTEXT                    │
  │ - customer_answers JSON                     │
  │ - form_unified JSON                         │
  │ - current_stage                             │
  │ (пересчитывается каждый запрос)             │
  └─────────────────────────────────────────────┘

TOOLS: [...]  ← стабильны per company, кешируются автоматически

MESSAGES:
  - history (user/assistant/tool)
  - current user message
```

---

## Шаги реализации

### Шаг 1: PromptFormatter — раздельный рендеринг

**Файл:** `apps/sales-agent/src/sales_agent/services/prompt_formatter.py`

Добавить метод `format_prompt_parts()` → возвращает `tuple[str, str]` (static_prompt, dynamic_context).

**Логика:**
1. В `_prepare_data()` НЕ включать `customer_answers` и `form_unified` в data dict
2. Рендерить шаблон только со статическими данными
3. Поскольку `{{ customer_answers }}` и `{{ form_unified }}` в шаблоне окажутся без значений — Jinja2 по умолчанию рендерит undefined переменные как пустую строку (с `undefined=Undefined()`)
4. Нужно настроить `jinja2.Environment(undefined=jinja2.ChainableUndefined)` чтобы неопределённые переменные рендерились как пустая строка без ошибок
5. Собрать dynamic_context как форматированный текст отдельно

**Новый метод:**
```python
def format_prompt_parts(
    self,
    prompt_template: str,
    company_spec: dict[str, Any],
    customer_answers: CustomerAnswers,
    form_unified: FormPayload | None = None,
    extra_substitutions: dict[str, Any] | None = None,
    qualification_workflow: str | None = None,
    qualification_examples: str | None = None,
) -> tuple[str, str]:
    """Returns (static_prompt, dynamic_context) for cache-aware message building."""
```

**Dynamic context формат:**
```
# Текущий контекст

## Текущая стадия
{current_stage}

## Ответы клиента
{customer_answers_json}

## Форма
{form_unified_json}
```

**Сохранить** существующий `format_prompt()` без изменений — он нужен для обратной совместимости и task execution.

### Шаг 2: _build_messages — content blocks с cache_control

**Файл:** `apps/sales-agent/src/sales_agent/agents/pipeline.py`

Изменить `_build_messages()`:

```python
def _build_messages(
    static_prompt: str,
    dynamic_context: str,
    history: list[dict[str, Any]],
    user_text: str,
) -> list[dict[str, Any]]:
    system_content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": static_prompt,
            "cache_control": {"type": "ephemeral"},
        },
    ]
    if dynamic_context:
        system_content.append({"type": "text", "text": dynamic_context})

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]

    for item in history:
        role = item.get("role", "")
        content = item.get("content", "")
        if role in ("user", "assistant", "tool") and content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_text})
    return messages
```

### Шаг 3: Pipeline — использовать format_prompt_parts

**Файл:** `apps/sales-agent/src/sales_agent/agents/pipeline.py`

В `process_user_message_agents()` заменить вызов:

```python
# Было:
system_prompt = formatter.format_prompt(...)
if reminder_instructions:
    system_prompt = f"{system_prompt}\n\n---\n\n{reminder_instructions}"
messages = _build_messages(system_prompt, history, text)

# Стало:
static_prompt, dynamic_context = formatter.format_prompt_parts(...)
if reminder_instructions:
    dynamic_context = f"{dynamic_context}\n\n---\n\n{reminder_instructions}"
messages = _build_messages(static_prompt, dynamic_context, history, text)
```

### Шаг 4: Проверить совместимость с LLM client

**Файл:** `apps/sales-agent/src/sales_agent/core/llm/client.py`

Проверить что `chat()` корректно передаёт content blocks:
- `AsyncOpenAI.chat.completions.create()` принимает messages с content как `list[dict]` (content blocks) — это стандарт OpenAI API
- OpenRouter проксирует это в Anthropic формат автоматически
- Для GPT-5 (Responses API): `convert_messages_to_responses_input()` должен обработать content blocks — проверить и при необходимости обновить

**Файл:** `apps/sales-agent/src/sales_agent/core/llm/utils.py`

Проверить `convert_messages_to_responses_input()` — если system message приходит с content blocks (list), нужно собрать текст из всех блоков.

### Шаг 5: Логирование cache stats

**Файл:** `apps/sales-agent/src/sales_agent/core/llm/client.py`

В `chat()` после получения response, логировать cache-related usage:

```python
usage = response.get("usage", {})
cache_stats = {
    k: v for k, v in usage.items()
    if "cache" in k.lower()
}
if cache_stats:
    log.info("llm.cache_stats", **cache_stats)
```

OpenRouter/Anthropic возвращает `cache_creation_input_tokens` и `cache_read_input_tokens` в usage.

### Шаг 6: Тесты

**Файл:** `apps/sales-agent/tests/test_prompt_caching.py`

1. `test_format_prompt_parts_static_stability` — два вызова с разными `customer_answers` дают одинаковый `static_prompt`
2. `test_format_prompt_parts_dynamic_contains_answers` — `dynamic_context` содержит actual customer_answers
3. `test_build_messages_cache_control` — system message имеет content blocks с cache_control
4. `test_format_prompt_parts_matches_format_prompt` — static + dynamic содержат ту же информацию, что и полный format_prompt

---

## Ограничения и риски

| Риск | Митигация |
|------|-----------|
| Минимум токенов для кеша (1024-4096 в зависимости от модели) | Наши system prompts 15-25k токенов — далеко за порогом |
| TTL кеша 5 минут | Для активного диалога достаточно. Между сессиями кеш протухнет — это нормально |
| Макс 4 cache breakpoints | Используем 1 breakpoint — на границе static/dynamic |
| DB-шаблоны могут не следовать паттерну (dynamic в конце) | Jinja2 `ChainableUndefined` обработает undefined переменные как пустую строку. Static prompt будет стабильным даже если dynamic placeholders раскиданы по шаблону |
| GPT-5/Responses API совместимость | Проверить convert_messages_to_responses_input для content blocks |
| Langfuse wrapper может не передавать cache_control | Протестировать — Langfuse AsyncOpenAI это drop-in replacement |

---

## Что НЕ меняется

- Шаблоны промптов в DB — не требуют изменений
- Tool registry и build_tools — без изменений
- Tool loop — без изменений
- Backend — без изменений
- Транспорты — без изменений
- `format_prompt()` — сохраняется для обратной совместимости

---

## Ожидаемый эффект

| Метрика | До | После |
|---------|-----|-------|
| Input tokens per request | ~20k | ~500 (dynamic) + ~20k cached |
| Стоимость input | 100% | ~10% (cached × 0.1 + dynamic × 1.0) |
| Latency (TTFT) | baseline | ~85% от baseline (cached prefix не пересчитывается) |
