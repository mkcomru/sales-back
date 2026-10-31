"""Tests for close_order tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.sales_agent.agents.tools import CloseOrderResponse, close_order


class TestCloseOrderTool:
    """Test close_order function."""

    @pytest.mark.asyncio
    async def test_close_order_won(self) -> None:
        """Test closing order with won result."""
        mock_backend_client = AsyncMock()
        mock_backend_client.close_order = AsyncMock(
            return_value={
                "id": 123,
                "result": "won",
                "closed_at": "2026-01-23T12:00:00Z",
                "stage": {"id": 5, "name": "Закрыто"},
            }
        )

        with patch("src.sales_agent.agents.tools.get_backend_client", return_value=mock_backend_client):
            result = await close_order(
                order_id=123,
                result="won",
                reason="deal completed successfully",
            )

        assert isinstance(result, CloseOrderResponse)
        assert result.order_id == 123
        assert result.result == "won"
        assert result.closed is True
        assert "won" in result.message
        assert "deal completed successfully" in result.message

        mock_backend_client.close_order.assert_called_once_with(
            order_id=123,
            result="won",
        )

    @pytest.mark.asyncio
    async def test_close_order_lost(self) -> None:
        """Test closing order with lost result."""
        mock_backend_client = AsyncMock()
        mock_backend_client.close_order = AsyncMock(
            return_value={
                "id": 456,
                "result": "lost",
                "closed_at": "2026-01-23T12:00:00Z",
                "stage": {"id": 5, "name": "Закрыто"},
            }
        )

        with patch("src.sales_agent.agents.tools.get_backend_client", return_value=mock_backend_client):
            result = await close_order(
                order_id=456,
                result="lost",
                reason="customer refused",
            )

        assert isinstance(result, CloseOrderResponse)
        assert result.order_id == 456
        assert result.result == "lost"
        assert result.closed is True
        assert "lost" in result.message
        assert "customer refused" in result.message

        mock_backend_client.close_order.assert_called_once_with(
            order_id=456,
            result="lost",
        )

    @pytest.mark.asyncio
    async def test_close_order_without_reason(self) -> None:
        """Test closing order without reason."""
        mock_backend_client = AsyncMock()
        mock_backend_client.close_order = AsyncMock(
            return_value={
                "id": 789,
                "result": "won",
                "closed_at": "2026-01-23T12:00:00Z",
                "stage": {"id": 5, "name": "Закрыто"},
            }
        )

        with patch("src.sales_agent.agents.tools.get_backend_client", return_value=mock_backend_client):
            result = await close_order(
                order_id=789,
                result="won",
            )

        assert isinstance(result, CloseOrderResponse)
        assert result.order_id == 789
        assert result.result == "won"
        assert result.closed is True
        assert result.message == "Order closed as won"

    @pytest.mark.asyncio
    async def test_close_order_invalid_result(self) -> None:
        """Test that invalid result raises ValueError."""
        with pytest.raises(ValueError, match="Invalid result"):
            await close_order(
                order_id=123,
                result="invalid",  # type: ignore[arg-type]
            )

    @pytest.mark.asyncio
    async def test_close_order_backend_error(self) -> None:
        """Test that backend errors are propagated."""
        mock_backend_client = AsyncMock()
        mock_backend_client.close_order = AsyncMock(side_effect=Exception("Backend error"))

        with patch("src.sales_agent.agents.tools.get_backend_client", return_value=mock_backend_client):
            with pytest.raises(Exception, match="Backend error"):
                await close_order(
                    order_id=123,
                    result="won",
                )
