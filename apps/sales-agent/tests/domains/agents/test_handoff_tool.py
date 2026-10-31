"""Integration tests for handoff_commit tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from common import SalesAgentSettings
from common.models.io import SimpleChat, SimpleMessage, SimpleUser

from src.sales_agent.agents.tools import HandoffSummary, handoff_commit


class TestHandoffCommit:
    """Test handoff_commit function."""

    @pytest.mark.asyncio
    async def test_handoff_commit_calls_backend(self, settings: SalesAgentSettings) -> None:
        """Test that handoff_commit notifies backend."""
        message = SimpleMessage(
            text="Hello",
            from_user=SimpleUser(id=123),
            chat=SimpleChat(id=456),
            message_id=789,
            metadata={
                "company_id": 1,
                "channel_type": "telegram",
                "conversation_id": "conv123",
                "thread_id": "thread_abc123",
                "order_id": 42,
            },
        )

        mock_backend_client = AsyncMock()
        mock_backend_client.request_handoff = AsyncMock(
            return_value={
                "thread_id": "thread_abc123",
                "state": "handoff",
                "assistant_mode": "shadowing",
                "message_id": "msg_456",
            }
        )

        with patch("src.sales_agent.agents.tools.get_backend_client", return_value=mock_backend_client):
            with patch("src.sales_agent.agents.tools.update_customer_fields", new=AsyncMock()):
                with patch("src.sales_agent.agents.tools.notify_handoff", new=AsyncMock()):
                    result = await handoff_commit(
                        settings=settings,
                        user_id="user123",
                        summary={"text": "Customer needs expert help"},
                        reason="complex_question",
                        message=message,
                    )

        assert isinstance(result, HandoffSummary)
        assert result.text == "Customer needs expert help"
        assert result.reason == "complex_question"

        mock_backend_client.request_handoff.assert_called_once_with(
            order_id=42,
            summary="Customer needs expert help",
            reason="complex_question",
            escalate=False,
        )

    @pytest.mark.asyncio
    async def test_handoff_commit_handles_backend_error(self, settings: SalesAgentSettings) -> None:
        """Test that handoff_commit continues even if backend notification fails."""
        message = SimpleMessage(
            text="Hello",
            from_user=SimpleUser(id=123),
            chat=SimpleChat(id=456),
            message_id=789,
            metadata={
                "company_id": 1,
                "channel_type": "telegram",
                "conversation_id": "conv123",
            },
        )

        mock_backend_client = AsyncMock()
        mock_backend_client.get_or_create_thread = AsyncMock(side_effect=Exception("Backend unavailable"))

        with patch("src.sales_agent.agents.tools.get_backend_client", return_value=mock_backend_client):
            with patch("src.sales_agent.agents.tools.update_customer_fields", new=AsyncMock()):
                with patch("src.sales_agent.agents.tools.notify_handoff", new=AsyncMock()) as mock_crm_notify:
                    result = await handoff_commit(
                        settings=settings,
                        user_id="user123",
                        summary={"text": "Test summary"},
                        reason="test_reason",
                        message=message,
                    )

        # Should still return result
        assert isinstance(result, HandoffSummary)
        assert result.text == "Test summary"

        # CRM notification should still be called
        mock_crm_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_handoff_commit_saves_to_customer_fields(self, settings: SalesAgentSettings) -> None:
        """Test that handoff_commit saves summary to customer fields."""
        message = SimpleMessage(
            text="Hello",
            from_user=SimpleUser(id=123),
            chat=SimpleChat(id=456),
            message_id=789,
            metadata={
                "company_id": 1,
                "channel_type": "telegram",
            },
        )

        mock_update_fields = AsyncMock()

        with patch("src.sales_agent.agents.tools.get_backend_client", return_value=AsyncMock()):
            with patch("src.sales_agent.agents.tools.update_customer_fields", new=mock_update_fields):
                with patch("src.sales_agent.agents.tools.notify_handoff", new=AsyncMock()):
                    await handoff_commit(
                        settings=settings,
                        user_id="user123",
                        summary={"text": "Summary text"},
                        reason="user_request",
                        message=message,
                    )

        # Verify customer fields were updated
        mock_update_fields.assert_called_once()
        call_args = mock_update_fields.call_args
        assert call_args[0][0] == "user123"  # user_id
        assert call_args[0][1] == 1  # company_id
        assert "handoff_summary" in call_args[0][2]
        assert call_args[0][2]["handoff_summary"]["text"] == "Summary text"
        assert call_args[0][2]["handoff_summary"]["reason"] == "user_request"

    @pytest.mark.asyncio
    async def test_handoff_commit_without_escalate(self, settings: SalesAgentSettings) -> None:
        """Test handoff_commit passes escalate=False to backend request_handoff."""
        message = SimpleMessage(
            text="Hello",
            from_user=SimpleUser(id=123),
            chat=SimpleChat(id=456),
            message_id=789,
            metadata={
                "company_id": 1,
                "channel_type": "telegram",
                "thread_id": "thread_123",
                "order_id": 99,
            },
        )

        mock_backend_client = AsyncMock()
        mock_backend_client.request_handoff = AsyncMock()

        with patch("src.sales_agent.agents.tools.get_backend_client", return_value=mock_backend_client):
            with patch("src.sales_agent.agents.tools.update_customer_fields", new=AsyncMock()):
                with patch("src.sales_agent.agents.tools.notify_handoff", new=AsyncMock()):
                    await handoff_commit(
                        settings=settings,
                        user_id="user123",
                        summary={"text": "Test"},
                        reason="test",
                        message=message,
                    )

        assert mock_backend_client.request_handoff.called
        call_kwargs = mock_backend_client.request_handoff.call_args.kwargs
        assert call_kwargs["escalate"] is False

    @pytest.mark.asyncio
    async def test_handoff_commit_requires_company_id(self, settings: SalesAgentSettings) -> None:
        """Test that handoff_commit raises error without company_id."""
        message = SimpleMessage(
            text="Hello",
            from_user=SimpleUser(id=123),
            chat=SimpleChat(id=456),
            message_id=789,
            metadata={},  # Missing company_id
        )

        with pytest.raises(ValueError, match="company_id is required"):
            await handoff_commit(
                settings=settings,
                user_id="user123",
                summary={"text": "Test"},
                reason="test",
                message=message,
            )

    @pytest.mark.asyncio
    async def test_handoff_commit_merges_all_fields(self, settings: SalesAgentSettings) -> None:
        """Test that handoff_commit properly merges all provided fields."""
        message = SimpleMessage(
            text="Hello",
            from_user=SimpleUser(id=123),
            chat=SimpleChat(id=456),
            message_id=789,
            metadata={"company_id": 1, "channel_type": "whatsapp"},
        )

        mock_update_fields = AsyncMock()

        with patch("src.sales_agent.agents.tools.get_backend_client", return_value=AsyncMock()):
            with patch("src.sales_agent.agents.tools.update_customer_fields", new=mock_update_fields):
                with patch("src.sales_agent.agents.tools.notify_handoff", new=AsyncMock()):
                    result = await handoff_commit(
                        settings=settings,
                        user_id="user123",
                        summary={"text": "Original summary"},
                        reason="original_reason",
                        message=message,
                    )

        # Check final result has all fields
        assert result.text == "Original summary"
        assert result.reason == "original_reason"

        # Verify saved to customer fields
        call_args = mock_update_fields.call_args
        saved_summary = call_args[0][2]["handoff_summary"]
        assert saved_summary["text"] == "Original summary"
        assert saved_summary["reason"] == "original_reason"
