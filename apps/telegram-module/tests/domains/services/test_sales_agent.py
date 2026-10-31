"""Tests for SalesAgentClient."""

from __future__ import annotations

import time
from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from telegram_module.bots.models import BotConfig
from telegram_module.config import Settings
from telegram_module.services.sales_agent import BackendInboundClient, BackendInboundClientError


@pytest.fixture
def sales_agent_client(settings: Settings) -> BackendInboundClient:
    return BackendInboundClient(settings)


@pytest.fixture
def bot_config() -> BotConfig:
    return BotConfig(
        connector_id="test-connector",
        company_id="test-company",
        bot_token="123456:ABC-DEF",  # pragma: allowlist secret
    )


def _make_telegram_update(text: str = "test message", chat_id: int = 12345, user_id: int = 67890) -> dict:
    """Create a valid Telegram update payload."""
    return {
        "message": {
            "message_id": 1,
            "date": int(time.time()),
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "text": text,
        }
    }


class TestSalesAgentClient:
    """Test BackendInboundClient functionality."""

    def test_sales_agent_client_init(self, settings: Settings) -> None:
        client = BackendInboundClient(settings)

        assert client._base_url is not None
        assert client._timeout is not None

    @pytest.mark.asyncio
    async def test_forward_update_success(
        self, sales_agent_client: BackendInboundClient, bot_config: BotConfig
    ) -> None:
        update = _make_telegram_update()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = HTTPStatus.ACCEPTED

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            await sales_agent_client.forward_update("test-connector", bot_config, update)

            mock_client.post.assert_called_once()
            call_kwargs = mock_client.post.call_args[1]
            # Check InboundEnvelope format
            json_body = call_kwargs["json"]
            assert "conversation_id" in json_body
            assert "user_id" in json_body
            assert "text" in json_body
            assert "ts" in json_body
            assert json_body["conversation_id"] == "12345"
            assert json_body["user_id"] == "67890"
            assert json_body["text"] == "test message"
            # Check headers
            assert "X-Connector-Id" in call_kwargs["headers"]
            assert call_kwargs["headers"]["X-Connector-Id"] == "test-connector"

    @pytest.mark.asyncio
    async def test_forward_update_with_service_key(self, settings: Settings) -> None:
        # Create client with service key configured
        client = BackendInboundClient(settings)
        bot_config = BotConfig(
            connector_id="test-connector",
            company_id="test-company",
            bot_token="123456:ABC-DEF",  # pragma: allowlist secret
        )
        update = _make_telegram_update()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = HTTPStatus.ACCEPTED

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            await client.forward_update("test-connector", bot_config, update)

            call_kwargs = mock_client.post.call_args[1]
            # Service key header should be present if configured
            if settings.service.api_key:
                assert settings.service.resolved_header() in call_kwargs["headers"]

    @pytest.mark.asyncio
    async def test_forward_update_skips_unsupported(
        self, sales_agent_client: BackendInboundClient, bot_config: BotConfig
    ) -> None:
        # Update without proper message structure should be skipped
        update = {"update_id": 123}  # No message

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            await sales_agent_client.forward_update("test-connector", bot_config, update)

            # Should not call post for unsupported updates
            mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_forward_update_http_error(
        self, sales_agent_client: BackendInboundClient, bot_config: BotConfig
    ) -> None:
        update = _make_telegram_update()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.side_effect = httpx.HTTPError("Connection error")
            mock_client_class.return_value = mock_client

            with pytest.raises(BackendInboundClientError):
                await sales_agent_client.forward_update("test-connector", bot_config, update)

    @pytest.mark.asyncio
    async def test_forward_update_bad_status(
        self, sales_agent_client: BackendInboundClient, bot_config: BotConfig
    ) -> None:
        update = _make_telegram_update()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = HTTPStatus.BAD_REQUEST

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            with pytest.raises(BackendInboundClientError):
                await sales_agent_client.forward_update("test-connector", bot_config, update)

    @pytest.mark.asyncio
    async def test_forward_update_url_format(
        self, sales_agent_client: BackendInboundClient, bot_config: BotConfig
    ) -> None:
        update = _make_telegram_update()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = HTTPStatus.ACCEPTED

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            await sales_agent_client.forward_update("test-connector", bot_config, update)

            call_args = mock_client.post.call_args[0]
            assert call_args[0].endswith("/messages/inbound")


class TestNormalizeUpdate:
    """Test _normalize_update method."""

    def test_normalize_text_message(self, sales_agent_client: BackendInboundClient) -> None:
        update = _make_telegram_update(text="Hello world", chat_id=111, user_id=222)
        envelope = sales_agent_client._normalize_update(update)

        assert envelope is not None
        assert envelope.conversation_id == "111"
        assert envelope.user_id == "222"
        assert envelope.text == "Hello world"
        assert envelope.artifact_ids == []

    def test_normalize_edited_message(self, sales_agent_client: BackendInboundClient) -> None:
        update = {
            "edited_message": {
                "message_id": 1,
                "date": int(time.time()),
                "chat": {"id": 333, "type": "private"},
                "from": {"id": 444, "is_bot": False},
                "text": "Edited text",
            }
        }
        envelope = sales_agent_client._normalize_update(update)

        assert envelope is not None
        assert envelope.conversation_id == "333"
        assert envelope.text == "Edited text"

    def test_normalize_channel_post(self, sales_agent_client: BackendInboundClient) -> None:
        update = {
            "channel_post": {
                "message_id": 1,
                "date": int(time.time()),
                "chat": {"id": -100123, "type": "channel"},
                "text": "Channel message",
            }
        }
        envelope = sales_agent_client._normalize_update(update)

        assert envelope is not None
        assert envelope.conversation_id == "-100123"
        # user_id falls back to chat_id when no "from" field
        assert envelope.user_id == "-100123"

    def test_normalize_callback_query(self, sales_agent_client: BackendInboundClient) -> None:
        update = {
            "callback_query": {
                "id": "query123",
                "from": {"id": 555, "is_bot": False},
                "message": {
                    "message_id": 1,
                    "date": int(time.time()),
                    "chat": {"id": 666, "type": "private"},
                    "text": "Button text",
                },
            }
        }
        envelope = sales_agent_client._normalize_update(update)

        assert envelope is not None
        assert envelope.conversation_id == "666"

    def test_normalize_missing_chat(self, sales_agent_client: BackendInboundClient) -> None:
        update = {"message": {"text": "No chat"}}
        envelope = sales_agent_client._normalize_update(update)
        assert envelope is None

    def test_normalize_missing_chat_id(self, sales_agent_client: BackendInboundClient) -> None:
        update = {"message": {"chat": {}, "text": "No chat id"}}
        envelope = sales_agent_client._normalize_update(update)
        assert envelope is None

    def test_normalize_unsupported_update(self, sales_agent_client: BackendInboundClient) -> None:
        update = {"inline_query": {"id": "123", "query": "search"}}
        envelope = sales_agent_client._normalize_update(update)
        assert envelope is None

    def test_normalize_caption(self, sales_agent_client: BackendInboundClient) -> None:
        update = {
            "message": {
                "message_id": 1,
                "date": int(time.time()),
                "chat": {"id": 777, "type": "private"},
                "from": {"id": 888, "is_bot": False},
                "photo": [{"file_id": "xxx"}],
                "caption": "Photo caption",
            }
        }
        envelope = sales_agent_client._normalize_update(update)

        assert envelope is not None
        assert envelope.text == "Photo caption"
