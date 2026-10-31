"""Tests for event contracts."""

import pytest
from pydantic import ValidationError

from common.events.contracts import (
    ChangeType,
    PayloadRegistry,
    ResourceType,
    TransportConnectorsChangedPayloadV1,
    UnknownEventError,
)
from common.events.envelope import EventName


class TestTransportConnectorsChangedPayload:
    def test_create_payload(self) -> None:
        payload = TransportConnectorsChangedPayloadV1(
            change_type=ChangeType.UPSERT,
            resource=ResourceType.TELEGRAM_BOT,
            company_id=42,
            connector_id="bot-123",
        )

        assert payload.change_type == ChangeType.UPSERT
        assert payload.resource == ResourceType.TELEGRAM_BOT
        assert payload.company_id == 42
        assert payload.connector_id == "bot-123"

    def test_create_payload_without_optional_fields(self) -> None:
        payload = TransportConnectorsChangedPayloadV1(
            change_type=ChangeType.BULK,
            resource=ResourceType.CONNECTORS_AGGREGATE,
        )

        assert payload.company_id is None
        assert payload.connector_id is None

    def test_payload_is_frozen(self) -> None:
        payload = TransportConnectorsChangedPayloadV1(
            change_type=ChangeType.DELETE,
            resource=ResourceType.WAPPI_CONNECTOR,
        )

        with pytest.raises(ValidationError):
            payload.change_type = ChangeType.UPSERT  # type: ignore[misc]


class TestPayloadRegistry:
    def test_get_registered_payload(self) -> None:
        model = PayloadRegistry.get(
            EventName.TRANSPORT_CONNECTORS_CHANGED,
            version=1,
        )

        assert model == TransportConnectorsChangedPayloadV1

    def test_is_registered(self) -> None:
        assert PayloadRegistry.is_registered(
            EventName.TRANSPORT_CONNECTORS_CHANGED,
            version=1,
        )

    def test_is_not_registered(self) -> None:
        assert not PayloadRegistry.is_registered(
            EventName.TRANSPORT_CONNECTORS_CHANGED,
            version=999,
        )

    def test_get_unknown_raises(self) -> None:
        with pytest.raises(UnknownEventError):
            PayloadRegistry.get(
                EventName.TRANSPORT_CONNECTORS_CHANGED,
                version=999,
            )

    def test_validate_payload(self) -> None:
        validated = PayloadRegistry.validate(
            EventName.TRANSPORT_CONNECTORS_CHANGED,
            version=1,
            payload={
                "change_type": "upsert",
                "resource": "telegram_bot",
                "company_id": 1,
            },
        )

        assert isinstance(validated, TransportConnectorsChangedPayloadV1)
        assert validated.change_type == ChangeType.UPSERT
