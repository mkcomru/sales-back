"""Transport-related event payload contracts."""

from enum import StrEnum

from common.events.contracts.base import BaseEventPayload


class ChangeType(StrEnum):
    """Type of change that occurred."""

    UPSERT = "upsert"
    DELETE = "delete"
    BULK = "bulk"


class ResourceType(StrEnum):
    """Type of transport resource that changed."""

    TELEGRAM_BOT = "telegram_bot"
    WAPPI_CONNECTOR = "wappi_connector"
    CONNECTORS_AGGREGATE = "connectors_aggregate"


class TransportConnectorsChangedPayloadV1(BaseEventPayload):
    """
    Payload for transport.connectors.changed event (v1).

    Signal-only: identifies what changed, not the actual data.
    Consumers should call GET /transport/connectors to fetch current state.
    """

    change_type: ChangeType
    resource: ResourceType
    company_id: int | None = None
    connector_id: str | None = None
