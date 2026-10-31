"""Outbound message schemas for Backend routing.

These schemas define the contract between Sales Agent and Backend for outbound routing.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from common.models.inbound import ConnectorContext, InboundEnvelope


class TaskAutoAction(str, Enum):
    """Auto-action types for AI-scheduled tasks."""

    SEND_FOLLOWUP_MESSAGE = "send_followup_message"


class HandoffPayload(BaseModel):
    """Handoff information for CRM integration."""

    summary: str
    reason: str
    stage: str | None = None


class AgentResponse(BaseModel):
    """Response from Sales Agent to Backend for outbound routing."""

    connector_id: str
    conversation_id: str
    correlation_id: str
    replies: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)
    stage_id: str | None = None
    handoff: HandoffPayload | None = None


class AgentContext(BaseModel):
    """Full context for Sales Agent LLM execution.

    Assembled by Backend so that Sales Agent needs zero read calls.
    """

    prompt_template: str = Field(description="Raw Jinja2 prompt template from DB")
    company: dict[str, Any] = Field(
        description="Company spec: name, description, fields, categories, tools, stages, etc."
    )
    customer_answers: dict[str, Any] = Field(default_factory=dict, description="Current customer field values")
    order_fields: dict[str, Any] = Field(default_factory=dict, description="Current order field values")
    extra_fields: dict[str, Any] = Field(
        default_factory=dict, description="AI-discovered extra fields on the active order"
    )
    history: list[dict[str, Any]] = Field(
        default_factory=list, description="Recent messages [{role, content, metadata, created_at}, ...], capped at 20"
    )
    enabled_tools: list[str] = Field(default_factory=list, description="Enabled tool names for handler wiring")
    active_capabilities: list[str] = Field(
        default_factory=list, description="Active integration capabilities for this company"
    )
    customer_name: str | None = Field(
        default=None, description="Customer display name (e.g. from Telegram first+last name)"
    )
    langfuse_session_id: str | None = Field(default=None, description="Langfuse session ID for tracing")
    form_data: dict[str, Any] | None = Field(default=None, description="Unified form payload if any")


class BaseInternalRequest(BaseModel):
    """Base class for internal Backend → Sales Agent requests."""

    context: ConnectorContext
    thread_id: str = Field(description="Backend-created thread ID")
    order_id: int | None = Field(default=None, description="Active order ID")
    agent_context: AgentContext = Field(description="Full LLM execution context assembled by Backend")


class InternalInboundRequest(BaseInternalRequest):
    """Internal request for inbound message processing."""

    envelope: InboundEnvelope
    order_stage: dict[str, Any] | None = Field(
        default=None, description="Current order stage info (id, name, position, color)"
    )
    qualification_workflow: str | None = Field(
        default=None,
        description="Qualification workflow from prompt_addon or company fallback",
    )
    qualification_examples: str | None = Field(
        default=None,
        description="Qualification examples from prompt_addon or company fallback",
    )


class PingContext(BaseModel):
    """Context for auto-ping tasks, passed alongside TaskExecutionRequest."""

    ping_rule_id: int
    content_type: str
    static_content: str | None = None
    prompt_override: str | None = None


class TaskExecutionRequest(BaseInternalRequest):
    """Internal request for scheduled task execution."""

    task_id: int
    auto_action: TaskAutoAction
    title: str
    description: str | None = None
    ping_context: PingContext | None = None


class OutboundDeliveryRequest(BaseModel):
    """Request from Sales Agent to Backend for outbound delivery."""

    connector_id: str
    conversation_id: str
    thread_id: str = Field(description="Thread ID echoed back for Backend to save assistant messages")
    correlation_id: str
    replies: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)
    stage_id: str | None = None
    handoff: dict[str, Any] | None = None
