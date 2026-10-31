"""Tests for BackendClient.request_handoff (042: unified handoff, notify_handoff removed)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from pydantic import SecretStr

from common import SalesAgentSettings

from src.sales_agent.services.backend_client import BackendClient


class TestRequestHandoff:
    """POST /internal/orders/{order_id}/handoff — unified handoff endpoint."""

    @pytest.mark.asyncio
    async def test_request_handoff_success(self, settings: SalesAgentSettings) -> None:
        settings.backend.url = "http://localhost:8001"
        settings.service.api_key = SecretStr("test-service-key")
        client = BackendClient(settings)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "manager": {"id": 1, "name": "Test Manager", "timezone": "UTC"},
            "availability": {
                "is_working_now": True,
                "next_available_at": None,
                "next_available_at_local": None,
                "next_available_timezone": None,
                "schedule_description": None,
            },
            "message_hint": "ok",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        client._chat_client = mock_client

        result = await client.request_handoff(
            order_id=99,
            summary="Need human",
            reason="escalation",
        )

        assert result["success"] is True
        assert result["manager"]["id"] == 1

        mock_client.post.assert_called_once_with(
            "/internal/orders/99/handoff",
            json={"summary": "Need human", "reason": "escalation", "escalate": False},
        )

    @pytest.mark.asyncio
    async def test_request_handoff_with_escalate(self, settings: SalesAgentSettings) -> None:
        settings.backend.url = "http://localhost:8001"
        settings.service.api_key = SecretStr("test-service-key")
        client = BackendClient(settings)

        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True, "manager": None}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        client._chat_client = mock_client

        await client.request_handoff(
            order_id=42,
            summary="Urgent escalation",
            reason="angry_customer",
            escalate=True,
        )

        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        assert payload["escalate"] is True

    @pytest.mark.asyncio
    async def test_request_handoff_http_error(self, settings: SalesAgentSettings) -> None:
        settings.backend.url = "http://localhost:8001"
        settings.service.api_key = SecretStr("test-service-key")
        client = BackendClient(settings)

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not found", request=MagicMock(), response=mock_response
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        client._chat_client = mock_client

        with pytest.raises(httpx.HTTPStatusError):
            await client.request_handoff(order_id=99999, summary="x", reason="y")

    @pytest.mark.asyncio
    async def test_request_handoff_uses_chat_client(self, settings: SalesAgentSettings) -> None:
        settings.backend.url = "http://localhost:8001"
        settings.service.api_key = SecretStr("my-secret-key")
        client = BackendClient(settings)

        chat_client = client._get_chat_client()
        assert chat_client is not None
        assert client._service_key is not None

        await client.close_chat_client()

    @pytest.mark.asyncio
    async def test_request_handoff_constructs_correct_url(self, settings: SalesAgentSettings) -> None:
        settings.backend.url = "http://localhost:8001"
        settings.service.api_key = SecretStr("test-key")
        client = BackendClient(settings)

        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        client._chat_client = mock_client

        await client.request_handoff(order_id=777, summary="Test", reason="test")

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/internal/orders/777/handoff"

    @pytest.mark.asyncio
    async def test_request_handoff_includes_all_fields(self, settings: SalesAgentSettings) -> None:
        settings.backend.url = "http://localhost:8001"
        settings.service.api_key = SecretStr("test-key")
        client = BackendClient(settings)

        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        client._chat_client = mock_client

        await client.request_handoff(
            order_id=123,
            summary="Very detailed summary of the conversation",
            reason="escalation_needed",
            escalate=True,
        )

        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]

        assert payload["summary"] == "Very detailed summary of the conversation"
        assert payload["reason"] == "escalation_needed"
        assert payload["escalate"] is True
