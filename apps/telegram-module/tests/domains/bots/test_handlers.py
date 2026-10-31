"""Tests for message handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Router
from aiogram.types import Chat, Document, Message, PhotoSize
from aiogram.types import User as TelegramUser

from common import AudioConversionService, FileType
from telegram_module.bots.handlers.message import create_message_handler_router
from telegram_module.bots.models import BotConfig
from telegram_module.services.backend import TransportBackendClient
from telegram_module.services.sales_agent import BackendInboundClient, BackendInboundClientError


@pytest.fixture
def bot_config() -> BotConfig:
    return BotConfig(
        connector_id="test-connector",
        company_id="1",
        bot_token="123456:ABC-DEF",  # pragma: allowlist secret
    )


@pytest.fixture
def mock_sales_agent() -> AsyncMock:
    return AsyncMock(spec=BackendInboundClient)


@pytest.fixture
def mock_backend_client() -> AsyncMock:
    return AsyncMock(spec=TransportBackendClient)


@pytest.fixture
def audio_converter() -> AudioConversionService:
    return AudioConversionService()


class TestMessageHandlers:
    """Test message handler router creation and handling."""

    def test_create_message_handler_router_returns_router(
        self,
        bot_config: BotConfig,
        mock_sales_agent: AsyncMock,
        mock_backend_client: AsyncMock,
        audio_converter: AudioConversionService,
    ) -> None:
        router = create_message_handler_router(bot_config, mock_sales_agent, mock_backend_client, audio_converter)

        assert isinstance(router, Router)
        assert router.name == "bot_test-connector"

    @pytest.mark.asyncio
    async def test_message_handler_forwards_to_sales_agent(
        self,
        bot_config: BotConfig,
        mock_sales_agent: AsyncMock,
        mock_backend_client: AsyncMock,
        audio_converter: AudioConversionService,
    ) -> None:
        router = create_message_handler_router(bot_config, mock_sales_agent, mock_backend_client, audio_converter)

        telegram_user = TelegramUser(
            id=123,
            is_bot=False,
            first_name="Test",
        )
        chat = Chat(id=456, type="private")
        message = Message(
            message_id=1,
            date=1234567890,
            chat=chat,
            from_user=telegram_user,
            text="Hello",
        )

        handler = router.message.handlers[0]
        await handler.callback(message)

        mock_sales_agent.forward_update.assert_called_once()
        call_args = mock_sales_agent.forward_update.call_args
        assert call_args[0][0] == "test-connector"
        assert call_args[0][1] == bot_config
        assert "message" in call_args[0][2]

    @pytest.mark.asyncio
    async def test_message_handler_handles_sales_agent_error(
        self,
        bot_config: BotConfig,
        mock_sales_agent: AsyncMock,
        mock_backend_client: AsyncMock,
        audio_converter: AudioConversionService,
    ) -> None:
        router = create_message_handler_router(bot_config, mock_sales_agent, mock_backend_client, audio_converter)

        mock_sales_agent.forward_update.side_effect = BackendInboundClientError("Sales agent error")

        telegram_user = TelegramUser(
            id=123,
            is_bot=False,
            first_name="Test",
        )
        chat = Chat(id=456, type="private")
        message = Message(
            message_id=1,
            date=1234567890,
            chat=chat,
            from_user=telegram_user,
            text="Hello",
        )

        handler = router.message.handlers[0]

        with pytest.raises(BackendInboundClientError):
            await handler.callback(message)

    @pytest.mark.asyncio
    async def test_message_handler_photo_uploads_and_sets_artifact_ids(
        self,
        bot_config: BotConfig,
        mock_sales_agent: AsyncMock,
        mock_backend_client: AsyncMock,
        audio_converter: AudioConversionService,
    ) -> None:
        mock_backend_client.upload_artifact = AsyncMock(return_value="artifact-photo-1")

        with patch("telegram_module.bots.handlers.message.TelegramFileDownloader") as mock_dl_cls:
            mock_dl = mock_dl_cls.return_value
            mock_dl.download_bot_file = AsyncMock(return_value=b"\xff\xd8\xff")

            router = create_message_handler_router(bot_config, mock_sales_agent, mock_backend_client, audio_converter)
            handler = router.message.handlers[0]

            telegram_user = TelegramUser(id=123, is_bot=False, first_name="Test")
            chat = Chat(id=456, type="private")
            photo = (
                PhotoSize(file_id="small", file_unique_id="a", width=10, height=10, file_size=100),
                PhotoSize(file_id="big", file_unique_id="b", width=200, height=200, file_size=50000),
            )
            message = Message(
                message_id=1,
                date=1234567890,
                chat=chat,
                from_user=telegram_user,
                photo=photo,
            )

            await handler.callback(message)

            mock_dl.download_bot_file.assert_awaited_once()
            assert mock_dl.download_bot_file.await_args.args[1] == "big"

            mock_backend_client.upload_artifact.assert_awaited_once_with(
                file_bytes=b"\xff\xd8\xff",
                file_type=FileType.IMAGE,
                company_id=1,
                connector_id="test-connector",
            )

            payload = mock_sales_agent.forward_update.call_args[0][2]
            assert payload["message"]["artifact_ids"] == ["artifact-photo-1"]

    @pytest.mark.asyncio
    async def test_message_handler_image_document_uploads_and_sets_artifact_ids(
        self,
        bot_config: BotConfig,
        mock_sales_agent: AsyncMock,
        mock_backend_client: AsyncMock,
        audio_converter: AudioConversionService,
    ) -> None:
        mock_backend_client.upload_artifact = AsyncMock(return_value="artifact-doc-1")

        with patch("telegram_module.bots.handlers.message.TelegramFileDownloader") as mock_dl_cls:
            mock_dl = mock_dl_cls.return_value
            mock_dl.download_bot_file = AsyncMock(return_value=b"png-bytes")

            router = create_message_handler_router(bot_config, mock_sales_agent, mock_backend_client, audio_converter)
            handler = router.message.handlers[0]

            telegram_user = TelegramUser(id=123, is_bot=False, first_name="Test")
            chat = Chat(id=456, type="private")
            document = Document(
                file_id="doc-file",
                file_unique_id="uq",
                mime_type="image/png",
                file_name="x.png",
            )
            message = Message(
                message_id=1,
                date=1234567890,
                chat=chat,
                from_user=telegram_user,
                document=document,
            )

            await handler.callback(message)

            mock_dl.download_bot_file.assert_awaited_once_with(
                bot_config.bot_token.get_secret_value(),
                "doc-file",
            )
            mock_backend_client.upload_artifact.assert_awaited_once_with(
                file_bytes=b"png-bytes",
                file_type=FileType.IMAGE,
                company_id=1,
                connector_id="test-connector",
            )
            payload = mock_sales_agent.forward_update.call_args[0][2]
            assert payload["message"]["artifact_ids"] == ["artifact-doc-1"]
