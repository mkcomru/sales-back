"""Tests for inbound message models."""

import pytest

from common.models import InboundEnvelope, MessageRole


class TestMessageRole:
    """Tests for MessageRole enum."""

    def test_message_role_values(self):
        """Test MessageRole enum values."""
        assert MessageRole.USER == "user"
        assert MessageRole.MANAGER == "manager"

    def test_message_role_from_string(self):
        """Test creating MessageRole from string."""
        assert MessageRole("user") == MessageRole.USER
        assert MessageRole("manager") == MessageRole.MANAGER

    def test_message_role_invalid(self):
        """Test invalid MessageRole raises error."""
        with pytest.raises(ValueError):
            MessageRole("invalid")


class TestInboundEnvelope:
    """Tests for InboundEnvelope model."""

    def test_inbound_envelope_minimal(self):
        """Test creating InboundEnvelope with minimal fields."""
        envelope = InboundEnvelope(
            conversation_id="conv-123",
            user_id="user-123",
            ts=1234567890.0,
        )
        assert envelope.conversation_id == "conv-123"
        assert envelope.user_id == "user-123"
        assert envelope.ts == 1234567890.0
        assert envelope.text is None
        assert envelope.artifact_ids == []
        assert envelope.role == MessageRole.USER
        assert envelope.is_historical is False
        assert envelope.sender_name is None
        assert envelope.sender_username is None
        assert envelope.extra == {}

    def test_inbound_envelope_with_text(self):
        """Test InboundEnvelope with text message."""
        envelope = InboundEnvelope(
            conversation_id="conv-123",
            user_id="user-123",
            text="Hello, World!",
            ts=1234567890.0,
        )
        assert envelope.text == "Hello, World!"

    def test_inbound_envelope_with_audio(self):
        """Test InboundEnvelope with audio attachment."""
        envelope = InboundEnvelope(
            conversation_id="conv-123",
            user_id="user-123",
            ts=1234567890.0,
            artifact_ids=["company_1/voice/test.mp3"],
        )
        assert len(envelope.artifact_ids) == 1
        assert envelope.artifact_ids[0] == "company_1/voice/test.mp3"

    def test_inbound_envelope_with_role(self):
        """Test InboundEnvelope with manager role."""
        envelope = InboundEnvelope(
            conversation_id="conv-123",
            user_id="user-123",
            text="Manager message",
            ts=1234567890.0,
            role=MessageRole.MANAGER,
        )
        assert envelope.role == MessageRole.MANAGER

    def test_inbound_envelope_with_historical_flag(self):
        """Test InboundEnvelope with historical flag for sync messages."""
        envelope = InboundEnvelope(
            conversation_id="conv-123",
            user_id="user-123",
            text="Historical message",
            ts=1234567890.0,
            is_historical=True,
        )
        assert envelope.is_historical is True

    def test_inbound_envelope_with_sender_info(self):
        """Test InboundEnvelope with sender name and username."""
        envelope = InboundEnvelope(
            conversation_id="conv-123",
            user_id="user-123",
            text="Hello",
            ts=1234567890.0,
            sender_name="John Doe",
            sender_username="johndoe",
        )
        assert envelope.sender_name == "John Doe"
        assert envelope.sender_username == "johndoe"

    def test_inbound_envelope_full(self):
        """Test InboundEnvelope with all fields."""
        envelope = InboundEnvelope(
            conversation_id="conv-123",
            user_id="user-123",
            text="Full message",
            ts=1234567890.0,
            artifact_ids=["company_1/voice/audio.mp3", "company_1/image/photo.jpg"],
            role=MessageRole.USER,
            is_historical=False,
            sender_name="Jane Doe",
            sender_username="janedoe",
            extra={"custom_field": "value"},
        )
        assert envelope.conversation_id == "conv-123"
        assert envelope.user_id == "user-123"
        assert envelope.text == "Full message"
        assert envelope.ts == 1234567890.0
        assert len(envelope.artifact_ids) == 2
        assert envelope.artifact_ids[0] == "company_1/voice/audio.mp3"
        assert envelope.artifact_ids[1] == "company_1/image/photo.jpg"
        assert envelope.role == MessageRole.USER
        assert envelope.is_historical is False
        assert envelope.sender_name == "Jane Doe"
        assert envelope.sender_username == "janedoe"
        assert envelope.extra == {"custom_field": "value"}

    def test_inbound_envelope_role_from_string(self):
        """Test InboundEnvelope accepts role as string."""
        envelope = InboundEnvelope(
            conversation_id="conv-123",
            user_id="user-123",
            ts=1234567890.0,
            role="manager",
        )
        assert envelope.role == MessageRole.MANAGER
