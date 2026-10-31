"""Tests for outbound message models."""

import pytest

from common.models import (
    AgentResponse,
    ConnectorContext,
    HandoffPayload,
    InboundEnvelope,
    InternalInboundRequest,
    MessageRole,
    OutboundDeliveryRequest,
)


class TestHandoffPayload:
    """Tests for HandoffPayload model."""

    def test_handoff_payload_creation(self):
        """Test creating HandoffPayload with required fields."""
        handoff = HandoffPayload(
            summary="Customer needs help",
            reason="Complex issue",
            stage="HANDOFF",
        )
        assert handoff.summary == "Customer needs help"
        assert handoff.reason == "Complex issue"
        assert handoff.stage == "HANDOFF"

    def test_handoff_payload_optional_stage(self):
        """Test HandoffPayload with optional stage."""
        handoff = HandoffPayload(
            summary="Summary",
            reason="Reason",
            stage=None,
        )
        assert handoff.stage is None


class TestAgentResponse:
    """Tests for AgentResponse model."""

    def test_agent_response_creation(self):
        """Test creating AgentResponse with all fields."""
        handoff = HandoffPayload(
            summary="Summary",
            reason="Reason",
        )
        response = AgentResponse(
            connector_id="tg-bot-123",
            conversation_id="conv-123",
            correlation_id="corr-123",
            replies=["Hello", "How can I help?"],
            metadata={"key": "value"},
            stage_id="QUALIFIED",
            handoff=handoff,
        )
        assert response.connector_id == "tg-bot-123"
        assert response.conversation_id == "conv-123"
        assert response.correlation_id == "corr-123"
        assert response.replies == ["Hello", "How can I help?"]
        assert response.metadata == {"key": "value"}
        assert response.stage_id == "QUALIFIED"
        assert response.handoff == handoff

    def test_agent_response_minimal(self):
        """Test creating AgentResponse with minimal required fields."""
        response = AgentResponse(
            connector_id="tg-bot-123",
            conversation_id="conv-123",
            correlation_id="corr-123",
            replies=["Hello"],
        )
        assert response.metadata == {}
        assert response.stage_id is None
        assert response.handoff is None

    def test_agent_response_empty_replies(self):
        """Test AgentResponse with empty replies list."""
        response = AgentResponse(
            connector_id="tg-bot-123",
            conversation_id="conv-123",
            correlation_id="corr-123",
            replies=[],
        )
        assert response.replies == []


class TestInternalInboundRequest:
    """Tests for InternalInboundRequest model."""

    def test_internal_inbound_request_creation(self):
        """Test creating InternalInboundRequest."""
        envelope = InboundEnvelope(
            conversation_id="conv-123",
            user_id="user-123",
            text="Hello",
            ts=1234567890.0,
        )
        context = ConnectorContext(
            connector_id="tg-bot-123",
            company_id=1,
            type="telegram",
            channel_type="telegram",
            debounce={"window_seconds": 45, "storage_key_template": "{connector_id}:{conversation_id}"},
        )
        request = InternalInboundRequest(envelope=envelope, context=context, thread_id="telegram_123_abc")
        assert request.envelope == envelope
        assert request.context == context
        assert request.thread_id == "telegram_123_abc"

    def test_internal_inbound_request_with_audio(self):
        """Test InternalInboundRequest with audio attachment."""
        envelope = InboundEnvelope(
            conversation_id="conv-456",
            user_id="user-456",
            text=None,
            ts=1234567890.0,
            artifact_ids=["company_2/voice/test_audio.mp3"],
        )
        context = ConnectorContext(
            connector_id="tg-bot-456",
            company_id=2,
            type="telegram",
            channel_type="telegram",
            debounce={"window_seconds": 30, "storage_key_template": "{connector_id}:{conversation_id}"},
        )
        request = InternalInboundRequest(envelope=envelope, context=context, thread_id="telegram_456_def")
        assert len(request.envelope.artifact_ids) == 1
        assert request.envelope.artifact_ids[0] == "company_2/voice/test_audio.mp3"
        assert request.thread_id == "telegram_456_def"

    def test_internal_inbound_request_with_message_role(self):
        """Test InternalInboundRequest with MessageRole fields."""
        envelope = InboundEnvelope(
            conversation_id="conv-789",
            user_id="user-789",
            text="Manager message",
            ts=1234567890.0,
            role=MessageRole.MANAGER,
            is_historical=True,
            sender_name="John Manager",
            sender_username="john_manager",
        )
        context = ConnectorContext(
            connector_id="wappi-123",
            company_id=3,
            type="wappi",
            channel_type="whatsapp",
            debounce={"window_seconds": 45, "storage_key_template": "{connector_id}:{conversation_id}"},
        )
        request = InternalInboundRequest(envelope=envelope, context=context, thread_id="whatsapp_789_ghi")
        assert request.envelope.role == MessageRole.MANAGER
        assert request.envelope.is_historical is True
        assert request.envelope.sender_name == "John Manager"
        assert request.envelope.sender_username == "john_manager"


class TestOutboundDeliveryRequest:
    """Tests for OutboundDeliveryRequest model."""

    def test_outbound_delivery_request_creation(self):
        """Test creating OutboundDeliveryRequest with all fields."""
        request = OutboundDeliveryRequest(
            connector_id="tg-bot-123",
            conversation_id="conv-123",
            thread_id="telegram_123_abc",
            correlation_id="corr-123",
            replies=["Hello", "How can I help?"],
            metadata={"key": "value"},
            stage_id="QUALIFIED",
            handoff={
                "summary": "Summary",
                "reason": "Reason",
                "stage": "HANDOFF",
            },
        )
        assert request.connector_id == "tg-bot-123"
        assert request.conversation_id == "conv-123"
        assert request.thread_id == "telegram_123_abc"
        assert request.correlation_id == "corr-123"
        assert request.replies == ["Hello", "How can I help?"]
        assert request.metadata == {"key": "value"}
        assert request.stage_id == "QUALIFIED"
        assert request.handoff == {
            "summary": "Summary",
            "reason": "Reason",
            "stage": "HANDOFF",
        }

    def test_outbound_delivery_request_minimal(self):
        """Test creating OutboundDeliveryRequest with minimal fields."""
        request = OutboundDeliveryRequest(
            connector_id="tg-bot-123",
            conversation_id="conv-123",
            thread_id="telegram_123_abc",
            correlation_id="corr-123",
            replies=["Hello"],
        )
        assert request.thread_id == "telegram_123_abc"
        assert request.metadata == {}
        assert request.stage_id is None
        assert request.handoff is None

    def test_outbound_delivery_request_requires_thread_id(self):
        """Test OutboundDeliveryRequest requires thread_id."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            OutboundDeliveryRequest(
                connector_id="tg-bot-123",
                conversation_id="conv-123",
                correlation_id="corr-123",
                replies=["Hello"],
                # missing thread_id should fail
            )
