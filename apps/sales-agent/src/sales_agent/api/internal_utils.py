"""Utilities for internal API endpoints."""

import mimetypes
from typing import Any

from common import ArtifactService
from common.models import InternalInboundRequest

from src.sales_agent.services.debounce import IncomingMessage


def map_to_incoming_message(request: InternalInboundRequest) -> IncomingMessage:
    """Map InternalInboundRequest to IncomingMessage for debouncer."""
    envelope = request.envelope
    context = request.context

    attachments: list[dict[str, Any]] = []
    for artifact_id in envelope.artifact_ids or []:
        parsed = ArtifactService.parse_artifact_id(artifact_id)
        file_type = parsed["file_type"]
        mime_type, _ = mimetypes.guess_type(artifact_id)
        attachments.append(
            {
                "type": file_type,
                "artifact_id": artifact_id,
                "mime": mime_type or "application/octet-stream",
            }
        )

    storage_key = context.debounce.storage_key_template.format(
        connector_id=context.connector_id,
        conversation_id=envelope.conversation_id,
        user_id=envelope.user_id,
        channel_type=context.channel_type,
    )

    return IncomingMessage(
        connector_id=context.connector_id,
        conversation_id=envelope.conversation_id,
        user_id=envelope.user_id,
        text=envelope.text,
        attachments=attachments,
        ts=envelope.ts,
        metadata={
            "connector_id": context.connector_id,
            "company_id": context.company_id,
            "connector_type": context.type,
            "channel_type": context.channel_type,
            "conversation_id": envelope.conversation_id,
            "user_id": envelope.user_id,
            "thread_id": request.thread_id,
            "order_id": request.order_id,
            "order_stage": request.order_stage,
            "provider_message_id": envelope.message_id,
            "qualification_workflow": request.qualification_workflow,
            "qualification_examples": request.qualification_examples,
            "agent_context": request.agent_context.model_dump(mode="json"),
            **envelope.extra,
        },
        debounce_seconds=context.debounce.window_seconds,
        storage_key=storage_key,
    )
