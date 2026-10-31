"""Shared event payload contracts.

All modules import contracts from here to ensure schema consistency.
Each event has its own payload model (no "god" payloads).
"""

from common.events.contracts.base import BaseEventPayload, CompanyScopedPayload
from common.events.contracts.prompt import (
    CompanySpecificationChangedPayloadV1,
    PromptChangedPayloadV1,
)
from common.events.contracts.registry import (
    PayloadRegistry,
    UnknownEventError,
    get_payload_model,
    register_payload,
)
from common.events.contracts.transport import (
    ChangeType,
    ResourceType,
    TransportConnectorsChangedPayloadV1,
)

__all__ = [
    "BaseEventPayload",
    "ChangeType",
    "CompanyScopedPayload",
    "CompanySpecificationChangedPayloadV1",
    "PayloadRegistry",
    "PromptChangedPayloadV1",
    "ResourceType",
    "TransportConnectorsChangedPayloadV1",
    "UnknownEventError",
    "get_payload_model",
    "register_payload",
]
