"""Tests for WappiApiClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from wappi_module.services.wappi_api import WappiApiClient, WappiApiError


class TestWappiApiClient:
    @pytest.mark.asyncio
    async def test_send_message_success(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "sent", "message_id": "msg123"}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await client.send_message(
                wappi_token="token",
                profile_id="profile123",
                recipient="351311665",
                body="Test message",
                channel_type="telegram",
            )

        assert result == {"status": "sent", "message_id": "msg123"}
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://wappi.test/tapi/async/message/send"
        assert call_args[1]["json"] == {
            "body": "Test message",
            "recipient": "351311665",
        }
        assert call_args[1]["params"] == {"profile_id": "profile123"}
        assert call_args[1]["headers"]["Authorization"] == "token"

    @pytest.mark.asyncio
    async def test_send_message_http_status_error(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")

        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        mock_error = httpx.HTTPStatusError("Bad request", request=AsyncMock(), response=mock_response)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(side_effect=mock_error)
            mock_client_class.return_value = mock_client

            with pytest.raises(WappiApiError, match="400"):
                await client.send_message(
                    wappi_token="token",
                    profile_id="profile123",
                    recipient="351311665",
                    body="Test",
                    channel_type="telegram",
                )

    @pytest.mark.asyncio
    async def test_send_message_http_error(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(side_effect=httpx.RequestError("Connection failed", request=AsyncMock()))
            mock_client_class.return_value = mock_client

            with pytest.raises(WappiApiError, match="Failed to send message"):
                await client.send_message(
                    wappi_token="token",
                    profile_id="profile123",
                    recipient="351311665",
                    body="Test",
                    channel_type="telegram",
                )

    @pytest.mark.asyncio
    async def test_send_message_with_custom_base_url(self) -> None:
        client = WappiApiClient(api_base_url="https://custom.wappi.test")

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.send_message(
                wappi_token="token",
                profile_id="profile",
                recipient="123",
                body="Test",
                channel_type="telegram",
            )

        call_args = mock_client.post.call_args
        assert call_args[0][0].startswith("https://custom.wappi.test")

    @pytest.mark.asyncio
    async def test_send_message_strips_trailing_slash_from_url(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test/")

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.send_message(
                wappi_token="token",
                profile_id="profile",
                recipient="123",
                body="Test",
                channel_type="telegram",
            )

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://wappi.test/tapi/async/message/send"

    @pytest.mark.asyncio
    async def test_send_message_rate_limit_429(self) -> None:
        client = WappiApiClient()

        mock_response = AsyncMock()
        mock_response.status_code = 429
        mock_response.text = "Too many requests"
        mock_error = httpx.HTTPStatusError("Rate limited", request=AsyncMock(), response=mock_response)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(side_effect=mock_error)
            mock_client_class.return_value = mock_client

            with pytest.raises(WappiApiError, match="429"):
                await client.send_message(
                    wappi_token="token",
                    profile_id="profile",
                    recipient="123",
                    body="Test",
                    channel_type="telegram",
                )

    @pytest.mark.asyncio
    async def test_get_chats_list_success(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "done",
            "dialogs": [
                {"id": "1645157187", "name": "Chat 1"},
                {"id": "1645157188", "name": "Chat 2"},
            ],
            "total_count": 2,
        }
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await client.get_chats_list(
                wappi_token="token",
                profile_id="profile123",
            )

        assert result["status"] == "done"
        assert len(result["dialogs"]) == 2
        assert result["total_count"] == 2
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert call_args[0][0] == "https://wappi.test/tapi/sync/chats/get"
        assert call_args[1]["params"] == {"profile_id": "profile123"}
        assert call_args[1]["headers"]["Authorization"] == "token"

    @pytest.mark.asyncio
    async def test_get_chats_list_with_limit(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "done", "dialogs": []}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.get_chats_list(
                wappi_token="token",
                profile_id="profile123",
                limit=50,
            )

        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["limit"] == 50

    @pytest.mark.asyncio
    async def test_get_chats_list_with_offset(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "done", "dialogs": []}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.get_chats_list(
                wappi_token="token",
                profile_id="profile123",
                offset=10,
            )

        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["offset"] == 10

    @pytest.mark.asyncio
    async def test_get_chats_list_with_show_all(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "done", "dialogs": []}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.get_chats_list(
                wappi_token="token",
                profile_id="profile123",
                show_all=True,
            )

        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["show_all"] == "true"

    @pytest.mark.asyncio
    async def test_get_chats_list_skips_offset_zero(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "done", "dialogs": []}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.get_chats_list(
                wappi_token="token",
                profile_id="profile123",
                offset=0,
            )

        call_args = mock_client.get.call_args
        assert "offset" not in call_args[1]["params"]

    @pytest.mark.asyncio
    async def test_get_chats_list_http_error(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")

        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.text = "Server error"
        mock_error = httpx.HTTPStatusError("Server error", request=AsyncMock(), response=mock_response)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(side_effect=mock_error)
            mock_client_class.return_value = mock_client

            with pytest.raises(WappiApiError, match="Failed to fetch chats"):
                await client.get_chats_list(
                    wappi_token="token",
                    profile_id="profile123",
                )

    @pytest.mark.asyncio
    async def test_get_chat_messages_success(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "done",
            "messages": [
                {
                    "id": "2910",
                    "fromMe": True,
                    "body": "Текст",
                    "time": 1709456814,
                    "chatId": "89323786",
                }
            ],
            "total_count": 1,
        }
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await client.get_chat_messages(
                wappi_token="token",
                profile_id="profile123",
                chat_id="89323786",
            )

        assert result["status"] == "done"
        assert len(result["messages"]) == 1
        assert result["total_count"] == 1
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert call_args[0][0] == "https://wappi.test/tapi/sync/messages/get"
        assert call_args[1]["params"]["profile_id"] == "profile123"
        assert call_args[1]["params"]["chat_id"] == "89323786"
        assert call_args[1]["params"]["limit"] == 100
        assert call_args[1]["params"]["offset"] == 0
        assert call_args[1]["params"]["order"] == "desc"

    @pytest.mark.asyncio
    async def test_get_chat_messages_with_custom_params(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "done", "messages": []}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.get_chat_messages(
                wappi_token="token",
                profile_id="profile123",
                chat_id=89323786,
                limit=50,
                offset=10,
                order="asc",
            )

        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["limit"] == 50
        assert call_args[1]["params"]["offset"] == 10
        assert call_args[1]["params"]["order"] == "asc"
        assert call_args[1]["params"]["chat_id"] == "89323786"

    @pytest.mark.asyncio
    async def test_get_chat_messages_limits_max_100(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "done", "messages": []}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.get_chat_messages(
                wappi_token="token",
                profile_id="profile123",
                chat_id="89323786",
                limit=200,
            )

        call_args = mock_client.get.call_args
        assert call_args[1]["params"]["limit"] == 100

    @pytest.mark.asyncio
    async def test_get_chat_messages_http_error(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(side_effect=httpx.HTTPError("Connection failed"))
            mock_client_class.return_value = mock_client

            with pytest.raises(WappiApiError, match="Failed to fetch messages"):
                await client.get_chat_messages(
                    wappi_token="token",
                    profile_id="profile123",
                    chat_id="89323786",
                )


class TestApiPrefix:
    def test_telegram_prefix(self) -> None:
        assert WappiApiClient()._api_prefix("telegram") == "tapi"

    def test_whatsapp_prefix(self) -> None:
        assert WappiApiClient()._api_prefix("whatsapp") == "api"

    def test_vk_prefix(self) -> None:
        assert WappiApiClient()._api_prefix("vk") == "vkapi"

    def test_unknown_raises(self) -> None:
        with pytest.raises(WappiApiError, match="Unsupported channel_type"):
            WappiApiClient()._api_prefix("unknown")

    def test_case_insensitive(self) -> None:
        assert WappiApiClient()._api_prefix("VK") == "vkapi"
        assert WappiApiClient()._api_prefix("Telegram") == "tapi"


class TestVkChannel:
    @pytest.mark.asyncio
    async def test_send_message_vk_uses_vkapi_endpoint(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "sent"}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.send_message(
                wappi_token="token",
                profile_id="profile123",
                recipient="863567278",
                body="test",
                channel_type="vk",
            )

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://wappi.test/vkapi/async/message/send"

    @pytest.mark.asyncio
    async def test_get_chats_list_vk_uses_post(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "done", "dialogs": [], "total_count": 0}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.get_chats_list(
                wappi_token="token",
                profile_id="profile123",
                channel_type="vk",
            )

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://wappi.test/vkapi/sync/chats/get"

    @pytest.mark.asyncio
    async def test_get_chat_messages_vk_uses_get(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "done", "messages": [], "total_count": 0}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.get_chat_messages(
                wappi_token="token",
                profile_id="profile123",
                chat_id="863567278",
                channel_type="vk",
            )

        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert call_args[0][0] == "https://wappi.test/vkapi/sync/messages/get"


class TestWappiApiClientMedia:
    @pytest.mark.asyncio
    async def test_send_image_telegram_url(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")
        file_bytes = b"fake_image_data"

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "sent"}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await client.send_image(
                wappi_token="token",
                profile_id="profile123",
                recipient="123456",
                file_bytes=file_bytes,
                channel_type="telegram",
            )

        assert result == {"status": "sent"}
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://wappi.test/tapi/sync/message/img/send"
        assert call_args[1]["json"]["recipient"] == "123456"
        assert "b64_file" in call_args[1]["json"]
        assert call_args[1]["headers"]["Authorization"] == "token"

    @pytest.mark.asyncio
    async def test_send_image_whatsapp_url(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")
        file_bytes = b"fake_image_data"

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "sent"}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.send_image(
                wappi_token="token",
                profile_id="profile123",
                recipient="79001234567",
                file_bytes=file_bytes,
                channel_type="whatsapp",
            )

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://wappi.test/api/sync/message/img/send"

    @pytest.mark.asyncio
    async def test_send_image_with_caption(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")
        file_bytes = b"fake_image_data"

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "sent"}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.send_image(
                wappi_token="token",
                profile_id="profile123",
                recipient="123",
                file_bytes=file_bytes,
                channel_type="telegram",
                caption="My photo",
            )

        call_args = mock_client.post.call_args
        assert call_args[1]["json"]["caption"] == "My photo"

    @pytest.mark.asyncio
    async def test_send_image_no_caption_omitted(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "sent"}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.send_image(
                wappi_token="token",
                profile_id="profile123",
                recipient="123",
                file_bytes=b"data",
                channel_type="telegram",
            )

        call_args = mock_client.post.call_args
        assert "caption" not in call_args[1]["json"]

    @pytest.mark.asyncio
    async def test_send_audio_telegram_url(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "sent"}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.send_audio(
                wappi_token="token",
                profile_id="profile123",
                recipient="123",
                file_bytes=b"audio_data",
                channel_type="telegram",
            )

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://wappi.test/tapi/sync/message/audio/send"

    @pytest.mark.asyncio
    async def test_send_document_includes_filename(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "sent"}
        mock_response.raise_for_status = MagicMock()

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            await client.send_document(
                wappi_token="token",
                profile_id="profile123",
                recipient="123",
                file_bytes=b"pdf_data",
                channel_type="whatsapp",
                filename="report.pdf",
            )

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://wappi.test/api/sync/message/document/send"
        assert call_args[1]["json"]["file_name"] == "report.pdf"

    @pytest.mark.asyncio
    async def test_send_media_http_status_error(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")

        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        mock_error = httpx.HTTPStatusError("Bad request", request=AsyncMock(), response=mock_response)

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(side_effect=mock_error)
            mock_client_class.return_value = mock_client

            with pytest.raises(WappiApiError, match="400"):
                await client.send_image(
                    wappi_token="token",
                    profile_id="profile123",
                    recipient="123",
                    file_bytes=b"data",
                    channel_type="telegram",
                )

    @pytest.mark.asyncio
    async def test_send_media_http_error(self) -> None:
        client = WappiApiClient(api_base_url="https://wappi.test")

        with patch("wappi_module.services.wappi_api.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post = AsyncMock(side_effect=httpx.RequestError("Connection failed", request=AsyncMock()))
            mock_client_class.return_value = mock_client

            with pytest.raises(WappiApiError, match="Failed to send media"):
                await client.send_audio(
                    wappi_token="token",
                    profile_id="profile123",
                    recipient="123",
                    file_bytes=b"data",
                    channel_type="telegram",
                )
