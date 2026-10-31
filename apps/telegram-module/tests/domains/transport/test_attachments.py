"""Tests for attachment delivery in TransportDeliveryService (Telegram)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter, TelegramServerError

from common.models.transport import AttachmentDescriptor
from common.transport.base_backend_client import TransportBackendClientError
from telegram_module.bots.manager import BotRuntime
from telegram_module.bots.models import BotConfig, BotMode
from telegram_module.config import Settings
from telegram_module.services.backend import TransportBackendClient
from telegram_module.transport.models import TransportDeliveryPayload
from telegram_module.transport.service import TransportDeliveryError, TransportDeliveryService


@pytest.fixture
def bot_config() -> BotConfig:
    from pydantic import SecretStr

    return BotConfig(
        connector_id="test-connector",
        company_id="test-company",
        bot_token=SecretStr("123456:ABC-DEF"),  # pragma: allowlist secret
    )


@pytest.fixture
def bot_runtime(bot_config: BotConfig) -> BotRuntime:
    with (
        patch("telegram_module.bots.manager.Bot") as mock_bot_class,
        patch("telegram_module.bots.manager.Dispatcher"),
    ):
        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot
        return BotRuntime(
            config=bot_config,
            mode=BotMode.POLLING,
            bot=mock_bot,
            dispatcher=MagicMock(),
            webhook_path=None,
        )


@pytest.fixture
def bot_manager(bot_runtime: BotRuntime) -> MagicMock:
    manager = MagicMock()
    manager.get.return_value = bot_runtime
    return manager


@pytest.fixture
def backend_client() -> MagicMock:
    return MagicMock(spec=TransportBackendClient)


@pytest.fixture
def transport_service(
    settings: Settings,
    bot_manager: MagicMock,
    backend_client: MagicMock,
) -> TransportDeliveryService:
    return TransportDeliveryService(settings, bot_manager, backend_client)


@pytest.fixture
def attachment_payload() -> TransportDeliveryPayload:
    return TransportDeliveryPayload(
        connector_id="test-connector",
        company_id="test-company",
        channel_type="telegram",
        user_id="user-123",
        conversation_id="conv-456",
        correlation_id="corr-attach",
        metadata={"chat_id": "123456"},
        attachments=[
            AttachmentDescriptor(
                artifact_id="art-001",
                type="image",
                mime_type="image/jpeg",
                caption="A photo",
            )
        ],
    )


class TestAttachmentDelivery:
    @pytest.mark.asyncio
    async def test_deliver_image_calls_send_photo(
        self,
        transport_service: TransportDeliveryService,
        bot_runtime: BotRuntime,
        backend_client: MagicMock,
        attachment_payload: TransportDeliveryPayload,
    ) -> None:
        file_bytes = b"fake_image"
        backend_client.download_artifact = AsyncMock(return_value=file_bytes)
        bot_runtime.bot.send_photo = AsyncMock()

        await transport_service._deliver_replies(bot_runtime, attachment_payload)

        backend_client.download_artifact.assert_called_once_with("art-001")
        bot_runtime.bot.send_photo.assert_called_once()
        call_kwargs = bot_runtime.bot.send_photo.call_args[1]
        assert call_kwargs["chat_id"] == "123456"
        assert call_kwargs["caption"] == "A photo"

    @pytest.mark.asyncio
    async def test_deliver_audio_calls_send_audio(
        self,
        transport_service: TransportDeliveryService,
        bot_runtime: BotRuntime,
        backend_client: MagicMock,
    ) -> None:
        file_bytes = b"fake_audio"
        backend_client.download_artifact = AsyncMock(return_value=file_bytes)
        bot_runtime.bot.send_audio = AsyncMock()

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="test-company",
            channel_type="telegram",
            user_id="user-123",
            conversation_id="conv-456",
            correlation_id="corr-audio",
            metadata={"chat_id": "123456"},
            attachments=[AttachmentDescriptor(artifact_id="art-audio", type="audio", mime_type="audio/mpeg")],
        )

        await transport_service._deliver_replies(bot_runtime, payload)

        bot_runtime.bot.send_audio.assert_called_once()
        call_kwargs = bot_runtime.bot.send_audio.call_args[1]
        assert call_kwargs["chat_id"] == "123456"

    @pytest.mark.asyncio
    async def test_deliver_voice_calls_send_voice(
        self,
        transport_service: TransportDeliveryService,
        bot_runtime: BotRuntime,
        backend_client: MagicMock,
    ) -> None:
        file_bytes = b"fake_voice"
        backend_client.download_artifact = AsyncMock(return_value=file_bytes)
        bot_runtime.bot.send_voice = AsyncMock()

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="test-company",
            channel_type="telegram",
            user_id="user-123",
            conversation_id="conv-456",
            correlation_id="corr-voice",
            metadata={"chat_id": "123456"},
            attachments=[AttachmentDescriptor(artifact_id="art-voice", type="voice", mime_type="audio/mpeg")],
        )

        await transport_service._deliver_replies(bot_runtime, payload)

        bot_runtime.bot.send_voice.assert_called_once()
        call_kwargs = bot_runtime.bot.send_voice.call_args[1]
        assert call_kwargs["chat_id"] == "123456"

    @pytest.mark.asyncio
    async def test_deliver_document_calls_send_document(
        self,
        transport_service: TransportDeliveryService,
        bot_runtime: BotRuntime,
        backend_client: MagicMock,
    ) -> None:
        file_bytes = b"fake_pdf"
        backend_client.download_artifact = AsyncMock(return_value=file_bytes)
        bot_runtime.bot.send_document = AsyncMock()

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="test-company",
            channel_type="telegram",
            user_id="user-123",
            conversation_id="conv-456",
            correlation_id="corr-doc",
            metadata={"chat_id": "123456"},
            attachments=[
                AttachmentDescriptor(
                    artifact_id="art-doc",
                    type="document",
                    mime_type="application/pdf",
                    caption="A document",
                )
            ],
        )

        await transport_service._deliver_replies(bot_runtime, payload)

        bot_runtime.bot.send_document.assert_called_once()
        call_kwargs = bot_runtime.bot.send_document.call_args[1]
        assert call_kwargs["caption"] == "A document"

    @pytest.mark.asyncio
    async def test_deliver_attachment_download_failure(
        self,
        transport_service: TransportDeliveryService,
        bot_runtime: BotRuntime,
        backend_client: MagicMock,
        attachment_payload: TransportDeliveryPayload,
    ) -> None:
        backend_client.download_artifact = AsyncMock(side_effect=TransportBackendClientError("S3 error"))

        with pytest.raises(TransportDeliveryError, match="Failed to download artifact art-001"):
            await transport_service._deliver_replies(bot_runtime, attachment_payload)

    @pytest.mark.asyncio
    async def test_deliver_attachment_unsupported_type(
        self,
        transport_service: TransportDeliveryService,
        bot_runtime: BotRuntime,
        backend_client: MagicMock,
    ) -> None:
        backend_client.download_artifact = AsyncMock(return_value=b"data")

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="test-company",
            channel_type="telegram",
            user_id="user-123",
            conversation_id="conv-456",
            correlation_id="corr-vid",
            metadata={"chat_id": "123456"},
            attachments=[AttachmentDescriptor(artifact_id="art-vid", type="video", mime_type="video/mp4")],
        )

        with pytest.raises(TransportDeliveryError, match="Unsupported attachment type for Telegram"):
            await transport_service._deliver_replies(bot_runtime, payload)

    @pytest.mark.asyncio
    async def test_deliver_attachment_retries_on_retry_after(
        self,
        transport_service: TransportDeliveryService,
        bot_runtime: BotRuntime,
        backend_client: MagicMock,
        attachment_payload: TransportDeliveryPayload,
    ) -> None:
        backend_client.download_artifact = AsyncMock(return_value=b"img_bytes")
        bot_runtime.bot.send_photo = AsyncMock(
            side_effect=[
                TelegramRetryAfter(method="sendPhoto", message="Rate limit", retry_after=1),
                None,
            ]
        )

        await transport_service._deliver_replies(bot_runtime, attachment_payload)

        assert bot_runtime.bot.send_photo.call_count == 2

    @pytest.mark.asyncio
    async def test_deliver_attachment_retries_on_server_error(
        self,
        transport_service: TransportDeliveryService,
        bot_runtime: BotRuntime,
        backend_client: MagicMock,
        attachment_payload: TransportDeliveryPayload,
    ) -> None:
        backend_client.download_artifact = AsyncMock(return_value=b"img_bytes")
        bot_runtime.bot.send_photo = AsyncMock(
            side_effect=[
                TelegramServerError(method="sendPhoto", message="Server error"),
                None,
            ]
        )

        await transport_service._deliver_replies(bot_runtime, attachment_payload)

        assert bot_runtime.bot.send_photo.call_count == 2

    @pytest.mark.asyncio
    async def test_deliver_attachment_bad_request_raises(
        self,
        transport_service: TransportDeliveryService,
        bot_runtime: BotRuntime,
        backend_client: MagicMock,
        attachment_payload: TransportDeliveryPayload,
    ) -> None:
        backend_client.download_artifact = AsyncMock(return_value=b"img_bytes")
        bot_runtime.bot.send_photo = AsyncMock(
            side_effect=TelegramBadRequest(method="sendPhoto", message="Bad request")
        )

        with pytest.raises(TransportDeliveryError, match="Telegram API rejected attachment"):
            await transport_service._deliver_replies(bot_runtime, attachment_payload)

    @pytest.mark.asyncio
    async def test_deliver_text_and_image_together(
        self,
        transport_service: TransportDeliveryService,
        bot_runtime: BotRuntime,
        backend_client: MagicMock,
    ) -> None:
        backend_client.download_artifact = AsyncMock(return_value=b"img_bytes")
        bot_runtime.bot.send_message = AsyncMock()
        bot_runtime.bot.send_photo = AsyncMock()

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="test-company",
            channel_type="telegram",
            user_id="user-123",
            conversation_id="conv-456",
            correlation_id="corr-combined",
            replies=["Here is your photo:"],
            metadata={"chat_id": "123456"},
            attachments=[AttachmentDescriptor(artifact_id="art-img", type="image", mime_type="image/png")],
        )

        await transport_service._deliver_replies(bot_runtime, payload)

        bot_runtime.bot.send_message.assert_called_once()
        bot_runtime.bot.send_photo.assert_called_once()

    @pytest.mark.asyncio
    async def test_deliver_attachment_with_thread_id(
        self,
        transport_service: TransportDeliveryService,
        bot_runtime: BotRuntime,
        backend_client: MagicMock,
    ) -> None:
        backend_client.download_artifact = AsyncMock(return_value=b"img_bytes")
        bot_runtime.bot.send_photo = AsyncMock()

        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="test-company",
            channel_type="telegram",
            user_id="user-123",
            conversation_id="conv-456",
            correlation_id="corr-thread",
            metadata={"chat_id": "123456", "message_thread_id": "42"},
            attachments=[AttachmentDescriptor(artifact_id="art-thread", type="image", mime_type="image/jpeg")],
        )

        await transport_service._deliver_replies(bot_runtime, payload)

        bot_runtime.bot.send_photo.assert_called_once()
        call_kwargs = bot_runtime.bot.send_photo.call_args[1]
        assert call_kwargs["message_thread_id"] == "42"
