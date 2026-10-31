import asyncio
import zlib
from collections.abc import Awaitable, Callable

from fastapi import FastAPI

from common import SalesAgentSettings, log
from common.config import ConnectorSettings
from common.correlation import make_correlation_id
from common.models import OutboundDeliveryRequest
from common.models.inbound import ConnectorContext as CommonConnectorContext
from common.models.io import SimpleChat, SimpleMessage, SimpleUser

from src.sales_agent.agents.pipeline import process_user_message_agents
from src.sales_agent.connectors import (
    CONNECTOR_MIN_CAPABILITIES,
    ConnectorContext,
    ConnectorType,
)
from src.sales_agent.core.llm.client import LLMClient
from src.sales_agent.core.telemetry import Tracer
from src.sales_agent.services.backend_client import BackendClient
from src.sales_agent.services.crm_adapter import CRMAdapter
from src.sales_agent.services.debounce import IncomingMessage
from src.sales_agent.services.message_splitter import remove_trailing_dots, split_and_calculate_delays
from src.sales_agent.services.transcription import transcribe_if_audio
from src.sales_agent.storage.customer_store import update_customer_fields

# AICODE-NOTE: Pipeline execution context that must be stripped before outbound delivery.
# These are only needed during LLM processing and must NOT be persisted into
# chat_messages.metadata — agent_context alone caused 22MB+ per row.
_PIPELINE_CONTEXT_KEYS = frozenset(
    {
        "agent_context",
        "extra",
        "qualification_workflow",
        "qualification_examples",
    }
)


def _stable_int_id(raw: str | None) -> int:
    if raw is None:
        return 0
    value = raw.strip()
    if not value:
        return 0
    if value.isdigit():
        try:
            return int(value)
        except ValueError:
            pass
    return zlib.crc32(value.encode("utf-8")) & 0x7FFFFFFF


def _make_correlation_id(conversation_id: str, _batch: list[IncomingMessage]) -> str:
    return make_correlation_id("agent", conversation_id)


def _validate_company_id(company_id_raw: object, context: str, user_id: str) -> int | None:
    if company_id_raw is None:
        log.warning(f"{context}.missing_company_id", user_id=user_id)
        return None
    try:
        return int(company_id_raw)
    except (TypeError, ValueError):
        log.warning(f"{context}.invalid_company_id", user_id=user_id, company_id=company_id_raw)
        return None


def _resolve_connector_snapshot(
    settings: SalesAgentSettings,
    metadata: dict[str, object],
) -> tuple[ConnectorSettings | None, ConnectorContext | None]:
    connector_id_raw = metadata.get("connector_id")
    connector_id = str(connector_id_raw).strip() if connector_id_raw is not None else None

    channel_type_raw = metadata.get("channel_type")
    channel_type = str(channel_type_raw).strip() if isinstance(channel_type_raw, str) else None

    connector_cfg = (
        settings.get_connector(connector_id)
        or settings.get_connector_by_channel(channel_type)
        or settings.get_default_connector()
    )

    if connector_cfg is None:
        return None, None

    resolved_id = connector_cfg.connector_id or connector_id or "default"
    metadata.setdefault("connector_id", resolved_id)

    if not channel_type and connector_cfg.channel_types:
        channel_type = connector_cfg.channel_types[0]
    if channel_type:
        metadata.setdefault("channel_type", channel_type)

    metadata.setdefault("connector_type", connector_cfg.type)

    try:
        connector_type = ConnectorType(connector_cfg.type)
    except ValueError:
        connector_type = ConnectorType.MESSAGING

    context = ConnectorContext(
        connector_id=resolved_id,
        connector_type=connector_type,
        channel_type=channel_type,
        capabilities=CONNECTOR_MIN_CAPABILITIES[connector_type],
        config_snapshot=connector_cfg.sanitized(),
    )

    return connector_cfg, context


def _strip_asterisks(message: str) -> str:
    return message.replace("*", "")


def _normalize_text(message: str) -> str:
    s = message.replace("ё", "е").replace("Ё", "Е")
    s = s.replace("\u2014", "-")  # em dash — → hyphen -
    return s


def _apply_message_clearance(message: str) -> str:
    sanitized = _normalize_text(message)
    sanitized = _strip_asterisks(sanitized)
    sanitized = remove_trailing_dots(sanitized)
    return sanitized


