"""Single-agent pipeline — stateless LLM executor.

Receives all context via AgentContext in the envelope.
Renders prompt locally, runs tool loop, returns response.
"""

from __future__ import annotations

from typing import Any

import structlog
from pydantic import BaseModel

from common import SalesAgentSettings as Settings
from common.models.io import SimpleMessage

from src.sales_agent.connectors import (
    ConnectorCapability,
    ConnectorContext,
    ConnectorType,
)
from src.sales_agent.core.llm.client import LLMClient
from src.sales_agent.core.llm.loop import run_tool_loop
from src.sales_agent.core.telemetry import Tracer
from src.sales_agent.core.tools.registry import build_tools
from src.sales_agent.services.backend_client import BackendClient
from src.sales_agent.services.company_context import (
    get_handoff_result,
    reset_request_context,
    set_company_spec,
    set_customer_answers,
    set_extra_fields,
    set_order_fields,
)
from src.sales_agent.services.crm_adapter import CRMAdapter
from src.sales_agent.services.humanizer import humanize_message
from src.sales_agent.services.prompt_formatter import PromptFormatter
from src.sales_agent.storage.customer_store import reset_customer_profile

log = structlog.get_logger()


class AgentsPipelineResult(BaseModel):
    text: str
    stage_id: str | None = None
    handoff_summary: dict[str, Any] | None = None


def _get_conversation_id(message: SimpleMessage) -> str | None:
    metadata = message.metadata if isinstance(message.metadata, dict) else {}
    conv_id = metadata.get("conversation_id")
    if conv_id:
        return str(conv_id)
    return None


def _build_messages(
    static_prompt: str,
    dynamic_context: str,
    history: list[dict[str, Any]],
    user_text: str,
) -> list[dict[str, Any]]:
    """Build messages list for LLM with cache_control on the static system prompt prefix."""
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
        text = content or item.get("transcription", "")
        if role in ("user", "assistant", "tool", "manager") and text:
            if role == "manager":
                role = "assistant"
            messages.append({"role": role, "content": text})

    messages.append({"role": "user", "content": user_text})
    return messages


