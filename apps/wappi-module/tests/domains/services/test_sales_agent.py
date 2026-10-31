"""Tests for SalesAgentClient."""

from __future__ import annotations

import time
from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import SecretStr

from wappi_module.config import Settings
from wappi_module.connectors.models import WappiConnectorConfig
from wappi_module.services.sales_agent import BackendInboundClient, BackendInboundClientError


def _make_wappi_update(
    text: str = "test message",
    chat_id: str = "123456@c.us",
    msg_type: str = "chat",
    from_me: bool = False,
) -> dict:
    """Create a valid Wappi webhook payload."""
    return {
        "messages": [
            {
                "id": "msg123",
                "type": msg_type,
                "body": text,
                "chatId": chat_id,
                "from": chat_id,
                "fromMe": from_me,
                "time": int(time.time()),
            }
        ]
    }


def _make_telegram_wappi_update(
    text: str = "test message",
    chat_id: str = "123456",
    msg_type: str = "text",
    from_me: bool = False,
) -> dict:
    """Create a valid Wappi webhook payload for Telegram channel."""
    return {
        "messages": [
            {
                "id": "msg123",
                "type": msg_type,
                "body": text,
                "chatId": chat_id,
                "from": chat_id,
                "fromMe": from_me,
                "time": int(time.time()),
            }
        ]
    }


