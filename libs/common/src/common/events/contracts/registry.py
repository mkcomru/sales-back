"""Payload registry for event contract validation."""

from typing import Any

from pydantic import BaseModel

from common.events.envelope import EventName

PayloadModel = type[BaseModel]

_PAYLOAD_REGISTRY: dict[tuple[EventName, int], PayloadModel] = {}


class UnknownEventError(Exception):
    """Raised when an event name/version combination has no registered payload."""


def register_payload(
    event_name: EventName,
    version: int,
    model: PayloadModel,
) -> None:
    """
    Register a payload model for an event name and version.

    Args:
        event_name: Event name enum value
        version: Payload schema version
        model: Pydantic model class for the payload
    """
    key = (event_name, version)
    if key in _PAYLOAD_REGISTRY:
        msg = f"Payload already registered for {event_name.value} v{version}"
        raise ValueError(msg)
    _PAYLOAD_REGISTRY[key] = model


def get_payload_model(event_name: EventName, version: int) -> PayloadModel:
    """
    Get the payload model for an event name and version.

    Args:
        event_name: Event name enum value
        version: Payload schema version

    Returns:
        Pydantic model class for the payload

    Raises:
        UnknownEventError: If no payload is registered for the combination
    """
    key = (event_name, version)
    model = _PAYLOAD_REGISTRY.get(key)
    if model is None:
        msg = f"No payload registered for {event_name.value} v{version}"
        raise UnknownEventError(msg)
    return model


def validate_payload(
    event_name: EventName,
    version: int,
    payload: dict[str, Any],
) -> BaseModel:
    """
    Validate a payload dict against the registered model.

    Args:
        event_name: Event name enum value
        version: Payload schema version
        payload: Raw payload dict from event

    Returns:
        Validated Pydantic model instance

    Raises:
        UnknownEventError: If no payload is registered
        ValidationError: If payload doesn't match schema
    """
    model = get_payload_model(event_name, version)
    return model.model_validate(payload)


class PayloadRegistry:
    """
    Convenience class for working with payload registrations.

    Provides a cleaner API for registration and lookup.
    """

    @staticmethod
    def register(
        event_name: EventName,
        version: int,
        model: PayloadModel,
    ) -> None:
        """Register a payload model."""
        register_payload(event_name, version, model)

    @staticmethod
    def get(event_name: EventName, version: int) -> PayloadModel:
        """Get a payload model."""
        return get_payload_model(event_name, version)

    @staticmethod
    def validate(
        event_name: EventName,
        version: int,
        payload: dict[str, Any],
    ) -> BaseModel:
        """Validate a payload."""
        return validate_payload(event_name, version, payload)

    @staticmethod
    def is_registered(event_name: EventName, version: int) -> bool:
        """Check if a payload is registered."""
        return (event_name, version) in _PAYLOAD_REGISTRY


# Register known payloads on import
def _register_builtin_payloads() -> None:
    """Register all built-in payload contracts."""
    from common.events.contracts.prompt import (
        CompanySpecificationChangedPayloadV1,
        PromptChangedPayloadV1,
    )
    from common.events.contracts.transport import TransportConnectorsChangedPayloadV1

    register_payload(
        EventName.TRANSPORT_CONNECTORS_CHANGED,
        version=1,
        model=TransportConnectorsChangedPayloadV1,
    )
    register_payload(
        EventName.PROMPT_CHANGED,
        version=1,
        model=PromptChangedPayloadV1,
    )
    register_payload(
        EventName.COMPANY_SPECIFICATION_CHANGED,
        version=1,
        model=CompanySpecificationChangedPayloadV1,
    )


_register_builtin_payloads()
