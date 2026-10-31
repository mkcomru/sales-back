"""Simple service to fill prompts with backend data."""

import json
import re
from datetime import UTC, datetime
from typing import Any

import structlog
from jinja2 import ChainableUndefined, Environment, TemplateError

from src.sales_agent.core.tools.registry import TOOL_DESCRIPTIONS, TOOL_SCHEMAS
from src.sales_agent.core.tools.utils import merge_tools

log = structlog.get_logger(__name__)

CustomerAnswers = dict[str, Any]
FormPayload = dict[str, Any]


class PromptFormatter:
    """Takes prompt template and backend data, returns filled prompt."""

    def __init__(self):
        self.jinja_env = Environment(enable_async=False, autoescape=False)
        self.jinja_static_env = Environment(enable_async=False, autoescape=False, undefined=ChainableUndefined)

    def format_prompt(
        self,
        prompt_template: str,
        company_spec: dict[str, Any],
        customer_answers: CustomerAnswers,
        form_unified: FormPayload | None = None,
        extra_substitutions: dict[str, Any] | None = None,
        qualification_workflow: str | None = None,
        qualification_examples: str | None = None,
        order_fields: dict[str, Any] | None = None,
        extra_fields: dict[str, Any] | None = None,
        customer_name: str | None = None,
    ) -> str:
        """Fill prompt with data from backend.

        Args:
            prompt_template: Raw prompt from DB
            company_spec: Company data from backend
            customer_answers: Current customer answers
            form_unified: Optional form data
            extra_substitutions: Optional additional substitutions (e.g., thread_id)
            qualification_workflow: Optional workflow override from prompt_addon
            qualification_examples: Optional examples override from prompt_addon

        Returns:
            Prompt with all {{ placeholders }} replaced using Jinja2

        Note:
            Logs warning if unreplaced placeholders found
        """
        data = self._prepare_data(
            company_spec,
            customer_answers,
            form_unified,
            qualification_workflow,
            qualification_examples,
            order_fields=order_fields,
            extra_fields=extra_fields,
            customer_name=customer_name,
        )
        data["_omit_context_block"] = False
        if extra_substitutions:
            for key, value in extra_substitutions.items():
                data[key] = str(value) if value is not None else ""

        try:
            nested_data = self._flatten_to_nested(data)
            template = self.jinja_env.from_string(prompt_template)
            result = template.render(nested_data)
        except TemplateError as e:
            log.error("prompt.jinja_error", error=str(e))
            raise

        unreplaced = self._find_unreplaced_placeholders(result)
        if unreplaced:
            log.warning(
                "prompt.unreplaced_placeholders",
                placeholders=list(unreplaced),
                available_keys=list(data.keys()),
            )

        return result

    def format_prompt_parts(
        self,
        prompt_template: str,
        company_spec: dict[str, Any],
        customer_answers: CustomerAnswers,
        form_unified: FormPayload | None = None,
        extra_substitutions: dict[str, Any] | None = None,
        qualification_workflow: str | None = None,
        qualification_examples: str | None = None,
        order_fields: dict[str, Any] | None = None,
        extra_fields: dict[str, Any] | None = None,
        enabled_tools_override: list[str] | None = None,
        customer_name: str | None = None,
    ) -> tuple[str, str]:
        """Returns (static_prompt, dynamic_context) for cache-aware message building.

        static_prompt — rendered template without customer_answers/form_unified/current_stage.
        dynamic_context — formatted text with current_stage, customer_answers, form_unified.
        """
        data = self._prepare_data(
            company_spec,
            customer_answers,
            form_unified,
            qualification_workflow,
            qualification_examples,
            order_fields=order_fields,
            extra_fields=extra_fields,
            enabled_tools_override=enabled_tools_override,
            customer_name=customer_name,
        )
        data.pop("customer_answers", None)
        data.pop("form_unified", None)
        data.pop("order_fields", None)
        data.pop("extra_fields", None)
        data["_omit_context_block"] = True

        try:
            nested_data = self._flatten_to_nested(data)
            template = self.jinja_static_env.from_string(prompt_template)
            static_prompt = template.render(nested_data)
        except TemplateError as e:
            log.error("prompt.jinja_error", error=str(e))
            raise

        unreplaced = self._find_unreplaced_placeholders(static_prompt)
        if unreplaced:
            log.warning(
                "prompt.unreplaced_placeholders",
                placeholders=list(unreplaced),
                available_keys=list(data.keys()),
            )

        current_stage = (extra_substitutions or {}).get("current_stage", "")
        current_date = data.get("current_date", "")
        current_datetime = data.get("current_datetime", "")

        dynamic_parts: list[str] = [
            "# Текущий контекст",
            f"Сегодня: {current_date} ({current_datetime})",
        ]
        if current_stage:
            dynamic_parts.append(f"## Текущая стадия\n{current_stage}")
        dynamic_parts.append(f"## Ответы клиента\n{json.dumps(customer_answers, ensure_ascii=False)}")
        if order_fields:
            dynamic_parts.append(f"## Данные заказа\n{json.dumps(order_fields, ensure_ascii=False)}")
        if extra_fields:
            dynamic_parts.append(f"## Дополнительные данные\n{json.dumps(extra_fields, ensure_ascii=False)}")
        if form_unified:
            dynamic_parts.append(f"## Форма\n{json.dumps(form_unified, ensure_ascii=False)}")

        dynamic_parts.append(
            "Опираться на этот контекст обязательно: не задавай один и тот же вопрос дважды без причины и не меняй "
            "тему, если человек продолжает предыдущую линию разговора."
        )
        dynamic_context = "\n\n".join(dynamic_parts)
        return static_prompt, dynamic_context

    def _find_unreplaced_placeholders(self, text: str) -> set[str]:
        """Find Jinja2 placeholders that were not replaced."""
        pattern = r"\{\{([^}]+)\}\}"
        matches = re.findall(pattern, text)
        return {m.strip() for m in matches}

    def _prepare_data(
        self,
        company_spec: dict[str, Any],
        customer_answers: CustomerAnswers,
        form_unified: FormPayload | None,
        qualification_workflow: str | None = None,
        qualification_examples: str | None = None,
        order_fields: dict[str, Any] | None = None,
        extra_fields: dict[str, Any] | None = None,
        enabled_tools_override: list[str] | None = None,
        customer_name: str | None = None,
    ) -> dict[str, str]:
        """Prepare flat dict for substitution."""
        data: dict[str, str] = {}

        now = datetime.now(UTC)
        data["current_date"] = now.strftime("%Y-%m-%d")
        data["current_datetime"] = now.strftime("%Y-%m-%d %H:%M:%S %Z")

        company_data = dict(company_spec)
        answers_data = dict(customer_answers)
        form_data = dict(form_unified or {})

        # Company fields
        data["company.name"] = company_data.get("name", "")
        data["company.description"] = company_data.get("description", "")
        data["company.assistant_name"] = company_data.get("assistant_name", "")
        data["company.rules"] = company_data.get("rules", "")
        data["company.tone_of_voice"] = company_data.get("tone_of_voice", "")
        data["company.qualification_workflow"] = (
            qualification_workflow
            if qualification_workflow is not None
            else company_data.get("qualification_workflow", "")
        )
        data["company.qualification_examples"] = (
            qualification_examples
            if qualification_examples is not None
            else company_data.get("qualification_examples", "")
        )

        # Company tools — use override when provided (matches AgentContext.enabled_tools)
        tools = enabled_tools_override if enabled_tools_override is not None else company_data.get("enabled_tools", [])
        data["company.tools"] = self._format_tools(tools)

        # Company stages (for router)
        stages = company_data.get("stages_config", [])
        data["company.stages"] = self._format_stages(stages)

        all_fields = company_data.get("fields", [])

        company_level_fields = [f for f in all_fields if not f.get("category_id") and not f.get("product_id")]
        data["company.fields"] = self._format_fields(company_level_fields)

        # AICODE-NOTE: Category expert получает все поля выбранной категории
        current_category_id = answers_data.get("category_id")
        if current_category_id:
            category_fields = [f for f in all_fields if f.get("category_id") == current_category_id]
            data["company.current_category.fields"] = self._format_fields(category_fields)

            categories = company_data.get("categories", [])
            current_category = next((c for c in categories if c.get("id") == current_category_id), None)
            if current_category:
                data["company.current_category.description"] = current_category.get("description", "")
                data["company.current_category.workflow"] = current_category.get("workflow", "")
                data["company.current_category.examples"] = current_category.get("examples", "")
                company_tools = (
                    enabled_tools_override
                    if enabled_tools_override is not None
                    else company_data.get("enabled_tools", [])
                )
                category_tools = current_category.get("enabled_tools", [])
                combined_tools = (
                    company_tools if enabled_tools_override is not None else merge_tools(company_tools, category_tools)
                )
                data["company.current_category.tools"] = self._format_tools(combined_tools)
            else:
                data["company.current_category.description"] = ""
                data["company.current_category.workflow"] = ""
                data["company.current_category.examples"] = ""
                data["company.current_category.tools"] = ""
        else:
            data["company.current_category.fields"] = ""
            data["company.current_category.description"] = ""
            data["company.current_category.workflow"] = ""
            data["company.current_category.examples"] = ""
            data["company.current_category.tools"] = ""

        # Product-level fields (after product selection by customer)
        selected_product_id = answers_data.get("selected_product_id")
        if selected_product_id:
            # Convert to int if string
            if isinstance(selected_product_id, str):
                try:
                    selected_product_id = int(selected_product_id)
                except ValueError:
                    selected_product_id = None

            if selected_product_id:
                product_fields = [f for f in all_fields if f.get("product_id") == selected_product_id]
                data["company.selected_product.fields"] = self._format_fields(product_fields)

                # Get product info
                products = company_data.get("products", [])
                selected_product = next((p for p in products if p.get("id") == selected_product_id), None)
                if selected_product:
                    data["company.selected_product.name"] = selected_product.get("name", "")
                    data["company.selected_product.description"] = selected_product.get("description", "")
                else:
                    data["company.selected_product.name"] = ""
                    data["company.selected_product.description"] = ""
                    data["company.selected_product.fields"] = ""
            else:
                data["company.selected_product.name"] = ""
                data["company.selected_product.description"] = ""
                data["company.selected_product.fields"] = ""
        else:
            data["company.selected_product.name"] = ""
            data["company.selected_product.description"] = ""
            data["company.selected_product.fields"] = ""

        # Customer data
        data["customer_name"] = customer_name or ""
        data["customer_answers"] = json.dumps(answers_data, ensure_ascii=False) if answers_data else "{}"
        data["order_fields"] = json.dumps(order_fields or {}, ensure_ascii=False)
        data["extra_fields"] = json.dumps(extra_fields or {}, ensure_ascii=False)
        data["form_unified"] = json.dumps(form_data, ensure_ascii=False) if form_data else "{}"

        return data

    def _flatten_to_nested(self, flat_data: dict[str, str]) -> dict[str, Any]:
        """Convert flat keys like 'company.name' to nested structure."""
        nested: dict[str, Any] = {}
        for key, value in flat_data.items():
            if "." in key:
                parts = key.split(".")
                current = nested
                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                current[parts[-1]] = value
            else:
                nested[key] = value
        return nested

    def _format_fields(self, fields: list[dict[str, Any]]) -> str:
        """Format fields as text. Required fields are marked with *."""
        lines = []
        for field in fields:
            name = field.get("name", "")
            question = field.get("question", "")
            field_type = field.get("type", "")
            options = field.get("options", [])
            marker = " *" if field.get("required") else ""

            base = f"- {name} - {question} - {field_type}"
            if options:
                opts = ", ".join([o.get("value", "") for o in options])
                base += f" - ({opts})"
            lines.append(base + marker)

        return "\n".join(lines) if lines else ""

    def _format_products(self, products: list[dict[str, Any]]) -> str:
        """Format products as text."""
        lines = []
        for product in products:
            name = product.get("name", "")
            description = product.get("description", "")
            lines.append(f"- {name}: {description}")

        return "\n".join(lines) if lines else ""

    def _format_stages(self, stages: list[dict[str, Any]]) -> str:
        """Format stages as text for prompt."""
        lines: list[str] = []
        for stage in stages:
            name = stage.get("name", "")
            crm_id = stage.get("crm_id", "")
            if name and crm_id:
                lines.append(f"- {crm_id}: {name}")
        return "\n".join(lines) if lines else ""

    def _format_tools(self, tools: list[str]) -> str:
        """Format tools as text for prompt.

        Uses TOOL_SCHEMAS for parameters, TOOL_DESCRIPTIONS for descriptions.
        """
        lines: list[str] = []
        for name in tools:
            name = (name or "").strip()
            if not name:
                continue

            description = TOOL_DESCRIPTIONS.get(name, "").strip()
            schema = TOOL_SCHEMAS.get(name, {})

            arg_names: list[str] = []
            props = schema.get("properties")
            if isinstance(props, dict) and props:
                arg_names = list(props.keys())

            args_repr = ", ".join(arg_names)
            args_block = f"({args_repr})" if args_repr else "()"

            line = f"- {name}{args_block}"
            if description:
                line += f" - {description}"

            lines.append(line)

        return "\n".join(lines) if lines else ""
