"""Tests for TransportDeliveryPayload model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from common.models.transport import AttachmentDescriptor
from wappi_module.transport.models import TransportDeliveryPayload


class TestTransportDeliveryPayload:
    def test_valid_payload(self) -> None:
        payload = TransportDeliveryPayload(
            connector_id="test",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            replies=["Message 1", "Message 2"],
            metadata={"chat_id": "351311665"},
        )

        assert payload.connector_id == "test"
        assert payload.company_id == "123"
        assert payload.channel_type == "telegram"
        assert payload.user_id == "user123"
        assert payload.conversation_id == "conv123"
        assert payload.correlation_id == "corr123"
        assert payload.replies == ["Message 1", "Message 2"]
        assert payload.metadata == {"chat_id": "351311665"}

    def test_replies_strip_whitespace(self) -> None:
        payload = TransportDeliveryPayload(
            connector_id="test",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            replies=["  Message 1  ", "  Message 2  "],
        )
        assert payload.replies == ["Message 1", "Message 2"]

    def test_empty_replies_filtered_out(self) -> None:
        payload = TransportDeliveryPayload(
            connector_id="test",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            replies=["Valid", "", "  ", "Also valid"],
        )
        assert payload.replies == ["Valid", "Also valid"]

    def test_all_empty_replies_raises_error(self) -> None:
        with pytest.raises(ValidationError, match="Either replies or attachments must be non-empty"):
            TransportDeliveryPayload(
                connector_id="test",
                company_id="123",
                channel_type="telegram",
                user_id="user123",
                conversation_id="conv123",
                correlation_id="corr123",
                replies=["", "  ", "   "],
            )

    def test_empty_replies_list_raises_error(self) -> None:
        with pytest.raises(ValidationError):
            TransportDeliveryPayload(
                connector_id="test",
                company_id="123",
                channel_type="telegram",
                user_id="user123",
                conversation_id="conv123",
                correlation_id="corr123",
                replies=[],
            )

    def test_optional_fields(self) -> None:
        attachment = AttachmentDescriptor(artifact_id="art-1", type="image", mime_type="image/jpeg")
        payload = TransportDeliveryPayload(
            connector_id="test",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            replies=["Message"],
            stage_id="stage1",
            handoff={"agent": "human"},
            delivery_hint={"priority": "high"},
            attachments=[attachment],
        )

        assert payload.stage_id == "stage1"
        assert payload.handoff == {"agent": "human"}
        assert payload.delivery_hint == {"priority": "high"}
        assert payload.attachments == [attachment]

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            TransportDeliveryPayload(
                connector_id="test",
                company_id="123",
                channel_type="telegram",
                user_id="user123",
                conversation_id="conv123",
                correlation_id="corr123",
                replies=["Message"],
                unknown_field="should_fail",
            )

    def test_metadata_default(self) -> None:
        payload = TransportDeliveryPayload(
            connector_id="test",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            replies=["Message"],
        )
        assert payload.metadata == {}

    def test_required_fields_missing(self) -> None:
        with pytest.raises(ValidationError):
            TransportDeliveryPayload(
                connector_id="test",
                company_id="123",
            )

    def test_replies_with_empty_strings_filtered(self) -> None:
        payload = TransportDeliveryPayload(
            connector_id="test",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            replies=["Valid", "", "  ", "Also valid"],
        )
        assert payload.replies == ["Valid", "Also valid"]

    def test_single_reply(self) -> None:
        payload = TransportDeliveryPayload(
            connector_id="test",
            company_id="123",
            channel_type="telegram",
            user_id="user123",
            conversation_id="conv123",
            correlation_id="corr123",
            replies=["Single message"],
        )
        assert len(payload.replies) == 1
        assert payload.replies[0] == "Single message"
