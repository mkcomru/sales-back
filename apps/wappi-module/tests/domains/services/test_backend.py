"""Tests for WappiBackendClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from common import FileType
from wappi_module.config import Settings
from wappi_module.connectors.models import WappiConnectorConfig
from wappi_module.services.backend import WappiBackendClient, WappiBackendClientError


def _make_connector(
    connector_id: str = "test-connector",
    company_id: int = 1,
    wappi_token: str = "wappi-token-123",
    wappi_profile_id: str = "profile-123",
    channel_type: str = "whatsapp",
    connector_type: str = "wappi",
) -> dict:
    """Create connector response as returned by unified API."""
    return {
        "id": 1,
        "connector_id": connector_id,
        "company_id": company_id,
        "type": connector_type,
        "channel_type": channel_type,
        "display_name": "Test Wappi",
        "managed": True,
        "config": {
            "wappi_token": wappi_token,
            "wappi_profile_id": wappi_profile_id,
        },
        "enabled": True,
        "debounce_window_seconds": 45,
        "debounce_storage_key_template": "debounce:{connector_id}:{conversation_id}",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
    }


class TestWappiBackendClient:
    @pytest.mark.asyncio
    async def test_fetch_connectors_success(self, mock_settings: Settings) -> None:
        client = WappiBackendClient(mock_settings)
        connector = _make_connector()

        mock_response = MagicMock()
        mock_response.json.return_value = {"connectors": [connector]}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.backend.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            connectors = await client.fetch_connectors()

        assert len(connectors) == 1
        assert isinstance(connectors[0], WappiConnectorConfig)
        assert connectors[0].connector_id == "test-connector"
        assert connectors[0].wappi_token.get_secret_value() == "wappi-token-123"
        assert connectors[0].wappi_profile_id == "profile-123"

    @pytest.mark.asyncio
    async def test_fetch_connectors_filters_by_type_and_enabled(self, mock_settings: Settings) -> None:
        client = WappiBackendClient(mock_settings)

        mock_response = MagicMock()
        mock_response.json.return_value = {"connectors": []}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.backend.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.fetch_connectors()

            call_kwargs = mock_client.get.call_args[1]
            assert call_kwargs["params"]["type"] == "wappi"
            assert call_kwargs["params"]["enabled"] == "true"

    @pytest.mark.asyncio
    async def test_fetch_connectors_multiple(self, mock_settings: Settings) -> None:
        client = WappiBackendClient(mock_settings)
        connector1 = _make_connector(connector_id="wappi-1", channel_type="telegram")
        connector2 = _make_connector(connector_id="wappi-2", channel_type="whatsapp")

        mock_response = MagicMock()
        mock_response.json.return_value = {"connectors": [connector1, connector2]}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.backend.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            connectors = await client.fetch_connectors()

        assert len(connectors) == 2
        assert {c.connector_id for c in connectors} == {"wappi-1", "wappi-2"}

    @pytest.mark.asyncio
    async def test_fetch_connectors_empty(self, mock_settings: Settings) -> None:
        client = WappiBackendClient(mock_settings)

        mock_response = MagicMock()
        mock_response.json.return_value = {"connectors": []}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.backend.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            connectors = await client.fetch_connectors()

        assert len(connectors) == 0

    @pytest.mark.asyncio
    async def test_fetch_connectors_http_error(self, mock_settings: Settings) -> None:
        client = WappiBackendClient(mock_settings)

        with patch("wappi_module.services.backend.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(side_effect=httpx.HTTPError("Connection error"))
            mock_client_class.return_value = mock_client

            with pytest.raises(WappiBackendClientError):
                await client.fetch_connectors()

    @pytest.mark.asyncio
    async def test_fetch_connectors_skips_non_wappi(self, mock_settings: Settings) -> None:
        client = WappiBackendClient(mock_settings)
        telegram_connector = _make_connector(connector_type="telegram")

        mock_response = MagicMock()
        mock_response.json.return_value = {"connectors": [telegram_connector]}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.backend.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            connectors = await client.fetch_connectors()

        assert len(connectors) == 0

    @pytest.mark.asyncio
    async def test_fetch_connectors_skips_missing_token(self, mock_settings: Settings) -> None:
        client = WappiBackendClient(mock_settings)
        connector = _make_connector()
        connector["config"] = {"wappi_profile_id": "profile-123"}

        mock_response = MagicMock()
        mock_response.json.return_value = {"connectors": [connector]}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.backend.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            connectors = await client.fetch_connectors()

        assert len(connectors) == 0

    @pytest.mark.asyncio
    async def test_fetch_connectors_skips_missing_profile_id(self, mock_settings: Settings) -> None:
        client = WappiBackendClient(mock_settings)
        connector = _make_connector()
        connector["config"] = {"wappi_token": "token-123"}

        mock_response = MagicMock()
        mock_response.json.return_value = {"connectors": [connector]}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.backend.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            connectors = await client.fetch_connectors()

        assert len(connectors) == 0

    @pytest.mark.asyncio
    async def test_fetch_connectors_uses_correct_url(self, mock_settings: Settings) -> None:
        client = WappiBackendClient(mock_settings)

        mock_response = MagicMock()
        mock_response.json.return_value = {"connectors": []}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.backend.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.fetch_connectors()

            call_args = mock_client.get.call_args[0]
            assert "/transport/connectors" in call_args[0]

    def test_init_requires_backend_url(self) -> None:
        from common.config import BackendSettings, EventingSettings

        settings = Settings(
            backend=BackendSettings(url=""),
            sales_agent_url="http://sales-agent.test",
            service_api_key="test-key",  # pragma: allowlist secret
            eventing=EventingSettings(enabled=False),
        )

        with pytest.raises(ValueError, match="Backend URL must be configured"):
            WappiBackendClient(settings)

    def test_init_requires_api_key(self) -> None:
        from common.config import BackendSettings, EventingSettings, ServiceAuthSettings

        settings = Settings(
            backend=BackendSettings(url="http://backend.test"),
            sales_agent_url="http://sales-agent.test",
            service=ServiceAuthSettings(api_key=None),
            eventing=EventingSettings(enabled=False),
        )

        with pytest.raises(ValueError, match="SERVICE__API_KEY must be configured"):
            WappiBackendClient(settings)


class TestConnectorToWappiConfig:
    """Test _connector_to_wappi_config transformation."""

    def test_transform_minimal(self, mock_settings: Settings) -> None:
        client = WappiBackendClient(mock_settings)
        connector = _make_connector()

        config = client._connector_to_wappi_config(connector)

        assert config is not None
        assert config.connector_id == "test-connector"
        assert config.company_id == "1"
        assert config.wappi_token.get_secret_value() == "wappi-token-123"
        assert config.wappi_profile_id == "profile-123"
        assert config.channel_type == "whatsapp"

    def test_transform_with_metadata(self, mock_settings: Settings) -> None:
        client = WappiBackendClient(mock_settings)
        connector = _make_connector()
        connector["config"]["metadata"] = {"custom": "value"}

        config = client._connector_to_wappi_config(connector)

        assert config is not None
        assert config.metadata == {"custom": "value"}

    def test_transform_returns_none_for_non_wappi(self, mock_settings: Settings) -> None:
        client = WappiBackendClient(mock_settings)
        connector = _make_connector(connector_type="telegram")

        config = client._connector_to_wappi_config(connector)

        assert config is None

    def test_transform_returns_none_for_missing_token(self, mock_settings: Settings) -> None:
        client = WappiBackendClient(mock_settings)
        connector = _make_connector()
        connector["config"] = {"wappi_profile_id": "profile-123"}

        config = client._connector_to_wappi_config(connector)

        assert config is None

    def test_transform_returns_none_for_missing_profile_id(self, mock_settings: Settings) -> None:
        client = WappiBackendClient(mock_settings)
        connector = _make_connector()
        connector["config"] = {"wappi_token": "token-123"}

        config = client._connector_to_wappi_config(connector)

        assert config is None


class TestUploadArtifact:
    """Test WappiBackendClient.upload_artifact method."""

    @pytest.mark.asyncio
    async def test_upload_artifact_success(self, mock_settings: Settings) -> None:
        """Test successful artifact upload."""
        client = WappiBackendClient(mock_settings)
        file_bytes = b"fake audio content"
        file_type = FileType.VOICE
        company_id = 1
        connector_id = "test-connector"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"artifact_id": "company_1/voice/abc123.mp3"}
        mock_response.raise_for_status = MagicMock()

        with patch("common.transport.base_backend_client.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            artifact_id = await client.upload_artifact(
                file_bytes=file_bytes,
                file_type=file_type,
                company_id=company_id,
                connector_id=connector_id,
            )

            assert artifact_id == "company_1/voice/abc123.mp3"
            assert mock_client.post.called
            call_kwargs = mock_client.post.call_args[1]
            assert call_kwargs["headers"]["X-Connector-Id"] == connector_id

    @pytest.mark.asyncio
    async def test_upload_artifact_retry_on_failure(self, mock_settings: Settings) -> None:
        """Test artifact upload with retry on failure."""
        client = WappiBackendClient(mock_settings)
        file_bytes = b"fake audio content"
        file_type = FileType.AUDIO
        company_id = 1
        connector_id = "test-connector"

        mock_response_success = MagicMock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {"artifact_id": "company_1/audio/xyz789.mp3"}
        mock_response_success.raise_for_status = MagicMock()

        with (
            patch("common.transport.base_backend_client.httpx.AsyncClient") as mock_client_class,
            patch("asyncio.sleep") as mock_sleep,
        ):
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(side_effect=[httpx.HTTPError("Connection error"), mock_response_success])
            mock_client_class.return_value = mock_client

            artifact_id = await client.upload_artifact(
                file_bytes=file_bytes,
                file_type=file_type,
                company_id=company_id,
                connector_id=connector_id,
            )

            assert artifact_id == "company_1/audio/xyz789.mp3"
            assert mock_client.post.call_count == 2
            assert mock_sleep.called

    @pytest.mark.asyncio
    async def test_upload_artifact_max_retries_exceeded(self, mock_settings: Settings) -> None:
        """Test artifact upload fails after max retries."""
        client = WappiBackendClient(mock_settings)
        file_bytes = b"fake audio content"
        file_type = FileType.VOICE
        company_id = 1
        connector_id = "test-connector"

        with (
            patch("common.transport.base_backend_client.httpx.AsyncClient") as mock_client_class,
            patch("asyncio.sleep") as mock_sleep,
        ):
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(side_effect=httpx.HTTPError("Connection error"))
            mock_client_class.return_value = mock_client

            with pytest.raises(WappiBackendClientError, match="Failed to upload artifact"):
                await client.upload_artifact(
                    file_bytes=file_bytes,
                    file_type=file_type,
                    company_id=company_id,
                    connector_id=connector_id,
                )

            assert mock_client.post.call_count == 3
            assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_upload_artifact_missing_artifact_id(self, mock_settings: Settings) -> None:
        """Test artifact upload when response is missing artifact_id."""
        client = WappiBackendClient(mock_settings)
        file_bytes = b"fake audio content"
        file_type = FileType.VOICE
        company_id = 1
        connector_id = "test-connector"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.raise_for_status = MagicMock()

        with patch("common.transport.base_backend_client.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with pytest.raises(WappiBackendClientError, match="missing artifact_id"):
                await client.upload_artifact(
                    file_bytes=file_bytes,
                    file_type=file_type,
                    company_id=company_id,
                    connector_id=connector_id,
                )

    @pytest.mark.asyncio
    async def test_upload_artifact_non_200_status(self, mock_settings: Settings) -> None:
        """Test artifact upload when backend returns non-200 status."""
        client = WappiBackendClient(mock_settings)
        file_bytes = b"fake audio content"
        file_type = FileType.VOICE
        company_id = 1
        connector_id = "test-connector"

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status = MagicMock()

        with patch("common.transport.base_backend_client.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with pytest.raises(WappiBackendClientError, match="status 500"):
                await client.upload_artifact(
                    file_bytes=file_bytes,
                    file_type=file_type,
                    company_id=company_id,
                    connector_id=connector_id,
                )

    @pytest.mark.asyncio
    async def test_upload_artifact_all_file_types(self, mock_settings: Settings) -> None:
        """Test artifact upload for all supported file types."""
        client = WappiBackendClient(mock_settings)
        file_bytes = b"fake content"
        company_id = 1
        connector_id = "test-connector"

        for file_type in FileType:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "artifact_id": f"company_{company_id}/{file_type.value}/test.{file_type.value}"
            }
            mock_response.raise_for_status = MagicMock()

            with patch("common.transport.base_backend_client.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                artifact_id = await client.upload_artifact(
                    file_bytes=file_bytes,
                    file_type=file_type,
                    company_id=company_id,
                    connector_id=connector_id,
                )

                assert artifact_id.startswith(f"company_{company_id}/{file_type.value}/")
