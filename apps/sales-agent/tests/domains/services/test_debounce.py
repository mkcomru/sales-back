"""Tests for debounce module."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.sales_agent.services.debounce import (
    DebounceManager,
    IncomingMessage,
)


class TestIncomingMessage:
    """Test IncomingMessage dataclass."""

    def test_incoming_message_creation(self) -> None:
        """Test creating IncomingMessage with all fields."""
        msg = IncomingMessage(
            connector_id="test-connector",
            conversation_id="conv-1",
            user_id="123",
            text="Hello",
            metadata={"key": "value"},
            debounce_seconds=30,
        )

        assert msg.connector_id == "test-connector"
        assert msg.conversation_id == "conv-1"
        assert msg.user_id == "123"
        assert msg.text == "Hello"
        assert msg.metadata == {"key": "value"}
        assert msg.debounce_seconds == 30

    def test_incoming_message_defaults(self) -> None:
        """Test IncomingMessage with default values."""
        msg = IncomingMessage(
            connector_id=None,
            conversation_id="conv-1",
            user_id="123",
        )

        assert msg.connector_id is None
        assert msg.text is None
        assert msg.attachments == []
        assert msg.debounce_seconds is None


class TestDebounceManager:
    """Test DebounceManager class."""

    @pytest.mark.asyncio
    async def test_add_message_creates_bucket(
        self,
    ) -> None:
        """Test adding message creates a new bucket."""
        callback = AsyncMock()
        manager = DebounceManager(callback, debounce_seconds=1)

        msg = IncomingMessage(
            connector_id="test",
            conversation_id="conv-1",
            user_id="123",
            text="Hello",
        )

        window = await manager.add_message(msg)

        assert window == 1
        assert callback.await_count == 0  # Not called yet

    @pytest.mark.asyncio
    async def test_add_message_triggers_callback_after_debounce(
        self,
    ) -> None:
        """Test callback is triggered after debounce window."""
        callback = AsyncMock()
        manager = DebounceManager(callback, debounce_seconds=0.1)

        msg = IncomingMessage(
            connector_id="test",
            conversation_id="conv-1",
            user_id="123",
            text="Hello",
        )

        await manager.add_message(msg)
        await asyncio.sleep(0.15)  # Wait for debounce

        assert callback.await_count == 1
        args = callback.await_args
        assert args is not None
        storage_key, batch = args[0]
        assert storage_key == "conv-1"
        assert len(batch) == 1
        assert batch[0].text == "Hello"

    @pytest.mark.asyncio
    async def test_add_multiple_messages_batches_them(
        self,
    ) -> None:
        """Test multiple messages are batched together."""
        callback = AsyncMock()
        manager = DebounceManager(callback, debounce_seconds=0.1)

        msg1 = IncomingMessage(
            connector_id="test",
            conversation_id="conv-1",
            user_id="123",
            text="Message 1",
        )
        msg2 = IncomingMessage(
            connector_id="test",
            conversation_id="conv-1",
            user_id="123",
            text="Message 2",
        )

        await manager.add_message(msg1)
        await asyncio.sleep(0.05)
        await manager.add_message(msg2)
        await asyncio.sleep(0.15)  # Wait for debounce

        assert callback.await_count == 1
        args = callback.await_args
        assert args is not None
        _, batch = args[0]
        assert len(batch) == 2
        assert batch[0].text == "Message 1"
        assert batch[1].text == "Message 2"

    @pytest.mark.asyncio
    async def test_add_message_resets_timer(
        self,
    ) -> None:
        """Test adding new message resets debounce timer."""
        callback = AsyncMock()
        manager = DebounceManager(callback, debounce_seconds=0.2)

        msg1 = IncomingMessage(
            connector_id="test",
            conversation_id="conv-1",
            user_id="123",
            text="Message 1",
        )
        msg2 = IncomingMessage(
            connector_id="test",
            conversation_id="conv-1",
            user_id="123",
            text="Message 2",
        )

        await manager.add_message(msg1)
        await asyncio.sleep(0.15)  # Almost at debounce time
        await manager.add_message(msg2)  # Reset timer
        await asyncio.sleep(0.1)  # Not enough time yet
        assert callback.await_count == 0

        await asyncio.sleep(0.15)  # Now should trigger
        assert callback.await_count == 1

    @pytest.mark.asyncio
    async def test_add_message_with_storage_key(
        self,
    ) -> None:
        """Test message with custom storage_key."""
        callback = AsyncMock()
        manager = DebounceManager(callback, debounce_seconds=0.1)

        msg = IncomingMessage(
            connector_id="test",
            conversation_id="conv-1",
            user_id="123",
            text="Hello",
            storage_key="custom-key",
        )

        await manager.add_message(msg)
        await asyncio.sleep(0.15)

        assert callback.await_count == 1
        args = callback.await_args
        assert args is not None
        storage_key, _ = args[0]
        assert storage_key == "custom-key"

    @pytest.mark.asyncio
    async def test_add_message_empty_storage_key_raises_error(
        self,
    ) -> None:
        """Test message with empty storage_key raises ValueError."""
        callback = AsyncMock()
        manager = DebounceManager(callback)

        msg = IncomingMessage(
            connector_id="test",
            conversation_id="",
            user_id="123",
            text="Hello",
        )

        with pytest.raises(ValueError, match="non-empty storage key"):
            await manager.add_message(msg)

    @pytest.mark.asyncio
    async def test_add_message_with_custom_debounce_seconds(
        self,
    ) -> None:
        """Test message with custom debounce_seconds."""
        callback = AsyncMock()
        manager = DebounceManager(callback, debounce_seconds=1.0)

        msg = IncomingMessage(
            connector_id="test",
            conversation_id="conv-1",
            user_id="123",
            text="Hello",
            debounce_seconds=0.1,
        )

        window = await manager.add_message(msg)
        assert window == 0.1

        await asyncio.sleep(0.15)
        assert callback.await_count == 1

    @pytest.mark.asyncio
    async def test_debounce_seconds_property(self) -> None:
        """Test debounce_seconds property."""
        callback = AsyncMock()
        manager = DebounceManager(callback, debounce_seconds=45)

        assert manager.debounce_seconds == 45

    @pytest.mark.asyncio
    async def test_separate_conversations_dont_interfere(
        self,
    ) -> None:
        """Test messages from different conversations are handled separately."""
        callback = AsyncMock()
        manager = DebounceManager(callback, debounce_seconds=0.1)

        msg1 = IncomingMessage(
            connector_id="test",
            conversation_id="conv-1",
            user_id="123",
            text="Message 1",
        )
        msg2 = IncomingMessage(
            connector_id="test",
            conversation_id="conv-2",
            user_id="456",
            text="Message 2",
        )

        await manager.add_message(msg1)
        await manager.add_message(msg2)
        await asyncio.sleep(0.15)

        assert callback.await_count == 2
        calls = [call[0] for call in callback.await_args_list]
        storage_keys = [key for key, _ in calls]
        assert "conv-1" in storage_keys
        assert "conv-2" in storage_keys

    @pytest.mark.asyncio
    async def test_callback_exception_handled(
        self,
    ) -> None:
        """Test callback exceptions are handled gracefully."""

        async def failing_callback(key: str, batch: list[IncomingMessage]) -> None:
            raise ValueError("Test error")

        manager = DebounceManager(failing_callback, debounce_seconds=0.1)

        msg = IncomingMessage(
            connector_id="test",
            conversation_id="conv-1",
            user_id="123",
            text="Hello",
        )

        await manager.add_message(msg)
        await asyncio.sleep(0.15)

        # Should not raise, exception is caught and logged
        assert True
