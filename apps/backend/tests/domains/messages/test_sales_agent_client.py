"""Tests for SalesAgentClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import SecretStr

from common.models import AgentContext, ConnectorContext, InboundEnvelope, InternalInboundRequest

from src.backend.modules.core.settings import Settings
from src.backend.modules.messages.sales_agent_client import SalesAgentClient, SalesAgentClientError


class TestSalesAgentClient:
    """Tests for SalesAgentClient."""

    @pytest.fixture
    def mock_settings(self) -> Settings:
        """Create mock settings with Sales Agent URL."""
        settings = Settings()
        settings.sales_agent.url = "http://sales-agent:8000"
        settings.service.api_key = SecretStr("test-service-key")  # pragma: allowlist secret
        return settings

    async def test_forward_inbound_success(self, mock_settings: Settings):
        """Test successful inbound message forwarding."""
        client = SalesAgentClient(mock_settings)

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
        agent_context = AgentContext(
            prompt_template="",
            company={},
            customer_answers={},
            history=[],
            enabled_tools=[],
        )
        request = InternalInboundRequest(
            envelope=envelope, context=context, thread_id="test-thread-123", agent_context=agent_context
        )

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 202
            mock_response.raise_for_status = MagicMock()  # raise_for_status is sync
            mock_post.return_value = mock_response

            await client.forward_inbound(request)

            assert mock_post.called
            call_args = mock_post.call_args
            # httpx.post uses positional args: post(url, ...)
            assert call_args.args[0] == "/api/v1/internal/messages/inbound"
            assert "envelope" in call_args.kwargs["json"]
            assert "context" in call_args.kwargs["json"]

    async def test_forward_inbound_http_error(self, mock_settings: Settings):
        """Test forwarding failure with HTTP error."""
        client = SalesAgentClient(mock_settings)

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
        agent_context = AgentContext(
            prompt_template="",
            company={},
            customer_answers={},
            history=[],
            enabled_tools=[],
        )
        request = InternalInboundRequest(
            envelope=envelope, context=context, thread_id="test-thread-123", agent_context=agent_context
        )

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 503
            error = httpx.HTTPStatusError("Service unavailable", request=MagicMock(), response=mock_response)
            mock_response.raise_for_status = MagicMock(side_effect=error)  # raise_for_status is sync
            mock_post.return_value = mock_response

            with pytest.raises(SalesAgentClientError, match="Failed after"):
                await client.forward_inbound(request)

    async def test_forward_inbound_missing_url(self):
        """Test forwarding when Sales Agent URL is not configured."""
        settings = Settings()
        settings.sales_agent.url = None
        settings.service.api_key = "test-key"  # pragma: allowlist secret

        client = SalesAgentClient(settings)

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
        agent_context = AgentContext(
            prompt_template="",
            company={},
            customer_answers={},
            history=[],
            enabled_tools=[],
        )
        request = InternalInboundRequest(
            envelope=envelope, context=context, thread_id="test-thread-123", agent_context=agent_context
        )

        with pytest.raises(SalesAgentClientError, match="Sales Agent URL is not configured"):
            await client.forward_inbound(request)

    async def test_close_clears_client(self, mock_settings: Settings):
        """Test that close() clears HTTP client."""
        client = SalesAgentClient(mock_settings)
        client._get_client()  # pragma: allowlist secret
        assert client._client is not None

        await client.close()
        assert client._client is None

    async def test_get_client_includes_service_key_header(self, mock_settings: Settings):
        """Test that HTTP client includes service key header."""
        client = SalesAgentClient(mock_settings)
        http_client = client._get_client()

        assert http_client.headers.get("X-Service-Key") == "test-service-key"  # pragma: allowlist secret
