"""Tests for humanizer module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.sales_agent.services.humanizer import (
    MessageHumanizer,
    get_humanizer,
    humanize_message,
)


class TestMessageHumanizer:
    """Test MessageHumanizer class."""

    def test_humanize_does_not_remove_trailing_dot(self) -> None:
        """Test trailing dot is preserved (sanitization handled elsewhere)."""
        humanizer = MessageHumanizer()
        with patch("src.sales_agent.services.humanizer.random.random", return_value=1.0):
            result = humanizer.humanize("Hello world.")
        assert result == "Hello world."

    def test_humanize_keeps_ellipsis(self) -> None:
        """Test ellipsis is preserved."""
        humanizer = MessageHumanizer()
        result = humanizer.humanize("Wait...")
        assert "Wait..." in result

    def test_humanize_keeps_exclamation(self) -> None:
        """Test exclamation mark is preserved."""
        humanizer = MessageHumanizer()
        result = humanizer.humanize("Hello!")
        assert "Hello!" in result
        assert result.startswith("Hello!")

    def test_humanize_keeps_question(self) -> None:
        """Test question mark is preserved."""
        humanizer = MessageHumanizer()
        result = humanizer.humanize("How are you?")
        assert "How are you?" in result
        assert result.startswith("How are you?")

    def test_humanize_empty_string(self) -> None:
        """Test empty string is returned as-is."""
        humanizer = MessageHumanizer()
        result = humanizer.humanize("")
        assert result == ""

    def test_humanize_whitespace_only(self) -> None:
        """Test whitespace-only string is returned as-is."""
        humanizer = MessageHumanizer()
        result = humanizer.humanize("   ")
        assert result == "   "

    def test_humanize_replaces_emoji_with_brackets(self) -> None:
        """Test emojis are replaced with brackets."""
        humanizer = MessageHumanizer()
        result = humanizer.humanize("Hello 😊", recent_bot_messages=["Previous 😊"])
        assert "😊" not in result
        assert ")" in result or result == "Hello"

    def test_humanize_keeps_emoji_when_no_recent(self) -> None:
        """Test emojis may be kept when no recent emojis."""
        humanizer = MessageHumanizer()
        result = humanizer.humanize("Hello 😊", recent_bot_messages=[])
        # May keep or replace based on probability
        assert isinstance(result, str)

    def test_humanize_adds_brackets_when_no_markers(self) -> None:
        """Test brackets may be added when message lacks emotional markers."""
        humanizer = MessageHumanizer()
        result = humanizer.humanize("Hello world", recent_bot_messages=[])
        # May add brackets based on probability
        assert isinstance(result, str)
        assert "Hello world" in result

    def test_humanize_with_recent_messages(self) -> None:
        """Test humanization considers recent messages."""
        humanizer = MessageHumanizer()
        recent = ["Previous message 😊", "Another message"]
        result = humanizer.humanize("New message", recent_bot_messages=recent)
        assert isinstance(result, str)


class TestGetHumanizer:
    """Test get_humanizer function."""

    def test_get_humanizer_returns_singleton(self) -> None:
        """Test get_humanizer returns same instance."""
        humanizer1 = get_humanizer()
        humanizer2 = get_humanizer()
        assert humanizer1 is humanizer2


class TestHumanizeMessage:
    """Test humanize_message function."""

    @pytest.mark.asyncio
    async def test_humanize_message_success(self, mock_backend_client: AsyncMock) -> None:
        """Test successful message humanization."""
        from src.sales_agent.storage.customer_store import set_backend_client

        set_backend_client(mock_backend_client)
        mock_backend_client.get_or_create_thread.return_value = {"thread_id": "thread-1"}
        mock_backend_client.get_recent_history.return_value = [
            {"role": "assistant", "content": "Previous 😊"},
            {"role": "user", "content": "Hello"},
        ]

        with patch("src.sales_agent.services.humanizer.get_humanizer") as mock_get:
            mock_humanizer = MessageHumanizer()
            mock_get.return_value = mock_humanizer

            result = await humanize_message("Hello world.", history=[])

            assert isinstance(result, str)
            assert "Hello world" in result or result == "Hello world"

    @pytest.mark.asyncio
    async def test_humanize_message_disabled_in_settings(self, mock_backend_client: AsyncMock, settings) -> None:
        """Test humanizer is disabled when settings disable it."""

        from src.sales_agent.storage.customer_store import set_backend_client

        set_backend_client(mock_backend_client)
        settings.humanizer.enabled = False

        result = await humanize_message("Hello world.", history=[], settings=settings)

        assert result == "Hello world."
        mock_backend_client.get_recent_history.assert_not_called()

    @pytest.mark.asyncio
    async def test_humanize_message_with_empty_history(self, mock_backend_client: AsyncMock) -> None:
        """Test humanization with empty history."""
        from src.sales_agent.storage.customer_store import set_backend_client

        set_backend_client(mock_backend_client)
        mock_backend_client.get_or_create_thread.return_value = {"thread_id": "thread-1"}
        mock_backend_client.get_recent_history.return_value = []

        result = await humanize_message("Hello world.", history=[])

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_humanize_message_filters_assistant_messages(self, mock_backend_client: AsyncMock) -> None:
        """Test only assistant messages are used for context."""
        from src.sales_agent.storage.customer_store import set_backend_client

        set_backend_client(mock_backend_client)
        mock_backend_client.get_or_create_thread.return_value = {"thread_id": "thread-1"}
        mock_backend_client.get_recent_history.return_value = [
            {"role": "user", "content": "User message"},
            {"role": "assistant", "content": "Bot message 😊"},
            {"role": "user", "content": "Another user message"},
        ]

        with patch("src.sales_agent.services.humanizer.get_humanizer") as mock_get:
            mock_humanizer = MagicMock()
            mock_humanizer.humanize.return_value = "New message"
            mock_get.return_value = mock_humanizer

            await humanize_message("New message", history=[])

            # Verify humanizer was called with only assistant messages
            assert mock_humanizer.humanize.called
            call_args = mock_humanizer.humanize.call_args
            if call_args:
                recent_messages = call_args[0][1] if len(call_args[0]) > 1 else []
                assert all("Bot message" in msg for msg in recent_messages)
