"""Tests for TransportBackendClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from common import FileType
from telegram_module.bots.models import BotConfig
from telegram_module.config import Settings
from telegram_module.services.backend import (
    TransportBackendClient,
    TransportBackendClientError,
)


@pytest.fixture
def backend_client(settings: Settings) -> TransportBackendClient:
    return TransportBackendClient(settings)


def _make_connector(
    connector_id: str = "test-connector",
    company_id: int = 1,
    bot_token: str = "123456:ABC-DEF",  # pragma: allowlist secret
    mode: str = "auto",
    channel_type: str = "telegram",
    connector_type: str = "telegram",
) -> dict:
    """Create connector response as returned by unified API."""
    return {
        "id": 1,
        "connector_id": connector_id,
        "company_id": company_id,
        "type": connector_type,
        "channel_type": channel_type,
        "display_name": "Test Bot",
        "managed": True,
        "config": {
            "bot_token": bot_token,
            "mode": mode,
        },
        "enabled": True,
        "debounce_window_seconds": 45,
        "debounce_storage_key_template": "debounce:{connector_id}:{conversation_id}",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
    }


class TestTransportBackendClient:
    """Test TransportBackendClient functionality."""

    def test_backend_client_init(self, settings: Settings) -> None:
        client = TransportBackendClient(settings)

        assert client._base_url is not None
        assert client._timeout is not None
        assert client._api_key is not None

    def test_backend_client_init_missing_url(self) -> None:
        from pydantic import ValidationError

        try:
            settings = Settings(backend__url="")
        except ValidationError:
            pytest.skip("Settings validation prevents empty URL")
            return

        if not settings.backend.url or not settings.backend.url.strip():
            with pytest.raises(ValueError, match="Backend URL must be configured"):
                TransportBackendClient(settings)
        else:
            pytest.skip("Settings uses default URL value")

    def test_backend_client_init_missing_api_key(self) -> None:
        from pydantic import ValidationError

        try:
            settings = Settings(service__api_key=None)
        except ValidationError:
            pytest.skip("Settings validation prevents None API key")
            return

        if settings.service.api_key is None:
            with pytest.raises(ValueError, match="SERVICE__API_KEY must be configured"):
                TransportBackendClient(settings)
        else:
            pytest.skip("Settings uses default API key value")

    @pytest.mark.asyncio
    async def test_fetch_connectors_success(self, backend_client: TransportBackendClient) -> None:
        connector = _make_connector()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.json.return_value = {"connectors": [connector]}
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            bots = await backend_client.fetch_connectors()

            assert len(bots) == 1
            assert isinstance(bots[0], BotConfig)
            assert bots[0].connector_id == "test-connector"
            assert bots[0].bot_token.get_secret_value() == "123456:ABC-DEF"

    @pytest.mark.asyncio
    async def test_fetch_connectors_filters_by_type_and_enabled(self, backend_client: TransportBackendClient) -> None:
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.json.return_value = {"connectors": []}
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            await backend_client.fetch_connectors()

            call_kwargs = mock_client.get.call_args[1]
            assert call_kwargs["params"]["type"] == "telegram"
            assert call_kwargs["params"]["enabled"] == "true"

    @pytest.mark.asyncio
    async def test_fetch_connectors_empty_list(self, backend_client: TransportBackendClient) -> None:
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.json.return_value = {"connectors": []}
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            bots = await backend_client.fetch_connectors()

            assert len(bots) == 0

    @pytest.mark.asyncio
    async def test_fetch_connectors_http_error(self, backend_client: TransportBackendClient) -> None:
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.side_effect = httpx.HTTPError("Connection error")
            mock_client_class.return_value = mock_client

            with pytest.raises(TransportBackendClientError):
                await backend_client.fetch_connectors()

    @pytest.mark.asyncio
    async def test_fetch_connectors_skips_non_telegram(self, backend_client: TransportBackendClient) -> None:
        wappi_connector = _make_connector(connector_type="wappi")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.json.return_value = {"connectors": [wappi_connector]}
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            bots = await backend_client.fetch_connectors()

            assert len(bots) == 0

    @pytest.mark.asyncio
    async def test_fetch_connectors_skips_missing_token(self, backend_client: TransportBackendClient) -> None:
        connector = _make_connector()
        connector["config"] = {}  # No bot_token

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.json.return_value = {"connectors": [connector]}
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            bots = await backend_client.fetch_connectors()

            assert len(bots) == 0

    @pytest.mark.asyncio
    async def test_fetch_connectors_multiple(self, backend_client: TransportBackendClient) -> None:
        connector1 = _make_connector(connector_id="bot-1", bot_token="token1")
        connector2 = _make_connector(connector_id="bot-2", bot_token="token2")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.json.return_value = {"connectors": [connector1, connector2]}
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            bots = await backend_client.fetch_connectors()

            assert len(bots) == 2
            assert {bot.connector_id for bot in bots} == {"bot-1", "bot-2"}

    @pytest.mark.asyncio
    async def test_fetch_connectors_uses_correct_url(self, backend_client: TransportBackendClient) -> None:
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.json.return_value = {"connectors": []}
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            await backend_client.fetch_connectors()

            call_args = mock_client.get.call_args[0]
            assert "/transport/connectors" in call_args[0]


class TestConnectorToBotConfig:
    """Test _connector_to_bot_config transformation."""

    def test_transform_minimal(self, backend_client: TransportBackendClient) -> None:
        connector = _make_connector()
        bot = backend_client._connector_to_bot_config(connector)

        assert bot is not None
        assert bot.connector_id == "test-connector"
        assert bot.company_id == "1"
        assert bot.bot_token.get_secret_value() == "123456:ABC-DEF"
        assert bot.mode.value == "auto"
        assert bot.channel_type == "telegram"

    def test_transform_with_webhook(self, backend_client: TransportBackendClient) -> None:
        connector = _make_connector()
        connector["config"]["webhook_secret"] = "secret123"  # pragma: allowlist secret
        connector["config"]["webhook_path"] = "/webhook/custom"

        bot = backend_client._connector_to_bot_config(connector)

        assert bot is not None
        assert bot.webhook_secret.get_secret_value() == "secret123"
        assert bot.webhook_path == "/webhook/custom"

    def test_transform_with_metadata(self, backend_client: TransportBackendClient) -> None:
        connector = _make_connector()
        connector["config"]["metadata"] = {"custom": "value"}

        bot = backend_client._connector_to_bot_config(connector)

        assert bot is not None
        assert bot.metadata == {"custom": "value"}

    def test_transform_returns_none_for_non_telegram(self, backend_client: TransportBackendClient) -> None:
        connector = _make_connector(connector_type="wappi")
        bot = backend_client._connector_to_bot_config(connector)
        assert bot is None

    def test_transform_returns_none_for_missing_token(self, backend_client: TransportBackendClient) -> None:
        connector = _make_connector()
        connector["config"] = {}
        bot = backend_client._connector_to_bot_config(connector)
        assert bot is None


class TestUploadArtifact:
    """Test TransportBackendClient.upload_artifact method."""

    @pytest.mark.asyncio
    async def test_upload_artifact_success(self, backend_client: TransportBackendClient) -> None:
        """Test successful artifact upload."""
        file_bytes = b"fake audio content"
        file_type = FileType.VOICE
        company_id = 1
        connector_id = "test-connector"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"artifact_id": "company_1/voice/abc123.mp3"}
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            artifact_id = await backend_client.upload_artifact(
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
    async def test_upload_artifact_retry_on_failure(self, backend_client: TransportBackendClient) -> None:
        """Test artifact upload with retry on failure."""
        file_bytes = b"fake audio content"
        file_type = FileType.AUDIO
        company_id = 1
        connector_id = "test-connector"

        with patch("httpx.AsyncClient") as mock_client_class, patch("asyncio.sleep") as mock_sleep:
            mock_response_success = MagicMock()
            mock_response_success.status_code = 200
            mock_response_success.json.return_value = {"artifact_id": "company_1/audio/xyz789.mp3"}
            mock_response_success.raise_for_status = MagicMock()

            mock_response_error = MagicMock()
            mock_response_error.status_code = 500
            mock_response_error.text = "Internal Server Error"
            mock_response_error.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Server error", request=MagicMock(), response=mock_response_error
            )

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.side_effect = [
                httpx.HTTPError("Connection error"),
                mock_response_success,
            ]
            mock_client_class.return_value = mock_client

            artifact_id = await backend_client.upload_artifact(
                file_bytes=file_bytes,
                file_type=file_type,
                company_id=company_id,
                connector_id=connector_id,
            )

            assert artifact_id == "company_1/audio/xyz789.mp3"
            assert mock_client.post.call_count == 2
            assert mock_sleep.called

    @pytest.mark.asyncio
    async def test_upload_artifact_max_retries_exceeded(self, backend_client: TransportBackendClient) -> None:
        """Test artifact upload fails after max retries."""
        file_bytes = b"fake audio content"
        file_type = FileType.VOICE
        company_id = 1
        connector_id = "test-connector"

        with patch("httpx.AsyncClient") as mock_client_class, patch("asyncio.sleep") as mock_sleep:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.side_effect = httpx.HTTPError("Connection error")
            mock_client_class.return_value = mock_client

            with pytest.raises(TransportBackendClientError, match="Failed to upload artifact"):
                await backend_client.upload_artifact(
                    file_bytes=file_bytes,
                    file_type=file_type,
                    company_id=company_id,
                    connector_id=connector_id,
                )

            assert mock_client.post.call_count == 3
            assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_upload_artifact_missing_artifact_id(self, backend_client: TransportBackendClient) -> None:
        """Test artifact upload when response is missing artifact_id."""
        file_bytes = b"fake audio content"
        file_type = FileType.VOICE
        company_id = 1
        connector_id = "test-connector"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {}
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            with pytest.raises(TransportBackendClientError, match="missing artifact_id"):
                await backend_client.upload_artifact(
                    file_bytes=file_bytes,
                    file_type=file_type,
                    company_id=company_id,
                    connector_id=connector_id,
                )

    @pytest.mark.asyncio
    async def test_upload_artifact_non_200_status(self, backend_client: TransportBackendClient) -> None:
        """Test artifact upload when backend returns non-200 status."""
        file_bytes = b"fake audio content"
        file_type = FileType.VOICE
        company_id = 1
        connector_id = "test-connector"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            with pytest.raises(TransportBackendClientError, match="status 500"):
                await backend_client.upload_artifact(
                    file_bytes=file_bytes,
                    file_type=file_type,
                    company_id=company_id,
                    connector_id=connector_id,
                )

    @pytest.mark.asyncio
    async def test_upload_artifact_all_file_types(self, backend_client: TransportBackendClient) -> None:
        """Test artifact upload for all supported file types."""
        file_bytes = b"fake content"
        company_id = 1
        connector_id = "test-connector"

        for file_type in FileType:
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "artifact_id": f"company_{company_id}/{file_type.value}/test.{file_type.value}"
                }
                mock_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.post.return_value = mock_response
                mock_client_class.return_value = mock_client

                artifact_id = await backend_client.upload_artifact(
                    file_bytes=file_bytes,
                    file_type=file_type,
                    company_id=company_id,
                    connector_id=connector_id,
                )

                assert artifact_id.startswith(f"company_{company_id}/{file_type.value}/")
