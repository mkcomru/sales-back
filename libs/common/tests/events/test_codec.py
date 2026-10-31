"""Tests for event envelope codec (JSON serialization)."""

from datetime import UTC, datetime

import pytest

from common.events.codec import decode_envelope, encode_envelope
from common.events.envelope import EventEnvelope, EventName, Producer


class TestCodec:
    def test_roundtrip_minimal(self) -> None:
        original = EventEnvelope(
            event_name=EventName.TRANSPORT_CONNECTORS_CHANGED,
            event_version=1,
            producer=Producer.BACKEND,
            dedupe_key="test-roundtrip",
        )

        encoded = encode_envelope(original)
        decoded = decode_envelope(encoded)

        assert decoded.event_name == original.event_name
        assert decoded.event_version == original.event_version
        assert decoded.producer == original.producer
        assert decoded.dedupe_key == original.dedupe_key
        assert decoded.event_id == original.event_id
        assert decoded.payload == original.payload

    def test_roundtrip_with_payload(self) -> None:
        original = EventEnvelope(
            event_name=EventName.TRANSPORT_CONNECTORS_CHANGED,
            event_version=1,
            producer=Producer.BACKEND,
            dedupe_key="test-payload",
            payload={
                "change_type": "upsert",
                "resource": "telegram_bot",
                "company_id": 42,
                "connector_id": "bot-123",
            },
        )

        encoded = encode_envelope(original)
        decoded = decode_envelope(encoded)

        assert decoded.payload == original.payload

    def test_roundtrip_with_trace(self) -> None:
        original = EventEnvelope(
            event_name=EventName.TRANSPORT_CONNECTORS_CHANGED,
            event_version=1,
            producer=Producer.BACKEND,
            dedupe_key="test-trace",
        ).with_trace(
            correlation_id="corr-abc",
            trace_id="trace-xyz",
        )

        encoded = encode_envelope(original)
        decoded = decode_envelope(encoded)

        assert decoded.trace is not None
        assert decoded.trace.correlation_id == "corr-abc"
        assert decoded.trace.trace_id == "trace-xyz"

    def test_decode_invalid_json(self) -> None:
        with pytest.raises(ValueError, match="Invalid event envelope"):
            decode_envelope(b"not-json")

    def test_decode_non_object(self) -> None:
        with pytest.raises(ValueError, match="Invalid event envelope"):
            decode_envelope(b'"just a string"')

    def test_encode_produces_bytes(self) -> None:
        envelope = EventEnvelope(
            event_name=EventName.TRANSPORT_CONNECTORS_CHANGED,
            event_version=1,
            producer=Producer.BACKEND,
            dedupe_key="test-bytes",
        )

        encoded = encode_envelope(envelope)

        assert isinstance(encoded, bytes)

    def test_datetime_iso_format(self) -> None:
        envelope = EventEnvelope(
            event_name=EventName.TRANSPORT_CONNECTORS_CHANGED,
            event_version=1,
            producer=Producer.BACKEND,
            dedupe_key="test-datetime",
            occurred_at=datetime(2025, 6, 15, 10, 30, 0, tzinfo=UTC),
        )

        encoded = encode_envelope(envelope)
        decoded = decode_envelope(encoded)

        assert decoded.occurred_at.year == 2025
        assert decoded.occurred_at.month == 6
        assert decoded.occurred_at.day == 15