def create_batch_processor(
    app: FastAPI,
    settings: SalesAgentSettings,
    backend_client: BackendClient,
    large_llm_client: LLMClient,
    tracer: Tracer,
    crm_adapter: CRMAdapter,
) -> Callable[[str, list[IncomingMessage]], Awaitable[None]]:
    # NOTE: handle_sync_batch and handle_manager_outgoing removed.
    # Backend is now the intelligent router and handles sync/manager messages directly.

    async def handle_agent_batch(
        batch: list[IncomingMessage],
        merged_meta: dict[str, object],
        combined_text: str,
        conversation_id: str,
        connector_id: str | None,
        storage_key: str,
    ) -> None:
        # Use connector_id from metadata directly (passed by Backend)
        # Backend is the authoritative source for connector_id
        raw_connector_id = merged_meta.get("connector_id")
        resolved_connector_id: str | None = None
        if raw_connector_id is not None:
            candidate = str(raw_connector_id).strip()
            if candidate:
                resolved_connector_id = candidate
        if not resolved_connector_id and connector_id:
            resolved_connector_id = connector_id

        # Get connector_type and channel_type from metadata
        raw_connector_type = merged_meta.get("connector_type")
        resolved_connector_type: str | None = None
        if isinstance(raw_connector_type, str):
            resolved_connector_type = raw_connector_type.strip() or None
        raw_channel_type = merged_meta.get("channel_type")
        resolved_channel_type: str | None = None
        if isinstance(raw_channel_type, str):
            resolved_channel_type = raw_channel_type.strip() or None

        # Try to get connector config for capabilities (optional, for backward compatibility)
        connector_cfg, connector_context = _resolve_connector_snapshot(settings, merged_meta)

        lead_id = merged_meta.get("lead_id")
        phone = merged_meta.get("phone")

        metadata_payload: dict[str, object | None] = {
            "company_id": merged_meta.get("company_id"),
            "inbound_ts": batch[-1].ts if batch else None,
            "lead_id": lead_id,
            "phone": phone,
            "batch_size": len(batch),
            "extra": merged_meta,
            "connector_id": resolved_connector_id,
            "connector_type": resolved_connector_type,
            "channel_type": resolved_channel_type,
            "agent_context": merged_meta.get("agent_context"),
            "order_stage": merged_meta.get("order_stage"),
            "qualification_workflow": merged_meta.get("qualification_workflow"),
            "qualification_examples": merged_meta.get("qualification_examples"),
        }

        simple_msg = SimpleMessage(
            text=combined_text,
            from_user=SimpleUser(id=_stable_int_id(conversation_id)),
            chat=SimpleChat(id=_stable_int_id(conversation_id)),
            message_id=0,
            metadata=metadata_payload,
        )

        is_first_message = False
        callback_url = ""
        if connector_cfg is not None:
            callback_url = (connector_cfg.callbacks.delivery_url or "").strip()

        if callback_url and batch and connector_context:
            # Check if first message using envelope history
            agent_ctx = merged_meta.get("agent_context")
            if isinstance(agent_ctx, dict):
                history = agent_ctx.get("history") or []
                user_messages = [msg for msg in history if msg.get("role") == "user"]
                is_first_message = len(user_messages) == 0

        conversation_id = merged_meta.get("conversation_id") or str(batch[-1].user_id)

        company_id = _validate_company_id(merged_meta.get("company_id"), "agent", conversation_id)
        if company_id is None:
            return
        connector_id = str(merged_meta.get("connector_id")) if merged_meta.get("connector_id") else None

        # Get thread_id from metadata (passed by Backend)
        # Backend already checked assistant_mode and only forwards when active/shadowing
        thread_id = merged_meta.get("thread_id")
        if not thread_id:
            log.error("agent.missing_thread_id", conversation_id=conversation_id)
            return
        thread_id = str(thread_id)

        # Get order_id from metadata (passed by Backend)
        order_id = merged_meta.get("order_id")

        # Include thread_id and order_id in metadata for downstream tools
        metadata_payload["thread_id"] = thread_id
        if order_id is not None:
            metadata_payload["order_id"] = int(order_id) if isinstance(order_id, (int, str)) else order_id

        result = await process_user_message_agents(
            simple_msg,
            settings,
            large_llm_client,
            tracer,
            backend_client,
            connector_context=connector_context,
        )
        reply_text = result.text or ""
        stage_id = result.stage_id
        correlation_id = _make_correlation_id(conversation_id, batch)

        if not reply_text.strip():
            attention_stage_id = crm_adapter.manager_attention_stage_id()
            await update_customer_fields(
                conversation_id,
                company_id,
                {
                    "handoff_summary": {
                        "text": (
                            "⚠️ Произошла техническая ошибка при генерации ответа. "
                            "Модель достигла лимита токенов и "
                            "вернула некорректный результат. "
                            "Необходимо связаться с клиентом вручную "
                            "и проверить логи системы."
                        ),
                        "reason": "llm_generation_error",
                        "stage": attention_stage_id,
                    }
                },
            )
            log.error(
                "llm.generation_error.handoff_created",
                user_id=conversation_id,
                conversation_id=conversation_id,
                stage_id=attention_stage_id,
            )
            stage_id = attention_stage_id

        # Extract handoff data from pipeline result (set by handoff_commit tool via ContextVar)
        manager_comment = None
        hs: object | None = result.handoff_summary
        if isinstance(hs, dict):
            txt = hs.get("text")
            if isinstance(txt, str) and txt.strip():
                manager_comment = txt
        elif isinstance(hs, str) and hs.strip():
            manager_comment = hs

        if (
            callback_url
            and stage_id is None
            and is_first_message
            and connector_context
            and connector_context.connector_type == ConnectorType.CRM
        ):
            stage_id = crm_adapter.initial_stage_id()
            log.debug(
                "crm.first_message_stage_set",
                conversation_id=conversation_id,
                user_id=conversation_id,
            )

        log.info(
            "debounce.batch.completed",
            conversation_id=conversation_id,
            reply_length=len(reply_text),
            stage_id=stage_id,
        )

        reply_text_trimmed = reply_text.strip()
        if reply_text_trimmed:
            reply_chunks, chunk_delays = split_and_calculate_delays(reply_text_trimmed)

            delivery_metadata = {k: v for k, v in metadata_payload.items() if k not in _PIPELINE_CONTEXT_KEYS}
            if manager_comment:
                delivery_metadata["manager_comment"] = manager_comment
            if stage_id:
                delivery_metadata["stage_id"] = stage_id

            handoff_payload: dict[str, object] | None = None
            if isinstance(hs, dict):
                handoff_payload = {
                    "summary": hs.get("text") or manager_comment,
                    "reason": hs.get("reason"),
                    "manager_comment": manager_comment,
                }
                if hs.get("operator") is not None:
                    handoff_payload["operator_required"] = bool(hs.get("operator"))
                stage_candidate = hs.get("stage") or hs.get("stage_id") or stage_id
                if stage_candidate:
                    handoff_payload["stage"] = stage_candidate
                handoff_payload = {key: value for key, value in handoff_payload.items() if value is not None} or None
                delivery_metadata["handoff_summary"] = dict(hs)

            connector_identifier = (
                resolved_connector_id
                or (connector_context.connector_id if connector_context else None)
                or connector_id
                or "default"
            )
            conversation_value = str(conversation_id or storage_key)

            # Get connector type from metadata (authoritative source from inbound endpoint)
            connector_type = str(merged_meta.get("connector_type") or "").lower()
            if not connector_type and connector_cfg is not None:
                connector_type = str(connector_cfg.type or "").lower()

            is_telegram = connector_type == "telegram"
            is_wappi = connector_type == "wappi"

            log.debug(
                "transport.delivery.routing",
                connector_id=connector_identifier,
                connector_type=connector_type,
                is_telegram=is_telegram,
                is_wappi=is_wappi,
            )

            for chunk_index, chunk in enumerate(reply_chunks):
                cleared_chunk = _apply_message_clearance(chunk)
                if chunk_index > 0:
                    delay = chunk_delays[chunk_index - 1]
                    if delay > 0:
                        log.debug(
                            "message_splitter.delay",
                            chunk_index=chunk_index,
                            delay=delay,
                            correlation_id=correlation_id,
                        )
                        await asyncio.sleep(delay)

                chunk_stage_id = stage_id if chunk_index == len(reply_chunks) - 1 else None
                chunk_handoff = handoff_payload if chunk_index == len(reply_chunks) - 1 else None

                chunk_correlation_id = f"{correlation_id}-{chunk_index}" if len(reply_chunks) > 1 else correlation_id

                log.debug(
                    "message_splitter.sending_chunk",
                    chunk_index=chunk_index,
                    total_chunks=len(reply_chunks),
                    chunk_length=len(cleared_chunk),
                    correlation_id=chunk_correlation_id,
                )

                # NOTE: Backend saves assistant messages when receiving OutboundDeliveryRequest

                if not resolved_connector_id:
                    log.warning(
                        "outbound.delivery.skipped",
                        connector_id=connector_identifier,
                        conversation_id=conversation_id,
                        reason="connector_id_missing",
                    )
                else:
                    outbound_request = OutboundDeliveryRequest(
                        connector_id=resolved_connector_id,
                        conversation_id=conversation_value,
                        thread_id=thread_id,  # Echo back for Backend to save
                        correlation_id=chunk_correlation_id,
                        replies=[cleared_chunk],
                        metadata=delivery_metadata,
                        stage_id=chunk_stage_id,
                        handoff=chunk_handoff,
                    )

                    try:
                        await backend_client.send_outbound_message(outbound_request)
                        log.info(
                            "internal.response.sent",
                            connector_id=resolved_connector_id,
                            conversation_id=conversation_value,
                            correlation_id=chunk_correlation_id,
                        )
                    except Exception as exc:
                        log.error(
                            "outbound.delivery.failed",
                            connector_id=resolved_connector_id,
                            conversation_id=conversation_value,
                            error=str(exc),
                            exc_info=True,
                        )

    async def on_batch_callback(storage_key: str, batch: list[IncomingMessage]) -> None:
        if not batch:
            log.warning("debounce.batch.empty", storage_key=storage_key)
            return

        conversation_id = batch[-1].conversation_id
        connector_id = batch[-1].connector_id
        log.info(
            "debounce.batch.processing",
            storage_key=storage_key,
            conversation_id=conversation_id,
            batch_size=len(batch),
            user_id=conversation_id,
        )

        await transcribe_if_audio(batch, settings, backend_client)

        merged_meta: dict[str, object] = {}
        for item in batch:
            if item.metadata:
                merged_meta.update(item.metadata)

        # NOTE: Backend is the intelligent router. If we receive a message,
        # Backend already decided to forward it (assistant is active, not historical, not manager)
        combined_text = "\n".join([m.text.strip() for m in batch if m.text and m.text.strip()]) or "(пусто)"

        return await handle_agent_batch(
            batch,
            merged_meta,
            combined_text,
            conversation_id,
            connector_id,
            storage_key,
        )

    return on_batch_callback


