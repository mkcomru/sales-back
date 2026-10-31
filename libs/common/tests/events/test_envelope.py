"""Tests for event envelope."""

from datetime import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from common.events.envelope import EventEnvelope, EventName, EventTrace, Producer


class TestEventEnvelope:
    def test_create_minimal_envelope(self) -> None:
        envelope = EventEnvelope(
            event_name=EventName.TRANSPORT_CONNECTORS_CHANGED,
            event_version=1,
            producer=Producer.BACKEND,
            dedupe_key="test-key",
        )

        assert envelope.event_name == EventName.TRANSPORT_CONNECTORS_CHANGED
        assert envelope.event_version == 1
        assert envelope.producer == Producer.BACKEND
        assert envelope.dedupe_key == "test-key"
        assert envelope.payload == {}
        assert envelope.trace is None
        assert isinstance(envelope.event_id, UUID)
        assert isinstance(envelope.occurred_at, datetime)

    def test_create_envelope_with_payload(self) -> None:
        envelope = EventEnvelope(
            event_name=EventName.TRANSPORT_CONNECTORS_CHANGED,
            event_version=1,
            producer=Producer.BACKEND,
            dedupe_key="test-key",
            payload={"change_type": "upsert", "connector_id": "test-bot"},
        )

        assert envelope.payload == {"change_type": "upsert", "connector_id": "test-bot"}

    def test_with_trace(self) -> None:
        envelope = EventEnvelope(
            event_name=EventName.TRANSPORT_CONNECTORS_CHANGED,
            event_version=1,
            producer=Producer.BACKEND,
            dedupe_key="test-key",
        )

        traced = envelope.with_trace(
            correlation_id="corr-123",
            trace_id="trace-456",
        )

        assert traced.trace is not None
        assert traced.trace.correlation_id == "corr-123"
        assert traced.trace.trace_id == "trace-456"
        assert traced.trace.span_id is None
        assert envelope.trace is None

    def test_envelope_is_frozen(self) -> None:
        envelope = EventEnvelope(
            event_name=EventName.TRANSPORT_CONNECTORS_CHANGED,
            event_version=1,
            producer=Producer.BACKEND,
            dedupe_key="test-key",
        )

        with pytest.raises(ValidationError):
            envelope.dedupe_key = "new-key"  # type: ignore[misc]

    def test_envelope_forbids_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            EventEnvelope(
                event_name=EventName.TRANSPORT_CONNECTORS_CHANGED,
                event_version=1,
                producer=Producer.BACKEND,
                dedupe_key="test-key",
                extra_field="not-allowed",  # type: ignore[call-arg]
            )

    def test_dedupe_key_required(self) -> None:
        with pytest.raises(ValidationError):
            EventEnvelope(
                event_name=EventName.TRANSPORT_CONNECTORS_CHANGED,
                event_version=1,
                producer=Producer.BACKEND,
                dedupe_key="",
            )


class TestEventTrace:
    def test_create_trace(self) -> None:
        trace = EventTrace(
            correlation_id="corr-1",
            trace_id="trace-2",
            span_id="span-3",
        )

        assert trace.correlation_id == "corr-1"
        assert trace.trace_id == "trace-2"
        assert trace.span_id == "span-3"

    def test_trace_is_frozen(self) -> None:
        trace = EventTrace(correlation_id="corr-1")

        with pytest.raises(ValidationError):
            trace.correlation_id = "new"  # type: ignore[misc]
