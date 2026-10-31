"""Tests for TransportDeliveryService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramRetryAfter,
    TelegramServerError,
)
from fastapi import HTTPException, status

from telegram_module.bots.manager import BotManager, BotRuntime
from telegram_module.bots.models import BotConfig, BotMode
from telegram_module.config import Settings
from telegram_module.services.backend import TransportBackendClient
from telegram_module.transport.models import TransportDeliveryPayload
from telegram_module.transport.service import TransportDeliveryService


@pytest.fixture
def bot_config() -> BotConfig:
    return BotConfig(
        connector_id="test-connector",
        company_id="test-company",
        bot_token="123456:ABC-DEF",  # pragma: allowlist secret
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
    manager = MagicMock(spec=BotManager)
    manager.get.return_value = bot_runtime
    return manager


@pytest.fixture
def backend_client(settings: Settings) -> MagicMock:
    return MagicMock(spec=TransportBackendClient)


@pytest.fixture
def transport_service(
    settings: Settings, bot_manager: MagicMock, backend_client: MagicMock
) -> TransportDeliveryService:
    return TransportDeliveryService(settings, bot_manager, backend_client)


@pytest.fixture
def delivery_payload() -> TransportDeliveryPayload:
    return TransportDeliveryPayload(
        connector_id="test-connector",
        company_id="test-company",
        channel_type="telegram",
        user_id="user-123",
        conversation_id="conv-456",
        correlation_id="corr-789",
        replies=["Hello"],
        metadata={"chat_id": "123456"},
    )


class TestTransportDeliveryService:
    """Test TransportDeliveryService functionality."""

    def test_transport_service_init(
        self, settings: Settings, bot_manager: MagicMock, backend_client: MagicMock
    ) -> None:
        service = TransportDeliveryService(settings, bot_manager, backend_client)

        assert service._bots is bot_manager
        assert service._idempotency is not None

    def test_transport_service_init_missing_api_key(self, backend_client: MagicMock) -> None:
        from pydantic import ValidationError

        try:
            test_settings = Settings(service__api_key=None)
        except ValidationError:
            pytest.skip("Settings validation prevents None API key")
            return

        if test_settings.service.api_key is None:
            with pytest.raises(RuntimeError, match="SERVICE__API_KEY must be configured"):
                TransportDeliveryService(test_settings, MagicMock(), backend_client)
        else:
            pytest.skip("Settings has default API key")

    @pytest.mark.asyncio
    async def test_handle_success(
        self,
        transport_service: TransportDeliveryService,
        delivery_payload: TransportDeliveryPayload,
        service_headers: dict[str, str],
        bot_runtime: BotRuntime,
    ) -> None:
        bot_runtime.bot.send_message = AsyncMock()

        headers = {
            **service_headers,
            "X-Connector-Id": "test-connector",
        }

        response = await transport_service.handle(payload=delivery_payload, headers=headers)

        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.body
        assert b"accepted" in data
        bot_runtime.bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_unknown_connector(
        self,
        transport_service: TransportDeliveryService,
        delivery_payload: TransportDeliveryPayload,
        service_headers: dict[str, str],
        bot_manager: MagicMock,
    ) -> None:
        bot_manager.get.return_value = None

        headers = {
            **service_headers,
            "X-Connector-Id": "test-connector",
        }

        with pytest.raises(HTTPException) as exc_info:
            await transport_service.handle(payload=delivery_payload, headers=headers)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_handle_missing_connector_header(
        self,
        transport_service: TransportDeliveryService,
        delivery_payload: TransportDeliveryPayload,
        service_headers: dict[str, str],
    ) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await transport_service.handle(payload=delivery_payload, headers=service_headers)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_handle_connector_mismatch(
        self,
        transport_service: TransportDeliveryService,
        delivery_payload: TransportDeliveryPayload,
        service_headers: dict[str, str],
    ) -> None:
        headers = {
            **service_headers,
            "X-Connector-Id": "different-connector",
        }

        with pytest.raises(HTTPException) as exc_info:
            await transport_service.handle(payload=delivery_payload, headers=headers)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_handle_missing_service_key(
        self,
        transport_service: TransportDeliveryService,
        delivery_payload: TransportDeliveryPayload,
    ) -> None:
        headers = {"X-Connector-Id": "test-connector"}

        with pytest.raises(HTTPException) as exc_info:
            await transport_service.handle(payload=delivery_payload, headers=headers)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_handle_invalid_service_key(
        self,
        transport_service: TransportDeliveryService,
        delivery_payload: TransportDeliveryPayload,
    ) -> None:
        headers = {
            "X-Service-Key": "wrong-key",  # pragma: allowlist secret
            "X-Connector-Id": "test-connector",
        }

        with pytest.raises(HTTPException) as exc_info:
            await transport_service.handle(payload=delivery_payload, headers=headers)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_handle_empty_correlation_id(
        self,
        transport_service: TransportDeliveryService,
        service_headers: dict[str, str],
        bot_runtime: BotRuntime,
    ) -> None:
        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="test-company",
            channel_type="telegram",
            user_id="user-123",
            conversation_id="conv-456",
            correlation_id="   ",
            replies=["Hello"],
            metadata={"chat_id": "123456"},
        )

        headers = {
            **service_headers,
            "X-Connector-Id": "test-connector",
        }

        with pytest.raises(HTTPException) as exc_info:
            await transport_service.handle(payload=payload, headers=headers)

        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    @pytest.mark.asyncio
    async def test_handle_duplicate_correlation_id(
        self,
        transport_service: TransportDeliveryService,
        delivery_payload: TransportDeliveryPayload,
        service_headers: dict[str, str],
        bot_runtime: BotRuntime,
    ) -> None:
        bot_runtime.bot.send_message = AsyncMock()

        headers = {
            **service_headers,
            "X-Connector-Id": "test-connector",
        }

        await transport_service.handle(payload=delivery_payload, headers=headers)

        response = await transport_service.handle(payload=delivery_payload, headers=headers)

        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.body
        assert b"duplicate" in data

    @pytest.mark.asyncio
    async def test_handle_missing_chat_id(
        self,
        transport_service: TransportDeliveryService,
        service_headers: dict[str, str],
        bot_runtime: BotRuntime,
    ) -> None:
        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="test-company",
            channel_type="telegram",
            user_id="user-123",
            conversation_id="conv-456",
            correlation_id="corr-789",
            replies=["Hello"],
            metadata={},
        )

        headers = {
            **service_headers,
            "X-Connector-Id": "test-connector",
        }

        with pytest.raises(HTTPException) as exc_info:
            await transport_service.handle(payload=payload, headers=headers)

        assert exc_info.value.status_code == status.HTTP_502_BAD_GATEWAY

    @pytest.mark.asyncio
    async def test_handle_telegram_retry_after(
        self,
        transport_service: TransportDeliveryService,
        delivery_payload: TransportDeliveryPayload,
        service_headers: dict[str, str],
        bot_runtime: BotRuntime,
    ) -> None:
        bot_runtime.bot.send_message = AsyncMock()
        bot_runtime.bot.send_message.side_effect = [
            TelegramRetryAfter(method="sendMessage", message="Rate limit", retry_after=1),
            None,
        ]

        headers = {
            **service_headers,
            "X-Connector-Id": "test-connector",
        }

        response = await transport_service.handle(payload=delivery_payload, headers=headers)

        assert response.status_code == status.HTTP_202_ACCEPTED
        assert bot_runtime.bot.send_message.call_count == 2

    @pytest.mark.asyncio
    async def test_handle_telegram_server_error(
        self,
        transport_service: TransportDeliveryService,
        delivery_payload: TransportDeliveryPayload,
        service_headers: dict[str, str],
        bot_runtime: BotRuntime,
    ) -> None:
        bot_runtime.bot.send_message = AsyncMock()
        bot_runtime.bot.send_message.side_effect = [
            TelegramServerError(method="sendMessage", message="Server error"),
            None,
        ]

        headers = {
            **service_headers,
            "X-Connector-Id": "test-connector",
        }

        response = await transport_service.handle(payload=delivery_payload, headers=headers)

        assert response.status_code == status.HTTP_202_ACCEPTED
        assert bot_runtime.bot.send_message.call_count == 2

    @pytest.mark.asyncio
    async def test_handle_telegram_bad_request(
        self,
        transport_service: TransportDeliveryService,
        delivery_payload: TransportDeliveryPayload,
        service_headers: dict[str, str],
        bot_runtime: BotRuntime,
    ) -> None:
        bot_runtime.bot.send_message = AsyncMock()
        bot_runtime.bot.send_message.side_effect = TelegramBadRequest(method="sendMessage", message="Bad request")

        headers = {
            **service_headers,
            "X-Connector-Id": "test-connector",
        }

        with pytest.raises(HTTPException) as exc_info:
            await transport_service.handle(payload=delivery_payload, headers=headers)

        assert exc_info.value.status_code == status.HTTP_502_BAD_GATEWAY

    @pytest.mark.asyncio
    async def test_handle_multiple_replies(
        self,
        transport_service: TransportDeliveryService,
        service_headers: dict[str, str],
        bot_runtime: BotRuntime,
    ) -> None:
        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="test-company",
            channel_type="telegram",
            user_id="user-123",
            conversation_id="conv-456",
            correlation_id="corr-789",
            replies=["Hello", "World", "Test"],
            metadata={"chat_id": "123456"},
        )

        bot_runtime.bot.send_message = AsyncMock()

        headers = {
            **service_headers,
            "X-Connector-Id": "test-connector",
        }

        await transport_service.handle(payload=payload, headers=headers)

        assert bot_runtime.bot.send_message.call_count == 3

    @pytest.mark.asyncio
    async def test_handle_empty_replies_skipped(
        self,
        transport_service: TransportDeliveryService,
        service_headers: dict[str, str],
        bot_runtime: BotRuntime,
    ) -> None:
        payload = TransportDeliveryPayload(
            connector_id="test-connector",
            company_id="test-company",
            channel_type="telegram",
            user_id="user-123",
            conversation_id="conv-456",
            correlation_id="corr-789",
            replies=["Hello", "   ", "World"],
            metadata={"chat_id": "123456"},
        )

        bot_runtime.bot.send_message = AsyncMock()

        headers = {
            **service_headers,
            "X-Connector-Id": "test-connector",
        }

        await transport_service.handle(payload=payload, headers=headers)

        assert bot_runtime.bot.send_message.call_count == 2
