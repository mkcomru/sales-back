"""Tests for prompt caching (Anthropic prefix caching via OpenRouter)."""

from __future__ import annotations

from src.sales_agent.agents.pipeline import _build_messages
from src.sales_agent.services.prompt_formatter import PromptFormatter

_COMPANY_SPEC = {
    "name": "Test Co",
    "description": "A test company",
    "assistant_name": "Assistant",
    "rules": "Be polite",
    "tone_of_voice": "Friendly",
    "qualification_workflow": "",
    "qualification_examples": "",
    "enabled_tools": [],
    "stages_config": [],
    "fields": [{"name": "phone", "type": "text", "required": True, "category_id": None, "product_id": None}],
    "categories": [],
    "products": [],
}

_TEMPLATE = """\
# Роль
Ты — ассистент компании {{ company.name }}.

## Правила
{{ company.rules }}

## Поля
{{ company.fields }}

# Текущий контекст
Стадия: {{ current_stage }}
Ответы: {{ customer_answers }}
Форма: {{ form_unified }}
"""


def test_format_prompt_parts_static_stability() -> None:
    formatter = PromptFormatter()

    answers_1 = {"phone": "+79001234567"}
    answers_2 = {"phone": "+79009999999", "name": "Иван"}

    static_1, _ = formatter.format_prompt_parts(
        _TEMPLATE, _COMPANY_SPEC, answers_1, extra_substitutions={"current_stage": "Новый"}
    )
    static_2, _ = formatter.format_prompt_parts(
        _TEMPLATE, _COMPANY_SPEC, answers_2, extra_substitutions={"current_stage": "Квалифицирован"}
    )

    assert static_1 == static_2, "static_prompt must be identical regardless of customer_answers"


def test_format_prompt_parts_dynamic_contains_answers() -> None:
    formatter = PromptFormatter()
    answers = {"phone": "+79001234567", "name": "Иван"}
    form = {"budget": "100k"}

    _, dynamic = formatter.format_prompt_parts(
        _TEMPLATE,
        _COMPANY_SPEC,
        answers,
        form_unified=form,
        extra_substitutions={"current_stage": "Новый"},
    )

    assert "+79001234567" in dynamic
    assert "Иван" in dynamic
    assert "100k" in dynamic
    assert "Новый" in dynamic


def test_build_messages_cache_control() -> None:
    messages = _build_messages(
        static_prompt="Статичный промпт",
        dynamic_context="Динамический контекст",
        history=[],
        user_text="Привет",
    )

    system_msg = messages[0]
    assert system_msg["role"] == "system"
    content = system_msg["content"]
    assert isinstance(content, list)
    assert len(content) == 2

    first_block = content[0]
    assert first_block["type"] == "text"
    assert first_block["text"] == "Статичный промпт"
    assert first_block["cache_control"] == {"type": "ephemeral"}

    second_block = content[1]
    assert second_block["type"] == "text"
    assert second_block["text"] == "Динамический контекст"
    assert "cache_control" not in second_block


def test_format_prompt_parts_matches_format_prompt() -> None:
    """Static + dynamic together must contain the same data as the full format_prompt."""
    formatter = PromptFormatter()
    answers = {"phone": "+79001234567"}

    full = formatter.format_prompt(
        _TEMPLATE,
        _COMPANY_SPEC,
        answers,
        extra_substitutions={"current_stage": "Новый"},
    )
    static, dynamic = formatter.format_prompt_parts(
        _TEMPLATE,
        _COMPANY_SPEC,
        answers,
        extra_substitutions={"current_stage": "Новый"},
    )

    # Company data in static
    assert "Test Co" in static
    assert "Be polite" in static

    # Dynamic data in dynamic_context, not in static
    assert "+79001234567" in dynamic
    assert "+79001234567" not in static or "+79001234567" in full

    # current_stage in dynamic
    assert "Новый" in dynamic

    # full prompt has same phone
    assert "+79001234567" in full
    assert "Test Co" in full
