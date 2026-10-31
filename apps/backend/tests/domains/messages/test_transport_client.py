"""Tests for TransportClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import SecretStr

from src.backend.modules.core.settings import Settings
from src.backend.modules.messages.transport_client import TransportClient, TransportClientError
from src.backend.modules.transport.models import ConnectorType


class TestTransportClient:
    """Tests for TransportClient."""

    @pytest.fixture
    def mock_settings(self) -> Settings:
        """Create mock settings with transport URLs."""
        settings = Settings()
        # Mock transport settings
        settings.transport.telegram.url = "http://telegram-module:8001"
        settings.transport.wappi.url = "http://wappi-module:8002"
        settings.service.api_key = SecretStr("test-service-key")  # pragma: allowlist secret
        return settings

    async def test_resolve_endpoint_telegram(self, mock_settings: Settings):
        """Test endpoint resolution for Telegram connector."""
        client = TransportClient(mock_settings)
        endpoint = client._resolve_endpoint("telegram")
        assert endpoint == "http://telegram-module:8001"

    async def test_resolve_endpoint_wappi(self, mock_settings: Settings):
        """Test endpoint resolution for Wappi connector."""
        client = TransportClient(mock_settings)
        endpoint = client._resolve_endpoint("wappi")
        assert endpoint == "http://wappi-module:8002"

    async def test_resolve_endpoint_unknown(self, mock_settings: Settings):
        """Test endpoint resolution for unknown connector type."""
        client = TransportClient(mock_settings)
        with pytest.raises(TransportClientError, match="Unknown connector type"):
            client._resolve_endpoint("unknown")

    async def test_resolve_endpoint_not_configured(self):
        """Test endpoint resolution when URL is not configured."""
        settings = Settings()
        settings.transport.telegram.url = None
        settings.service.api_key = "test-key"  # pragma: allowlist secret

        client = TransportClient(settings)
        with pytest.raises(TransportClientError, match="not configured"):
            client._resolve_endpoint("telegram")

    async def test_get_client_creates_new(self, mock_settings: Settings):
        """Test that _get_client creates a new HTTP client."""
        client = TransportClient(mock_settings)
        http_client = client._get_client("http://test:8000")
        assert http_client is not None
        assert isinstance(http_client, httpx.AsyncClient)

    async def test_get_client_reuses_existing(self, mock_settings: Settings):
        """Test that _get_client reuses existing HTTP client for same endpoint."""
        client = TransportClient(mock_settings)
        endpoint = "http://test:8000"
        client1 = client._get_client(endpoint)
        client2 = client._get_client(endpoint)
        assert client1 is client2

    async def test_deliver_success(
        self,
        mock_settings: Settings,
    ):
        """Test successful message delivery."""
        client = TransportClient(mock_settings)

        payload = {
            "connector_id": "tg-bot-123",
            "conversation_id": "conv-123",
            "correlation_id": "corr-123",
            "replies": ["Hello"],
            "metadata": {},
        }

        connector = MagicMock()
        connector.connector_id = "tg-bot-123"
        connector.type = ConnectorType.TELEGRAM
        connector.channel_type = "telegram"
        connector.config = {}

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()  # raise_for_status is sync
            mock_post.return_value = mock_response

            await client.deliver(connector=connector, payload=payload)

            assert mock_post.called
            call_args = mock_post.call_args
            # httpx.post uses positional args: post(url, ...)
            assert call_args.args[0] == "/transport/delivery"
            assert call_args.kwargs["json"] == payload
            assert call_args.kwargs["headers"]["X-Connector-Id"] == "tg-bot-123"

    async def test_deliver_http_error(
        self,
        mock_settings: Settings,
    ):
        """Test delivery failure with HTTP error."""
        client = TransportClient(mock_settings)

        payload = {
            "connector_id": "tg-bot-123",
            "conversation_id": "conv-123",
            "correlation_id": "corr-123",
            "replies": ["Hello"],
            "metadata": {},
        }

        with patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock) as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 500
            error = httpx.HTTPStatusError("Server error", request=MagicMock(), response=mock_response)
            mock_response.raise_for_status = MagicMock(side_effect=error)  # raise_for_status is sync
            mock_post.return_value = mock_response

            connector = MagicMock()
            connector.connector_id = "tg-bot-123"
            connector.type = ConnectorType.TELEGRAM
            connector.channel_type = "telegram"
            connector.config = {}

            with pytest.raises(TransportClientError, match="Transport delivery failed"):
                await client.deliver(connector=connector, payload=payload)

    async def test_close_clears_clients(self, mock_settings: Settings):
        """Test that close() clears all HTTP clients."""
        client = TransportClient(mock_settings)
        endpoint = "http://test:8000"  # pragma: allowlist secret
        client._get_client(endpoint)
        assert len(client._clients) == 1

        await client.close()
        assert len(client._clients) == 0

    async def test_deliver_includes_service_key_header(self, mock_settings: Settings):
        """Test that delivery includes service key header."""
        client = TransportClient(mock_settings)

        payload = {
            "connector_id": "tg-bot-123",
            "conversation_id": "conv-123",
            "correlation_id": "corr-123",
            "replies": ["Hello"],
            "metadata": {},
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            http_client = client._get_client("http://telegram-module:8001")
            http_client.post = mock_post

            connector = MagicMock()
            connector.connector_id = "tg-bot-123"
            connector.type = ConnectorType.TELEGRAM
            connector.channel_type = "telegram"
            connector.config = {}

            await client.deliver(connector=connector, payload=payload)

            # Verify the client was created with service key header
            assert http_client.headers.get("X-Service-Key") == "test-service-key"  # pragma: allowlist secret
