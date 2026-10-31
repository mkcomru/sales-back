from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from wazzup_module.services.wazzup_api import WazzupApiClient, WazzupApiError


@pytest.fixture
def wazzup_client() -> WazzupApiClient:
    return WazzupApiClient(api_base_url="https://api.wazzup.test/v3")


class TestSendMessage:
    @pytest.mark.anyio
    async def test_send_message_success(self, wazzup_client: WazzupApiClient) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"status":"ok"}'
        mock_response.json.return_value = {"status": "ok"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            result = await wazzup_client.send_message(
                api_key="test-key",  # pragma: allowlist secret
                channel_id="chan-1",
                chat_id="user-1",
                chat_type="instagram",
                text="Hello",
            )

        assert result == {"status": "ok"}

    @pytest.mark.anyio
    async def test_send_message_with_crm_message_id(self, wazzup_client: WazzupApiClient) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"{}"
        mock_response.json.return_value = {}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            await wazzup_client.send_message(
                api_key="test-key",  # pragma: allowlist secret
                channel_id="chan-1",
                chat_id="user-1",
                chat_type="instagram",
                text="Hello",
                crm_message_id="corr-1:0",
            )

        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs["json"]
        assert payload["crmMessageId"] == "corr-1:0"

    @pytest.mark.anyio
    async def test_send_message_api_error(self, wazzup_client: WazzupApiClient) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            with pytest.raises(WazzupApiError, match="400"):
                await wazzup_client.send_message(
                    api_key="test-key",  # pragma: allowlist secret
                    channel_id="chan-1",
                    chat_id="user-1",
                    chat_type="instagram",
                    text="Hello",
                )

    @pytest.mark.anyio
    async def test_send_message_http_error(self, wazzup_client: WazzupApiClient) -> None:
        with patch(
            "httpx.AsyncClient.post",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            with pytest.raises(WazzupApiError, match="request failed"):
                await wazzup_client.send_message(
                    api_key="test-key",  # pragma: allowlist secret
                    channel_id="chan-1",
                    chat_id="user-1",
                    chat_type="instagram",
                    text="Hello",
                )

    @pytest.mark.anyio
    async def test_send_message_empty_response(self, wazzup_client: WazzupApiClient) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b""

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            result = await wazzup_client.send_message(
                api_key="test-key",  # pragma: allowlist secret
                channel_id="chan-1",
                chat_id="user-1",
                chat_type="instagram",
                text="Hello",
            )

        assert result == {}


class TestRegisterWebhook:
    @pytest.mark.anyio
    async def test_register_webhook_success(self, wazzup_client: WazzupApiClient) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient.patch", new_callable=AsyncMock, return_value=mock_response) as mock_patch:
            await wazzup_client.register_webhook(
                api_key="test-key",  # pragma: allowlist secret
                webhook_uri="https://example.com/webhook",
            )

        call_kwargs = mock_patch.call_args
        assert call_kwargs.kwargs["json"]["webhooksUri"] == "https://example.com/webhook"
        assert call_kwargs.kwargs["json"]["subscriptions"]["messagesAndStatuses"] is True

    @pytest.mark.anyio
    async def test_register_webhook_api_error(self, wazzup_client: WazzupApiClient) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"

        with patch("httpx.AsyncClient.patch", new_callable=AsyncMock, return_value=mock_response):
            with pytest.raises(WazzupApiError, match="registration failed"):
                await wazzup_client.register_webhook(
                    api_key="bad-key",  # pragma: allowlist secret
                    webhook_uri="https://example.com/webhook",
                )

    @pytest.mark.anyio
    async def test_register_webhook_http_error(self, wazzup_client: WazzupApiClient) -> None:
        with patch(
            "httpx.AsyncClient.patch",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            with pytest.raises(WazzupApiError, match="request failed"):
                await wazzup_client.register_webhook(
                    api_key="test-key",  # pragma: allowlist secret
                    webhook_uri="https://example.com/webhook",
                )