class TestSalesAgentClient:
    @pytest.mark.asyncio
    async def test_forward_update_success(self, mock_settings: Settings) -> None:
        client = BackendInboundClient(mock_settings)

        connector = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
            channel_type="whatsapp",
        )

        update = _make_wappi_update(text="Hello")

        mock_response = MagicMock()
        mock_response.status_code = HTTPStatus.ACCEPTED

        with patch("wappi_module.services.sales_agent.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.forward_update("test", connector, update)

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        # Check URL
        assert call_args[0][0].endswith("/messages/inbound")
        # Check InboundEnvelope format
        json_body = call_args[1]["json"]
        assert "conversation_id" in json_body
        assert "user_id" in json_body
        assert "text" in json_body
        assert json_body["text"] == "Hello"
        # Check headers
        assert call_args[1]["headers"]["X-Connector-Id"] == "test"

    @pytest.mark.asyncio
    async def test_forward_update_telegram_channel(self, mock_settings: Settings) -> None:
        client = BackendInboundClient(mock_settings)

        connector = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
            channel_type="telegram",  # Telegram via Wappi
        )

        update = _make_telegram_wappi_update(text="Telegram message")

        mock_response = MagicMock()
        mock_response.status_code = HTTPStatus.ACCEPTED

        with patch("wappi_module.services.sales_agent.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.forward_update("test", connector, update)

        mock_client.post.assert_called_once()
        json_body = mock_client.post.call_args[1]["json"]
        assert json_body["text"] == "Telegram message"

    @pytest.mark.asyncio
    async def test_forward_update_empty_messages(self, mock_settings: Settings) -> None:
        client = BackendInboundClient(mock_settings)

        connector = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
            channel_type="whatsapp",
        )

        update = {"messages": []}

        with patch("wappi_module.services.sales_agent.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            await client.forward_update("test", connector, update)

        # No messages to forward - post should not be called
        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_forward_update_skips_outgoing(self, mock_settings: Settings) -> None:
        client = BackendInboundClient(mock_settings)

        connector = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
            channel_type="whatsapp",
        )

        update = _make_wappi_update(from_me=True)  # Outgoing message

        with patch("wappi_module.services.sales_agent.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            await client.forward_update("test", connector, update)

        # Outgoing messages should be skipped
        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_forward_update_http_error(self, mock_settings: Settings) -> None:
        client = BackendInboundClient(mock_settings)

        connector = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
            channel_type="whatsapp",
        )

        update = _make_wappi_update()

        with patch("wappi_module.services.sales_agent.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(side_effect=httpx.HTTPError("Connection error"))
            mock_client_class.return_value = mock_client

            with pytest.raises(BackendInboundClientError, match="Failed to forward"):
                await client.forward_update("test", connector, update)

    @pytest.mark.asyncio
    async def test_forward_update_non_success_status(self, mock_settings: Settings) -> None:
        client = BackendInboundClient(mock_settings)

        connector = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
            channel_type="whatsapp",
        )

        update = _make_wappi_update()

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("wappi_module.services.sales_agent.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with pytest.raises(BackendInboundClientError, match="responded with status"):
                await client.forward_update("test", connector, update)

    @pytest.mark.asyncio
    async def test_forward_update_400_status(self, mock_settings: Settings) -> None:
        client = BackendInboundClient(mock_settings)

        connector = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
            channel_type="whatsapp",
        )

        update = _make_wappi_update()

        mock_response = MagicMock()
        mock_response.status_code = 400

        with patch("wappi_module.services.sales_agent.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with pytest.raises(BackendInboundClientError):
                await client.forward_update("test", connector, update)

    @pytest.mark.asyncio
    async def test_forward_update_uses_correct_url(self, mock_settings: Settings) -> None:
        from common.config import BackendSettings, EventingSettings

        settings = Settings(
            backend=BackendSettings(url="http://backend.test/api/v1"),
            service_api_key="test-key",  # pragma: allowlist secret
            eventing=EventingSettings(enabled=False),
        )
        client = BackendInboundClient(settings)

        connector = WappiConnectorConfig(
            connector_id="connector-123",
            company_id="456",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
            channel_type="whatsapp",
        )

        update = _make_wappi_update()

        mock_response = MagicMock()
        mock_response.status_code = HTTPStatus.ACCEPTED

        with patch("wappi_module.services.sales_agent.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.forward_update("connector-123", connector, update)

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "http://backend.test/api/v1/messages/inbound"

    @pytest.mark.asyncio
    async def test_forward_update_strips_trailing_slash_from_url(self, mock_settings: Settings) -> None:
        from common.config import BackendSettings, EventingSettings

        settings = Settings(
            backend=BackendSettings(url="http://backend.test/api/v1/"),
            service_api_key="test-key",  # pragma: allowlist secret
            eventing=EventingSettings(enabled=False),
        )
        client = BackendInboundClient(settings)

        connector = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
            channel_type="whatsapp",
        )

        update = _make_wappi_update()

        mock_response = MagicMock()
        mock_response.status_code = HTTPStatus.ACCEPTED

        with patch("wappi_module.services.sales_agent.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.forward_update("test", connector, update)

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "http://backend.test/api/v1/messages/inbound"


class TestNormalizeMessage:
    """Test _normalize_message method."""

    @pytest.mark.asyncio
    async def test_normalize_whatsapp_chat_message(self, mock_settings: Settings) -> None:
        client = BackendInboundClient(mock_settings)
        message = {
            "type": "chat",
            "body": "Hello",
            "chatId": "123@c.us",
            "from": "123@c.us",
            "time": 1234567890,
        }
        envelope = await client._normalize_message(message, "whatsapp", company_id=1, connector_id="test-connector")

        assert envelope is not None
        assert envelope.conversation_id == "123@c.us"
        assert envelope.text == "Hello"
        assert envelope.ts == 1234567890

    @pytest.mark.asyncio
    async def test_normalize_telegram_text_message(self, mock_settings: Settings) -> None:
        client = BackendInboundClient(mock_settings)
        message = {
            "type": "text",
            "body": "Hello",
            "chatId": "456",
            "from": "456",
            "time": 1234567890,
        }
        envelope = await client._normalize_message(message, "telegram", company_id=1, connector_id="test-connector")

        assert envelope is not None
        assert envelope.conversation_id == "456"
        assert envelope.text == "Hello"

    @pytest.mark.asyncio
    async def test_normalize_skips_outgoing(self, mock_settings: Settings) -> None:
        client = BackendInboundClient(mock_settings)
        message = {
            "type": "chat",
            "body": "Hello",
            "chatId": "123@c.us",
            "fromMe": True,
        }
        envelope = await client._normalize_message(message, "whatsapp", company_id=1, connector_id="test-connector")
        assert envelope is None

    @pytest.mark.asyncio
    async def test_normalize_ptt_voice_message(self, mock_settings: Settings) -> None:
        import base64
        from unittest.mock import AsyncMock

        from common import AudioConversionService

        client = BackendInboundClient(mock_settings)
        mock_backend_client = AsyncMock()
        mock_backend_client.upload_artifact = AsyncMock(return_value="company_1/voice/test.mp3")
        client._backend_client = mock_backend_client

        mock_audio_converter = AsyncMock(spec=AudioConversionService)
        mock_audio_converter.convert_to_mp3 = AsyncMock(return_value=b"mp3_audio_data")
        client._audio_converter = mock_audio_converter

        # Use valid base64 encoded data
        audio_bytes = b"fake_audio_data"
        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

        message = {
            "type": "ptt",
            "body": audio_base64,
            "mimetype": "audio/ogg",
            "chatId": "123@c.us",
            "from": "123@c.us",
            "time": 1234567890,
        }
        envelope = await client._normalize_message(message, "whatsapp", company_id=1, connector_id="test-connector")

        assert envelope is not None
        assert len(envelope.artifact_ids) > 0
        assert mock_backend_client.upload_artifact.called
        assert mock_audio_converter.convert_to_mp3.called

    @pytest.mark.asyncio
    async def test_normalize_unsupported_type(self, mock_settings: Settings) -> None:
        client = BackendInboundClient(mock_settings)
        message = {
            "type": "image",
            "chatId": "123@c.us",
            "from": "123@c.us",
        }
        envelope = await client._normalize_message(message, "whatsapp", company_id=1, connector_id="test-connector")
        assert envelope is None

    @pytest.mark.asyncio
    async def test_normalize_missing_conversation_id(self, mock_settings: Settings) -> None:
        client = BackendInboundClient(mock_settings)
        message = {
            "type": "chat",
            "body": "Hello",
        }
        envelope = await client._normalize_message(message, "whatsapp", company_id=1, connector_id="test-connector")
        assert envelope is None

    @pytest.mark.asyncio
    async def test_normalize_whats_app_variant(self, mock_settings: Settings) -> None:
        client = BackendInboundClient(mock_settings)
        message = {
            "type": "chat",
            "body": "Hello",
            "chatId": "123@c.us",
            "from": "123@c.us",
            "time": 1234567890,
        }
        # Test whats_app variant
        envelope = await client._normalize_message(message, "whats_app", company_id=1, connector_id="test-connector")
        assert envelope is not None
        assert envelope.text == "Hello"

    @pytest.mark.asyncio
    async def test_normalize_vk_chat_type(self, mock_settings: Settings) -> None:
        client = BackendInboundClient(mock_settings)
        message = {
            "type": "chat",
            "body": "Hello from VK",
            "chatId": "863567278",
            "from": "863567278",
            "time": 1234567890,
        }
        envelope = await client._normalize_message(message, "vk", company_id=1, connector_id="test-connector")
        assert envelope is not None
        assert envelope.text == "Hello from VK"
        assert envelope.conversation_id == "863567278"

    @pytest.mark.asyncio
    async def test_normalize_vk_text_type(self, mock_settings: Settings) -> None:
        client = BackendInboundClient(mock_settings)
        message = {
            "type": "text",
            "body": "Hello from VK text",
            "chatId": "863567278",
            "from": "863567278",
            "time": 1234567890,
        }
        envelope = await client._normalize_message(message, "vk", company_id=1, connector_id="test-connector")
        assert envelope is not None
        assert envelope.text == "Hello from VK text"
