"""Tests for backend_client module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import SecretStr

from common import SalesAgentSettings

from src.sales_agent.services.backend_client import (
    BackendClient,
    BackendConnectorListResponse,
)


class TestBackendClientInit:
    """Test BackendClient initialization."""

    def test_init_success(self, settings: SalesAgentSettings) -> None:
        """Test successful initialization."""
        settings.backend.url = "http://localhost:8001"
        client = BackendClient(settings)
        assert client.base_url == "http://localhost:8001"
        assert client.timeout == 10.0

    def test_init_missing_url_raises_error(self, settings: SalesAgentSettings) -> None:
        """Test initialization without URL raises ValueError."""
        settings.backend.url = None
        with pytest.raises(ValueError, match="Backend URL is required"):
            BackendClient(settings)

    def test_init_strips_trailing_slash(self, settings: SalesAgentSettings) -> None:
        """Test trailing slash is stripped from URL."""
        settings.backend.url = "http://localhost:8001/"
        client = BackendClient(settings)
        assert client.base_url == "http://localhost:8001"


class TestListConnectors:
    """Test list_connectors method."""

    @pytest.mark.asyncio
    async def test_list_connectors_success(self, settings: SalesAgentSettings) -> None:
        """Test successful connector list retrieval."""
        settings.backend.url = "http://localhost:8001"
        settings.service.api_key = SecretStr("test-key")
        client = BackendClient(settings)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "connectors": [{"connector_id": "test-1"}],
            "ttl_seconds": 60,
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await client.list_connectors()

            assert result is not None
            assert isinstance(result, BackendConnectorListResponse)
            assert len(result.connectors) == 1

    @pytest.mark.asyncio
    async def test_list_connectors_no_service_key(self, settings: SalesAgentSettings) -> None:
        """Test list_connectors returns None when service key is missing."""
        settings.backend.url = "http://localhost:8001"
        settings.service.api_key = None
        client = BackendClient(settings)

        result = await client.list_connectors()

        assert result is None

    @pytest.mark.asyncio
    async def test_list_connectors_404_returns_none(self, settings: SalesAgentSettings) -> None:
        """Test list_connectors returns None on 404."""
        settings.backend.url = "http://localhost:8001"
        settings.service.api_key = SecretStr("test-key")
        client = BackendClient(settings)

        mock_response = MagicMock()
        mock_response.status_code = 404
        error = httpx.HTTPStatusError("404", request=MagicMock(), response=mock_response)
        error.response = mock_response

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(side_effect=error)
            mock_client_class.return_value = mock_client

            result = await client.list_connectors()

            assert result is None


class TestChatClient:
    """Test chat client methods."""

    @pytest.mark.asyncio
    async def test_close_chat_client(self, settings: SalesAgentSettings) -> None:
        """Test close_chat_client."""
        settings.backend.url = "http://localhost:8001"
        client = BackendClient(settings)

        mock_client = AsyncMock()
        client._chat_client = mock_client

        await client.close_chat_client()

        mock_client.aclose.assert_called_once()
        assert client._chat_client is None


class TestSchedulingCapabilityClient:
    """Test scheduling capability client methods."""

    @pytest.mark.asyncio
    async def test_get_available_dates_posts_expected_payload(self, settings: SalesAgentSettings) -> None:
        settings.backend.url = "http://localhost:8001"
        settings.service.api_key = SecretStr("test-key")
        client = BackendClient(settings)

        mock_response = MagicMock()
        mock_response.json.return_value = {"dates": ["2026-03-12", "2026-03-13"]}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        client._chat_client = mock_client

        result = await client.get_available_dates(
            company_id=1,
            staff_id=3676906,
            service_ids=[18277420],
        )

        assert result == {"dates": ["2026-03-12", "2026-03-13"]}
        mock_client.post.assert_awaited_once_with(
            "/internal/capabilities/scheduling/dates",
            json={"company_id": 1, "staff_id": 3676906, "service_ids": [18277420]},
        )
