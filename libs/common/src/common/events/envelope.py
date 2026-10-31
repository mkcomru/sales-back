"""Strongly-typed event envelope for signal-only events."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class Producer(StrEnum):
    """Known event producers. Only backend should publish events."""

    BACKEND = "backend"


class EventName(StrEnum):
    """Canonical event names. Maps 1:1 with payload contracts."""

    TRANSPORT_CONNECTORS_CHANGED = "transport.connectors.changed"
    PROMPT_CHANGED = "prompt.changed"
    COMPANY_SPECIFICATION_CHANGED = "company.specification.changed"


class EventTrace(BaseModel):
    """Optional tracing context for correlation."""

    model_config = ConfigDict(frozen=True)

    correlation_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None


class EventEnvelope(BaseModel):
    """
    Strongly-typed envelope for all events.

    Events are signals, not state. Payloads are minimal; consumers must fetch
    current truth via backend APIs after receiving the signal.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_name: EventName
    event_version: int = Field(ge=1, description="Payload schema version")
    event_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )
    producer: Producer
    dedupe_key: str = Field(
        min_length=1,
        description="Stable key for at-least-once idempotency",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific payload; validated against contracts",
    )
    trace: EventTrace | None = None

    def with_trace(
        self,
        correlation_id: str | None = None,
        trace_id: str | None = None,
        span_id: str | None = None,
    ) -> "EventEnvelope":
        """Return a copy with trace context attached."""
        return self.model_copy(
            update={
                "trace": EventTrace(
                    correlation_id=correlation_id,
                    trace_id=trace_id,
                    span_id=span_id,
                )
            }
        )