async def process_user_message_agents(
    message: SimpleMessage,
    settings: Settings,
    large_llm_client: LLMClient,
    tracer: Tracer,
    backend_client: BackendClient,
    connector_context: ConnectorContext | None = None,
    reminder_instructions: str | None = None,
    trace_name: str = "chat.process",
) -> AgentsPipelineResult:
    """Process a user message via single-agent pipeline.

    All context comes from AgentContext in message metadata (assembled by Backend).
    """
    from_user = message.from_user
    if from_user is None:
        return AgentsPipelineResult(text="Пожалуйста, отправьте текстовое сообщение.")

    user_id = from_user.id
    text = (message.text or "").strip()

    if not text and reminder_instructions:
        text = "[Выполни напоминание согласно инструкциям в системном промпте]"
    elif not text:
        return AgentsPipelineResult(text="Пожалуйста, отправьте текстовое сообщение.")

    metadata = message.metadata if isinstance(message.metadata, dict) else {}

    company_id_raw = metadata.get("company_id")
    if company_id_raw is None:
        raise ValueError("company_id is required in message metadata")
    company_id = int(company_id_raw)

    # Extract AgentContext from metadata (serialized by internal_utils)
    agent_ctx = metadata.get("agent_context")
    if not agent_ctx or not isinstance(agent_ctx, dict):
        raise ValueError("agent_context is required in message metadata")

    prompt_template: str = agent_ctx["prompt_template"]
    company_spec: dict[str, Any] = agent_ctx["company"]
    customer_answers: dict[str, Any] = dict(agent_ctx.get("customer_answers") or {})
    order_fields: dict[str, Any] = dict(agent_ctx.get("order_fields") or {})
    extra_fields: dict[str, Any] = dict(agent_ctx.get("extra_fields") or {})
    history: list[dict[str, Any]] = agent_ctx.get("history") or []
    enabled_tools: list[str] = agent_ctx.get("enabled_tools") or []
    langfuse_session_id: str | None = agent_ctx.get("langfuse_session_id")
    form_data: dict[str, Any] | None = agent_ctx.get("form_data")
    customer_name: str | None = agent_ctx.get("customer_name")

    qualification_workflow = metadata.get("qualification_workflow")
    qualification_examples = metadata.get("qualification_examples")

    # Set request-scoped context for tools
    reset_request_context()
    set_company_spec(company_spec)
    set_customer_answers(customer_answers)
    set_order_fields(order_fields)
    set_extra_fields(extra_fields)

    log.info("pipeline.config_loaded", company_id=company_id)

    is_simulator_mode = metadata.get("_simulator_mode") is True

    crm_adapter = CRMAdapter(settings=settings)
    supports_stage_sync = (
        connector_context is not None and ConnectorCapability.SYNC_STAGE in connector_context.capabilities
    )
    is_crm_connector = connector_context is not None and connector_context.connector_type == ConnectorType.CRM

    conversation_id = _get_conversation_id(message)
    effective_user_id = conversation_id or str(user_id)
    user_id = effective_user_id

    # /clear command — direct backend write
    if text.lower().startswith("/clear") and not is_simulator_mode:
        try:
            await reset_customer_profile(effective_user_id, company_id=company_id)
        except Exception:
            pass
        reply = await humanize_message("История очищена.", history=history, settings=settings)
        return AgentsPipelineResult(text=reply, stage_id=crm_adapter.initial_stage_id())

    # Trace setup
    connector_id_value = connector_context.connector_id if connector_context is not None else None
    connector_type_value = connector_context.connector_type.value if connector_context else None
    channel_type_value = connector_context.channel_type if connector_context else None
    session_id_for_trace = langfuse_session_id or conversation_id
    trace_tags = tracer.connector_tags(
        extra=["sales-agent"],
        connector_id=connector_id_value,
        connector_type=connector_type_value,
        channel_type=channel_type_value,
    )
    trace_metadata = {
        "connector_id": connector_id_value,
        "connector_type": connector_type_value,
        "channel_type": channel_type_value,
        "conversation_id": conversation_id,
    }

    with tracer.start_trace(
        name=trace_name,
        input=text[:200],
        tags=trace_tags,
        metadata={k: v for k, v in trace_metadata.items() if v is not None},
        user_id=str(effective_user_id),
        session_id=session_id_for_trace,
    ):
        # Extract extra/form from metadata
        extra_meta = metadata.get("extra") if isinstance(metadata, dict) else None
        extra_meta_dict = extra_meta if isinstance(extra_meta, dict) else {}
        form_payload_raw = extra_meta_dict.get("form") or form_data
        form_payload = form_payload_raw if isinstance(form_payload_raw, dict) else None
        is_form_message = is_crm_connector and bool(form_payload)

        # Initialize form confirmation lock for CRM form batches
        if is_form_message and not customer_answers.get("_form_pending_confirmation"):
            customer_answers["_form_pending_confirmation"] = True

        # Extract order context from metadata
        order_id_for_tools = None
        order_id_raw = metadata.get("order_id")
        if order_id_raw is not None:
            try:
                order_id_for_tools = int(order_id_raw)
            except (ValueError, TypeError):
                pass

        # Resolve current stage name from metadata
        current_stage_name = "Без стадии"
        order_stage = metadata.get("order_stage")
        if order_stage and isinstance(order_stage, dict):
            current_stage_name = order_stage.get("name", "Без стадии")

        # Render prompt
        formatter = PromptFormatter()
        extra_substitutions: dict[str, Any] = {"current_stage": current_stage_name}
        static_prompt, dynamic_context = formatter.format_prompt_parts(
            prompt_template,
            company_spec,
            customer_answers,
            form_payload,
            extra_substitutions=extra_substitutions,
            qualification_workflow=qualification_workflow,
            qualification_examples=qualification_examples,
            order_fields=order_fields,
            extra_fields=extra_fields,
            enabled_tools_override=enabled_tools,
            customer_name=customer_name,
        )

        if reminder_instructions:
            dynamic_context = f"{dynamic_context}\n\n---\n\n{reminder_instructions}"

        # Build messages from envelope history
        messages = _build_messages(static_prompt, dynamic_context, history, text)

        # Build tools from envelope enabled_tools
        tools = build_tools(
            enabled_tools=enabled_tools,
            settings=settings,
            user_id=user_id,
            company_id=company_id,
            message=message,
            order_id=order_id_for_tools,
        )

        with tracer.start_span(
            name="agent.invoke",
            input={"user_text": text[:500], "answers_count": len(customer_answers)},
            metadata={"tools_count": len(tools)},
        ):
            final_messages, final_text = await run_tool_loop(
                llm=large_llm_client,
                messages=messages,
                tools=tools,
                temperature=0.6,
                max_completion_tokens=2048,
                reasoning_effort="medium",
                verbosity="low",
                tracer=tracer,
            )

            reply = final_text.strip()

        if not reply:
            reply = "Принял. Продолжим."

        # Release form confirmation lock on real user messages
        if is_crm_connector and not is_form_message and customer_answers.get("_form_pending_confirmation"):
            try:
                customer_answers.pop("_form_pending_confirmation", None)
            except Exception:
                pass

        # Humanize using envelope history
        reply = await humanize_message(reply, history=history, settings=settings)

        try:
            tracer.update_current_trace(output=reply)
        except Exception:
            pass

        final_stage_id = None
        if supports_stage_sync:
            stage_name = customer_answers.get("stage")
            final_stage_id = crm_adapter.resolve_stage_id(stage_name) if stage_name else None

        handoff_data = get_handoff_result()

        return AgentsPipelineResult(
            text=reply,
            stage_id=final_stage_id,
            handoff_summary=handoff_data,
        )
