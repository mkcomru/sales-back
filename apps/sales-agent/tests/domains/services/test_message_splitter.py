"""Tests for message_splitter module."""

from __future__ import annotations

from src.sales_agent.services.message_splitter import (
    CHARS_PER_SECOND,
    MIN_DELAY_SECONDS,
    calculate_delay,
    remove_trailing_dots,
    split_and_calculate_delays,
    split_message,
)


class TestRemoveTrailingDots:
    """Test remove_trailing_dots function."""

    def test_remove_single_trailing_dot(self) -> None:
        """Test single trailing dot is removed."""
        result = remove_trailing_dots("Hello world.")
        assert result == "Hello world"

    def test_keep_ellipsis(self) -> None:
        """Test ellipsis is preserved."""
        result = remove_trailing_dots("Wait...")
        assert result == "Wait..."

    def test_keep_exclamation(self) -> None:
        """Test exclamation mark is preserved."""
        result = remove_trailing_dots("Hello!")
        assert result == "Hello!"

    def test_keep_question(self) -> None:
        """Test question mark is preserved."""
        result = remove_trailing_dots("How are you?")
        assert result == "How are you?"

    def test_no_trailing_dot(self) -> None:
        """Test text without trailing dot is unchanged."""
        result = remove_trailing_dots("Hello world")
        assert result == "Hello world"

    def test_empty_string(self) -> None:
        """Test empty string is returned as-is."""
        result = remove_trailing_dots("")
        assert result == ""

    def test_whitespace_only(self) -> None:
        """Test whitespace-only string is stripped."""
        result = remove_trailing_dots("   ")
        assert result == ""


class TestSplitMessage:
    """Test split_message function."""

    def test_split_by_double_newline(self) -> None:
        """Test message is split by double newlines."""
        text = "First paragraph\n\nSecond paragraph\n\nThird paragraph"
        result = split_message(text)
        assert len(result) == 3
        assert result[0] == "First paragraph"
        assert result[1] == "Second paragraph"
        assert result[2] == "Third paragraph"

    def test_single_paragraph(self) -> None:
        """Test single paragraph returns single chunk."""
        text = "Single paragraph text"
        result = split_message(text)
        assert len(result) == 1
        assert result[0] == "Single paragraph text"

    def test_empty_string(self) -> None:
        """Test empty string returns empty list."""
        result = split_message("")
        assert result == []

    def test_whitespace_only(self) -> None:
        """Test whitespace-only string returns empty list."""
        result = split_message("   ")
        assert result == []

    def test_strips_chunks(self) -> None:
        """Test chunks are stripped of whitespace."""
        text = "  First  \n\n  Second  "
        result = split_message(text)
        assert result[0] == "First"
        assert result[1] == "Second"

    def test_single_newline_not_split(self) -> None:
        """Test single newline doesn't split message."""
        text = "Line 1\nLine 2"
        result = split_message(text)
        assert len(result) == 1
        assert result[0] == "Line 1\nLine 2"


class TestCalculateDelay:
    """Test calculate_delay function."""

    def test_calculate_delay_based_on_length(self) -> None:
        """Test delay is calculated based on chunk length."""
        chunk = "a" * (CHARS_PER_SECOND * 2)  # 2 seconds worth
        delay = calculate_delay(chunk)
        assert delay == 2.0

    def test_calculate_delay_minimum(self) -> None:
        """Test delay is at least MIN_DELAY_SECONDS."""
        chunk = "a"  # Very short
        delay = calculate_delay(chunk)
        assert delay == MIN_DELAY_SECONDS

    def test_calculate_delay_long_message(self) -> None:
        """Test delay for long message."""
        chunk = "a" * (CHARS_PER_SECOND * 10)  # 10 seconds worth
        delay = calculate_delay(chunk)
        assert delay == 10.0

    def test_calculate_delay_empty_string(self) -> None:
        """Test delay for empty string is minimum."""
        delay = calculate_delay("")
        assert delay == MIN_DELAY_SECONDS


class TestSplitAndCalculateDelays:
    """Test split_and_calculate_delays function."""

    def test_split_and_calculate_delays_success(self) -> None:
        """Test successful split and delay calculation."""
        text = "First paragraph.\n\nSecond paragraph."
        chunks, delays = split_and_calculate_delays(text)

        assert len(chunks) == 2
        assert len(delays) == 2
        assert chunks[0] == "First paragraph."
        assert chunks[1] == "Second paragraph."
        assert all(d >= MIN_DELAY_SECONDS for d in delays)

    def test_split_and_calculate_delays_single_chunk(self) -> None:
        """Test single chunk message."""
        text = "Single paragraph."
        chunks, delays = split_and_calculate_delays(text)

        assert len(chunks) == 1
        assert len(delays) == 1
        assert chunks[0] == "Single paragraph."
        assert delays[0] >= MIN_DELAY_SECONDS

    def test_split_and_calculate_delays_empty(self) -> None:
        """Test empty message returns empty lists."""
        chunks, delays = split_and_calculate_delays("")
        assert chunks == []
        assert delays == []

    def test_split_and_calculate_delays_preserves_trailing_dots(self) -> None:
        """Test trailing dots are preserved (sanitized downstream)."""
        text = "First.\n\nSecond.\n\nThird."
        chunks, delays = split_and_calculate_delays(text)

        assert all(chunk.endswith(".") for chunk in chunks)
        assert len(chunks) == 3

    def test_split_and_calculate_delays_preserves_ellipsis(self) -> None:
        """Test ellipsis is preserved."""
        text = "Wait...\n\nContinue."
        chunks, delays = split_and_calculate_delays(text)

        assert "..." in chunks[0]
        assert chunks[1] == "Continue."

    def test_split_and_calculate_delays_delay_proportional_to_length(self) -> None:
        """Test delays are proportional to chunk lengths."""
        text = "Short.\n\n" + "a" * 100 + "."
        chunks, delays = split_and_calculate_delays(text)

        assert delays[1] > delays[0]
