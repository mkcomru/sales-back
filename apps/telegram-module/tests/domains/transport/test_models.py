"""Tests for TransportDeliveryPayload model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from common.models.transport import AttachmentDescriptor
from telegram_module.transport.models import TransportDeliveryPayload


class TestTransportDeliveryPayload:
    """Test TransportDeliveryPayload model."""

    def test_payload_minimal(self) -> None:
        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="test-company",
            channel_type="telegram",
            user_id="user-123",
            conversation_id="conv-456",
            correlation_id="corr-789",
            replies=["Hello"],
        )

        assert payload.connector_id == "test-connector"
        assert payload.company_id == "test-company"
        assert payload.channel_type == "telegram"
        assert payload.user_id == "user-123"
        assert payload.conversation_id == "conv-456"
        assert payload.correlation_id == "corr-789"
        assert payload.replies == ["Hello"]
        assert payload.metadata == {}
        assert payload.stage_id is None
        assert payload.handoff is None
        assert payload.delivery_hint is None
        assert payload.attachments is None

    def test_payload_full(self) -> None:
        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="test-company",
            channel_type="telegram",
            user_id="user-123",
            conversation_id="conv-456",
            correlation_id="corr-789",
            replies=["Hello", "World"],
            metadata={"key": "value"},
            stage_id="stage-1",
            handoff={"agent": "human"},
            delivery_hint={"priority": "high"},
            attachments=[AttachmentDescriptor(artifact_id="art-1", type="image", mime_type="image/jpeg")],
        )

        assert payload.replies == ["Hello", "World"]
        assert payload.metadata == {"key": "value"}
        assert payload.stage_id == "stage-1"
        assert payload.handoff == {"agent": "human"}
        assert payload.delivery_hint == {"priority": "high"}
        assert payload.attachments is not None
        assert len(payload.attachments) == 1

    def test_payload_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            TransportDeliveryPayload(
                company_id="test-company",
                channel_type="telegram",
                user_id="user-123",
                conversation_id="conv-456",
                correlation_id="corr-789",
                replies=["Hello"],
            )

    def test_payload_replies_required(self) -> None:
        with pytest.raises(ValidationError):
            TransportDeliveryPayload(
                connector_id="test-connector",
                company_id="test-company",
                channel_type="telegram",
                user_id="user-123",
                conversation_id="conv-456",
                correlation_id="corr-789",
                replies=[],
            )

    def test_payload_replies_stripped(self) -> None:
        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="test-company",
            channel_type="telegram",
            user_id="user-123",
            conversation_id="conv-456",
            correlation_id="corr-789",
            replies=["  Hello  ", "  World  ", "   "],
        )

        assert payload.replies == ["Hello", "World"]

    def test_payload_replies_empty_after_strip(self) -> None:
        with pytest.raises(ValidationError):
            TransportDeliveryPayload(
                connector_id="test-connector",
                company_id="test-company",
                channel_type="telegram",
                user_id="user-123",
                conversation_id="conv-456",
                correlation_id="corr-789",
                replies=["   ", "  "],
            )

    def test_payload_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            TransportDeliveryPayload(
                connector_id="test-connector",
                company_id="test-company",
                channel_type="telegram",
                user_id="user-123",
                conversation_id="conv-456",
                correlation_id="corr-789",
                replies=["Hello"],
                extra_field="should fail",
            )