async def process_reminder(
    app: FastAPI,
    context: CommonConnectorContext,
    thread_id: str,
    order_id: int | None,
    agent_context: dict,
    reminder_instructions: str,
) -> None:
    """Process scheduled reminder via existing pipeline.

    Builds minimal SimpleMessage with metadata, calls pipeline with
    reminder_instructions which get injected into system prompt.
    Response is sent to backend via normal outbound flow.
    Backend enriches transport addressing (chat_id etc.) from Thread.
    """
    simple_msg = SimpleMessage(
        text="",
        from_user=SimpleUser(id=0),
        chat=SimpleChat(id=0),
        message_id=0,
        metadata={
            "company_id": context.company_id,
            "connector_id": context.connector_id,
            "connector_type": context.type,
            "channel_type": context.channel_type,
            "thread_id": thread_id,
            "order_id": order_id,
            "agent_context": agent_context,
        },
    )

    result = await process_user_message_agents(
        simple_msg,
        settings=app.state.settings,
        large_llm_client=app.state.large_llm_client,
        tracer=app.state.tracer,
        backend_client=app.state.backend_client,
        connector_context=None,
        reminder_instructions=reminder_instructions,
        trace_name="task.execute",
    )

    if not result.text or not result.text.strip():
        return

    correlation_id = make_correlation_id("reminder", thread_id)
    outbound_request = OutboundDeliveryRequest(
        connector_id=context.connector_id,
        conversation_id="",
        thread_id=thread_id,
        correlation_id=correlation_id,
        replies=[result.text],
        metadata={"company_id": context.company_id},
    )
    try:
        await app.state.backend_client.send_outbound_message(outbound_request)
        log.info(
            "reminder.outbound.sent",
            correlation_id=correlation_id,
            thread_id=thread_id,
            company_id=context.company_id,
        )
    except Exception as exc:
        log.error(
            "reminder.outbound.failed",
            correlation_id=correlation_id,
            thread_id=thread_id,
            company_id=context.company_id,
            error=str(exc),
            exc_info=True,
        )
