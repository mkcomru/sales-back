"""Tests for sync more chats functionality."""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.backend.modules.transport.models import Connector, ConnectorType, SyncStatus


class TestSyncMoreChatsEndpoint:
    """Tests for POST /transport/connectors/{connector_id}/sync/more-chats endpoint."""

    @pytest.fixture
    async def wappi_connector(self, company_factory):
        """Create a wappi connector for testing."""
        company = await company_factory()
        connector = await Connector.create(
            connector_id="test-wappi-more-chats",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="whatsapp",
            display_name="Test WhatsApp More Chats",
            managed=True,
            config={"wappi_token": "test-token", "wappi_profile_id": "test-profile"},
            enabled=True,
            sync_status=SyncStatus.COMPLETED,
        )
        return connector

    async def test_sync_more_chats_without_auth(self, api_client: httpx.AsyncClient):
        """Test that sync more chats requires authentication."""
        response = await api_client.post("/api/v1/transport/connectors/test-connector/sync/more-chats")
        assert response.status_code == 401

    async def test_sync_more_chats_connector_not_found(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
    ):
        """Test sync more chats with non-existent connector."""
        response = await api_client.post(
            "/api/v1/transport/connectors/non-existent-connector/sync/more-chats",
            headers=service_headers,
        )
        assert response.status_code == 404
        assert "Connector not found" in response.json()["detail"]

    async def test_sync_more_chats_unmanaged_connector(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        company_factory,
    ):
        """Test sync more chats with unmanaged (custom) connector."""
        company = await company_factory()
        connector = await Connector.create(
            connector_id="test-custom-connector",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="Test Custom",
            managed=False,  # Unmanaged
            config={},
            enabled=True,
        )

        response = await api_client.post(
            f"/api/v1/transport/connectors/{connector.connector_id}/sync/more-chats",
            headers=service_headers,
        )
        assert response.status_code == 400
        assert "not managed" in response.json()["detail"].lower()

    async def test_sync_more_chats_unsupported_type(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        company_factory,
    ):
        """Test sync more chats with unsupported connector type."""
        company = await company_factory()
        connector = await Connector.create(
            connector_id="test-telegram-connector",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Test Telegram",
            managed=True,
            config={},
            enabled=True,
        )

        response = await api_client.post(
            f"/api/v1/transport/connectors/{connector.connector_id}/sync/more-chats",
            headers=service_headers,
        )
        assert response.status_code == 400
        assert "not supported" in response.json()["detail"].lower()

    @patch("httpx.AsyncClient")
    async def test_sync_more_chats_success(
        self,
        mock_httpx_client,
        api_client: httpx.AsyncClient,
        service_headers,
        wappi_connector: Connector,
        settings,
    ):
        """Test successful sync more chats triggers transport module."""
        settings.transport.wappi.url = "http://localhost:8002"
        # Mock httpx client
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.raise_for_status = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        response = await api_client.post(
            f"/api/v1/transport/connectors/{wappi_connector.connector_id}/sync/more-chats",
            headers=service_headers,
        )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "sync_triggered"
        assert data["connector_id"] == wappi_connector.connector_id
        assert "loading more chats" in data["message"].lower()

    @patch("httpx.AsyncClient")
    async def test_sync_more_chats_idempotent(
        self,
        mock_httpx_client,
        api_client: httpx.AsyncClient,
        service_headers,
        wappi_connector: Connector,
        settings,
    ):
        """Test sync more chats can be called multiple times."""
        settings.transport.wappi.url = "http://localhost:8002"
        # Mock httpx client
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.raise_for_status = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        # Call first time
        response1 = await api_client.post(
            f"/api/v1/transport/connectors/{wappi_connector.connector_id}/sync/more-chats",
            headers=service_headers,
        )
        assert response1.status_code == 202

        # Call second time
        response2 = await api_client.post(
            f"/api/v1/transport/connectors/{wappi_connector.connector_id}/sync/more-chats",
            headers=service_headers,
        )
        assert response2.status_code == 202


class TestSyncMoreChatsService:
    """Tests for ConnectorsService.sync_more_chats method."""

    @pytest.fixture
    async def wappi_connector(self, company_factory):
        """Create a wappi connector for testing."""
        company = await company_factory()
        connector = await Connector.create(
            connector_id="test-wappi-service",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="whatsapp",
            display_name="Test WhatsApp Service",
            managed=True,
            config={"wappi_token": "test-token", "wappi_profile_id": "test-profile"},
            enabled=True,
        )
        return connector

    async def test_sync_more_chats_service_connector_not_found(self):
        """Test service method with non-existent connector."""
        from src.backend.modules.transport.exceptions import ConnectorNotFoundError
        from src.backend.modules.transport.service import ConnectorsService

        service = ConnectorsService()

        with pytest.raises(ConnectorNotFoundError):
            await service.sync_more_chats(connector_id="non-existent-connector")

    async def test_sync_more_chats_service_unmanaged_connector(self, company_factory):
        """Test service method with unmanaged connector."""
        from src.backend.modules.transport.service import ConnectorsService

        company = await company_factory()
        connector = await Connector.create(
            connector_id="test-unmanaged",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="Test Unmanaged",
            managed=False,
            config={},
            enabled=True,
        )

        service = ConnectorsService()

        with pytest.raises(ValueError, match="not managed"):
            await service.sync_more_chats(connector_id=connector.connector_id)

    async def test_sync_more_chats_service_unsupported_type(self, company_factory):
        """Test service method with unsupported connector type."""
        from src.backend.modules.transport.service import ConnectorsService

        company = await company_factory()
        connector = await Connector.create(
            connector_id="test-telegram",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Test Telegram",
            managed=True,
            config={},
            enabled=True,
        )

        service = ConnectorsService()

        with pytest.raises(ValueError, match="not supported"):
            await service.sync_more_chats(connector_id=connector.connector_id)

    @patch("httpx.AsyncClient")
    async def test_sync_more_chats_service_success(
        self,
        mock_httpx_client,
        wappi_connector: Connector,
        settings,
    ):
        """Test service method successfully triggers background task."""
        from src.backend.modules.transport.service import ConnectorsService

        settings.transport.wappi.url = "http://localhost:8002"
        # Mock httpx client
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.raise_for_status = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        service = ConnectorsService()

        # Should not raise
        await service.sync_more_chats(connector_id=wappi_connector.connector_id)

        # Note: The actual HTTP call happens in background task,
        # so we can't assert on it directly in synchronous test
