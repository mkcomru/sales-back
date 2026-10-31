"""Tests for WappiBackendClient history-related methods."""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from pydantic import SecretStr

from common.config import BackendSettings, EventingSettings, S3Settings
from wappi_module.config import Settings
from wappi_module.services.backend import WappiBackendClient


class TestGetThreadByConversation:
    """Tests for WappiBackendClient.get_thread_by_conversation method."""

    @pytest.fixture
    def backend_client(self):
        """Create backend client for testing."""
        settings = Settings(
            backend=BackendSettings(url="http://backend:8001"),
            service_api_key="test-api-key",  # pragma: allowlist secret
            app_environment="test",
            app_debug=False,
            config_refresh_interval_s=0,
            request_timeout_s=10.0,
            max_delivery_attempts=3,
            idempotency_cache_ttl_s=86400,
            eventing=EventingSettings(enabled=False),
            s3=S3Settings(
                endpoint_url="http://localhost:9000",
                access_key_id=SecretStr("test-access-key"),  # pragma: allowlist secret
                secret_access_key=SecretStr("test-secret-key"),  # pragma: allowlist secret
                bucket_name="test-bucket",
            ),
        )
        return WappiBackendClient(settings)

    @patch("httpx.AsyncClient")
    async def test_get_thread_by_conversation_success(
        self,
        mock_httpx_client,
        backend_client,
    ):
        """Test successful thread retrieval."""
        # Mock response
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "thread_id": "thread-123",
            "history_synced": False,
        }
        mock_response.raise_for_status = Mock()
        mock_client_instance.get.return_value = mock_response
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        result = await backend_client.get_thread_by_conversation(
            connector_id="connector-456",
            conversation_id="conv-789",
        )

        assert result is not None
        thread_id, history_synced = result
        assert thread_id == "thread-123"
        assert history_synced is False

        # Verify request was made correctly
        mock_client_instance.get.assert_called_once()
        call_args = mock_client_instance.get.call_args
        assert "/internal/chat/threads/by-conversation" in call_args[0][0]
        assert call_args[1]["params"]["connector_id"] == "connector-456"
        assert call_args[1]["params"]["conversation_id"] == "conv-789"

    @patch("httpx.AsyncClient")
    async def test_get_thread_by_conversation_not_found(
        self,
        mock_httpx_client,
        backend_client,
    ):
        """Test thread not found returns None."""
        # Mock 404 response
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 404
        mock_client_instance.get.return_value = mock_response
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        result = await backend_client.get_thread_by_conversation(
            connector_id="connector-456",
            conversation_id="non-existent",
        )

        assert result is None

    @patch("httpx.AsyncClient")
    async def test_get_thread_by_conversation_history_synced_true(
        self,
        mock_httpx_client,
        backend_client,
    ):
        """Test thread with history_synced=True."""
        # Mock response
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "thread_id": "thread-synced",
            "history_synced": True,
        }
        mock_response.raise_for_status = Mock()
        mock_client_instance.get.return_value = mock_response
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        result = await backend_client.get_thread_by_conversation(
            connector_id="connector-456",
            conversation_id="conv-synced",
        )

        assert result is not None
        thread_id, history_synced = result
        assert thread_id == "thread-synced"
        assert history_synced is True

    @patch("httpx.AsyncClient")
    async def test_get_thread_by_conversation_http_error(
        self,
        mock_httpx_client,
        backend_client,
    ):
        """Test error handling for HTTP errors."""
        # Mock error
        mock_client_instance = AsyncMock()
        mock_client_instance.get.side_effect = httpx.ConnectError("Connection refused")
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        result = await backend_client.get_thread_by_conversation(
            connector_id="connector-456",
            conversation_id="conv-789",
        )

        # Should return None on error
        assert result is None


class TestMarkThreadHistorySynced:
    """Tests for WappiBackendClient.mark_thread_history_synced method."""

    @pytest.fixture
    def backend_client(self):
        """Create backend client for testing."""
        settings = Settings(
            backend=BackendSettings(url="http://backend:8001"),
            service_api_key="test-api-key",  # pragma: allowlist secret
            app_environment="test",
            app_debug=False,
            config_refresh_interval_s=0,
            request_timeout_s=10.0,
            max_delivery_attempts=3,
            idempotency_cache_ttl_s=86400,
            eventing=EventingSettings(enabled=False),
            s3=S3Settings(
                endpoint_url="http://localhost:9000",
                access_key_id=SecretStr("test-access-key"),  # pragma: allowlist secret
                secret_access_key=SecretStr("test-secret-key"),  # pragma: allowlist secret
                bucket_name="test-bucket",
            ),
        )
        return WappiBackendClient(settings)

    @patch("httpx.AsyncClient")
    async def test_mark_thread_history_synced_success(
        self,
        mock_httpx_client,
        backend_client,
    ):
        """Test successfully marking thread as synced."""
        # Mock response
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = Mock()
        mock_client_instance.patch.return_value = mock_response
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        result = await backend_client.mark_thread_history_synced(thread_id="thread-123")

        assert result is True

        # Verify request was made correctly
        mock_client_instance.patch.assert_called_once()
        call_args = mock_client_instance.patch.call_args
        assert "/internal/chat/threads/thread-123/history-synced" in call_args[0][0]

    @patch("httpx.AsyncClient")
    async def test_mark_thread_history_synced_not_found(
        self,
        mock_httpx_client,
        backend_client,
    ):
        """Test marking non-existent thread returns False."""
        # Mock 404 response
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not found",
            request=Mock(),
            response=mock_response,
        )
        mock_client_instance.patch.return_value = mock_response
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        result = await backend_client.mark_thread_history_synced(thread_id="non-existent")

        assert result is False

    @patch("httpx.AsyncClient")
    async def test_mark_thread_history_synced_http_error(
        self,
        mock_httpx_client,
        backend_client,
    ):
        """Test error handling for HTTP errors."""
        # Mock error
        mock_client_instance = AsyncMock()
        mock_client_instance.patch.side_effect = httpx.ConnectError("Connection refused")
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        result = await backend_client.mark_thread_history_synced(thread_id="thread-123")

        # Should return False on error
        assert result is False

    @patch("httpx.AsyncClient")
    async def test_mark_thread_history_synced_idempotent(
        self,
        mock_httpx_client,
        backend_client,
    ):
        """Test marking thread as synced multiple times."""
        # Mock response
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = Mock()
        mock_client_instance.patch.return_value = mock_response
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        # Call twice
        result1 = await backend_client.mark_thread_history_synced(thread_id="thread-123")
        result2 = await backend_client.mark_thread_history_synced(thread_id="thread-123")

        assert result1 is True
        assert result2 is True
        assert mock_client_instance.patch.call_count == 2
