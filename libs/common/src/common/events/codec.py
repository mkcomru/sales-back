"""JSON codec for event envelope serialization."""

from common.events.envelope import EventEnvelope


def encode_envelope(envelope: EventEnvelope) -> bytes:
    """Serialize an event envelope to JSON bytes using Pydantic's native encoder."""
    return envelope.model_dump_json().encode("utf-8")


def decode_envelope(data: bytes) -> EventEnvelope:
    """
    Deserialize JSON bytes to an event envelope using Pydantic's native decoder.

    Raises:
        ValueError: If data is not valid JSON or envelope structure is invalid
    """
    try:
        return EventEnvelope.model_validate_json(data)
    except Exception as exc:
        raise ValueError(f"Invalid event envelope: {exc}") from exc
