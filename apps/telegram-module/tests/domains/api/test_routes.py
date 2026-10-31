"""Tests for API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from telegram_module.api.routes import (
    admin_router,
    health_router,
    telegram_router,
    transport_router,
)
from telegram_module.bots.manager import BotManager, BotRuntime
from telegram_module.bots.models import BotConfig, BotMode
from telegram_module.config import Settings
from telegram_module.transport.manual_broadcast import ManualBroadcastService
from telegram_module.transport.service import TransportDeliveryService


@pytest.fixture
def test_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings
    app.include_router(health_router)
    app.include_router(transport_router)
    app.include_router(admin_router)
    app.include_router(telegram_router)
    return app


@pytest.fixture
def test_client(test_app: FastAPI) -> TestClient:
    return TestClient(test_app)


@pytest.fixture
def mock_bot_runtime() -> BotRuntime:
    with (
        patch("telegram_module.bots.manager.Bot") as mock_bot_class,
        patch("telegram_module.bots.manager.Dispatcher"),
    ):
        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot
        config = BotConfig(
            connector_id="test-connector",
            company_id="test-company",
            bot_token="123456:ABC-DEF",  # pragma: allowlist secret
        )
        return BotRuntime(
            config=config,
            mode=BotMode.WEBHOOK,
            bot=mock_bot,
            dispatcher=MagicMock(),
            webhook_path="/webhook",
        )


class TestHealthRouter:
    """Test health check endpoint."""

    def test_healthz_returns_ok(self, test_client: TestClient) -> None:
        response = test_client.get("/healthz")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "ok"}


class TestTransportRouter:
    """Test transport delivery endpoint."""

    def test_transport_delivery_missing_service(self, test_app: FastAPI, test_client: TestClient) -> None:
        mock_bot_manager = MagicMock(spec=BotManager)
        test_app.state.bot_manager = mock_bot_manager
        # Explicitly ensure transport_service is not set
        if hasattr(test_app.state, "transport_service"):
            delattr(test_app.state, "transport_service")

        # FastAPI dependency injection will raise RuntimeError if service is missing
        # TestClient will propagate this exception, so we catch it
        with pytest.raises(RuntimeError, match="Transport service not initialised"):
            test_client.post(
                "/transport/delivery",
                json={
                    "connector_id": "test-connector",
                    "company_id": "test-company",
                    "channel_type": "telegram",
                    "user_id": "user-123",
                    "conversation_id": "conv-456",
                    "correlation_id": "corr-789",
                    "replies": ["Hello"],
                },
            )

    @pytest.mark.asyncio
    async def test_transport_delivery_success(
        self,
        test_app: FastAPI,
        test_client: TestClient,
        mock_bot_runtime: BotRuntime,
        service_headers: dict[str, str],
    ) -> None:
        from fastapi.responses import JSONResponse

        mock_transport_service = AsyncMock(spec=TransportDeliveryService)
        mock_transport_service.handle.return_value = JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "status": "accepted",
                "connector_id": "test-connector",
                "correlation_id": "corr-789",
            },
        )

        mock_bot_manager = MagicMock(spec=BotManager)
        mock_bot_manager.get.return_value = mock_bot_runtime

        test_app.state.transport_service = mock_transport_service
        test_app.state.bot_manager = mock_bot_manager

        with patch(
            "telegram_module.api.routes.get_transport_service",
            return_value=mock_transport_service,
        ):
            response = test_client.post(
                "/transport/delivery",
                headers={
                    **service_headers,
                    "X-Connector-Id": "test-connector",
                },
                json={
                    "connector_id": "test-connector",
                    "company_id": "test-company",
                    "channel_type": "telegram",
                    "user_id": "user-123",
                    "conversation_id": "conv-456",
                    "correlation_id": "corr-789",
                    "replies": ["Hello"],
                    "metadata": {"chat_id": "123456"},
                },
            )

            assert response.status_code == status.HTTP_202_ACCEPTED

    def test_transport_delivery_invalid_json(self, test_app: FastAPI, test_client: TestClient) -> None:
        mock_bot_manager = MagicMock(spec=BotManager)
        mock_transport_service = AsyncMock(spec=TransportDeliveryService)
        test_app.state.bot_manager = mock_bot_manager
        test_app.state.transport_service = mock_transport_service

        response = test_client.post(
            "/transport/delivery",
            content="invalid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_manual_broadcast_success(
        self,
        test_app: FastAPI,
        test_client: TestClient,
        mock_bot_runtime: BotRuntime,
        service_headers: dict[str, str],
    ) -> None:
        from telegram_module.transport.manual_broadcast import ManualBroadcastResponse

        mock_broadcast_service = AsyncMock(spec=ManualBroadcastService)
        mock_broadcast_service.handle.return_value = ManualBroadcastResponse(
            total_sent=2,
            total_failed=0,
            recipients=[],
        )

        mock_bot_manager = MagicMock(spec=BotManager)
        test_app.state.manual_broadcast_service = mock_broadcast_service
        test_app.state.bot_manager = mock_bot_manager

        with patch(
            "telegram_module.api.routes.get_manual_broadcast_service",
            return_value=mock_broadcast_service,
        ):
            response = test_client.post(
                "/transport/broadcasts/manual",
                headers={
                    **service_headers,
                    "X-Connector-Id": "test-connector",
                },
                json={
                    "connector_id": "test-connector",
                    "message": {"text": "Test message"},
                    "recipients": [
                        {"recipient_id": "rec-1", "chat_id": "123456"},
                    ],
                },
            )

            assert response.status_code == status.HTTP_200_OK


class TestAdminRouter:
    """Test admin endpoints."""

    @pytest.mark.asyncio
    async def test_reload_bots_success(self, test_app: FastAPI, test_client: TestClient) -> None:
        mock_bot_manager = AsyncMock(spec=BotManager)
        mock_bot_manager.reload = AsyncMock()

        test_app.state.bot_manager = mock_bot_manager

        with patch("telegram_module.api.routes.get_bot_manager", return_value=mock_bot_manager):
            response = test_client.post("/admin/reload")

            assert response.status_code == status.HTTP_202_ACCEPTED
            assert response.json() == {"status": "reloaded"}


class TestTelegramRouter:
    """Test Telegram webhook endpoint."""

    @pytest.mark.asyncio
    async def test_telegram_webhook_success(
        self,
        test_app: FastAPI,
        test_client: TestClient,
        mock_bot_runtime: BotRuntime,
    ) -> None:
        mock_bot_runtime.config.webhook_secret = MagicMock()
        mock_bot_runtime.config.webhook_secret.get_secret_value.return_value = "secret-token"
        mock_bot_runtime.handle_raw_update = AsyncMock()

        mock_bot_manager = MagicMock(spec=BotManager)
        mock_bot_manager.get.return_value = mock_bot_runtime

        test_app.state.bot_manager = mock_bot_manager

        with patch("telegram_module.api.routes.get_bot_manager", return_value=mock_bot_manager):
            response = test_client.post(
                "/telegram/test-connector/webhook",
                headers={"X-Telegram-Bot-Api-Secret-Token": "secret-token"},
                json={"update_id": 123, "message": {"text": "Hello"}},
            )

            assert response.status_code == 202
            assert response.json() == {"status": "forwarded"}

    @pytest.mark.asyncio
    async def test_telegram_webhook_unknown_connector(self, test_app: FastAPI, test_client: TestClient) -> None:
        mock_bot_manager = MagicMock(spec=BotManager)
        mock_bot_manager.get.return_value = None

        test_app.state.bot_manager = mock_bot_manager

        with patch("telegram_module.api.routes.get_bot_manager", return_value=mock_bot_manager):
            response = test_client.post(
                "/telegram/unknown-connector/webhook",
                json={"update_id": 123},
            )

            assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_telegram_webhook_wrong_mode(
        self, test_app: FastAPI, test_client: TestClient, mock_bot_runtime: BotRuntime
    ) -> None:
        mock_bot_runtime.mode = BotMode.POLLING

        mock_bot_manager = MagicMock(spec=BotManager)
        mock_bot_manager.get.return_value = mock_bot_runtime

        test_app.state.bot_manager = mock_bot_manager

        with patch("telegram_module.api.routes.get_bot_manager", return_value=mock_bot_manager):
            response = test_client.post(
                "/telegram/test-connector/webhook",
                json={"update_id": 123},
            )

            assert response.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.asyncio
    async def test_telegram_webhook_missing_secret(
        self, test_app: FastAPI, test_client: TestClient, mock_bot_runtime: BotRuntime
    ) -> None:
        mock_bot_runtime.config.webhook_secret = None

        mock_bot_manager = MagicMock(spec=BotManager)
        mock_bot_manager.get.return_value = mock_bot_runtime

        test_app.state.bot_manager = mock_bot_manager

        with patch("telegram_module.api.routes.get_bot_manager", return_value=mock_bot_manager):
            response = test_client.post(
                "/telegram/test-connector/webhook",
                json={"update_id": 123},
            )

            assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_telegram_webhook_invalid_secret(
        self, test_app: FastAPI, test_client: TestClient, mock_bot_runtime: BotRuntime
    ) -> None:
        mock_bot_runtime.config.webhook_secret = MagicMock()
        mock_bot_runtime.config.webhook_secret.get_secret_value.return_value = "correct-secret"

        mock_bot_manager = MagicMock(spec=BotManager)
        mock_bot_manager.get.return_value = mock_bot_runtime

        test_app.state.bot_manager = mock_bot_manager

        with patch("telegram_module.api.routes.get_bot_manager", return_value=mock_bot_manager):
            response = test_client.post(
                "/telegram/test-connector/webhook",
                headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
                json={"update_id": 123},
            )

            assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_telegram_webhook_invalid_json(
        self, test_app: FastAPI, test_client: TestClient, mock_bot_runtime: BotRuntime
    ) -> None:
        mock_bot_runtime.config.webhook_secret = MagicMock()
        mock_bot_runtime.config.webhook_secret.get_secret_value.return_value = "secret-token"

        mock_bot_manager = MagicMock(spec=BotManager)
        mock_bot_manager.get.return_value = mock_bot_runtime

        test_app.state.bot_manager = mock_bot_manager

        with patch("telegram_module.api.routes.get_bot_manager", return_value=mock_bot_manager):
            response = test_client.post(
                "/telegram/test-connector/webhook",
                headers={
                    "X-Telegram-Bot-Api-Secret-Token": "secret-token",
                    "Content-Type": "application/json",
                },
                content="invalid json",
            )

            assert response.status_code == status.HTTP_400_BAD_REQUEST
