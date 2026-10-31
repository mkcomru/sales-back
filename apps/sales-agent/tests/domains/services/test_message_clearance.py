"""Tests for outbound message clearance."""

from src.sales_agent.services.message_processor import _apply_message_clearance


class TestApplyMessageClearance:
    """Ensure outbound clearance sanitizes content."""

    def test_removes_asterisks_and_trailing_dot(self) -> None:
        result = _apply_message_clearance("*Hello.*")
        assert result == "Hello"

    def test_preserves_ellipsis(self) -> None:
        result = _apply_message_clearance("Wait...")
        assert result == "Wait..."

    def test_no_change_when_clean(self) -> None:
        text = "Already clean!"
        result = _apply_message_clearance(text)
        assert result == text
