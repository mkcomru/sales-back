"""Tests for API dependencies."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request

from telegram_module.api.dependencies import (
    get_bot_manager,
    get_manual_broadcast_service,
    get_settings,
    get_transport_service,
)
from telegram_module.bots.manager import BotManager
from telegram_module.config import Settings
from telegram_module.transport.manual_broadcast import ManualBroadcastService
from telegram_module.transport.service import TransportDeliveryService


@pytest.fixture
def test_app() -> FastAPI:
    from fastapi import FastAPI

    app = FastAPI()
    return app


@pytest.fixture
def test_request(test_app: FastAPI) -> Request:
    from starlette.requests import Request as StarletteRequest

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "app": test_app,
    }
    return StarletteRequest(scope, None)


class TestGetSettings:
    """Test get_settings dependency."""

    def test_get_settings_success(self, test_app: FastAPI, test_request: Request, settings: Settings) -> None:
        test_app.state.settings = settings

        result = get_settings(test_request)

        assert result is settings

    def test_get_settings_not_initialized(self, test_app: FastAPI, test_request: Request) -> None:
        with pytest.raises(RuntimeError, match="Settings not initialised"):
            get_settings(test_request)


class TestGetBotManager:
    """Test get_bot_manager dependency."""

    def test_get_bot_manager_success(
        self, test_app: FastAPI, test_request: Request, mock_bot_manager: BotManager
    ) -> None:
        test_app.state.bot_manager = mock_bot_manager

        result = get_bot_manager(test_request)

        assert result is mock_bot_manager

    def test_get_bot_manager_not_initialized(self, test_app: FastAPI, test_request: Request) -> None:
        with pytest.raises(RuntimeError, match="Bot manager not initialised"):
            get_bot_manager(test_request)


class TestGetTransportService:
    """Test get_transport_service dependency."""

    def test_get_transport_service_success(
        self,
        test_app: FastAPI,
        test_request: Request,
        mock_transport_service: TransportDeliveryService,
    ) -> None:
        test_app.state.transport_service = mock_transport_service

        result = get_transport_service(test_request)

        assert result is mock_transport_service

    def test_get_transport_service_not_initialized(self, test_app: FastAPI, test_request: Request) -> None:
        with pytest.raises(RuntimeError, match="Transport service not initialised"):
            get_transport_service(test_request)


class TestGetManualBroadcastService:
    """Test get_manual_broadcast_service dependency."""

    def test_get_manual_broadcast_service_success(
        self,
        test_app: FastAPI,
        test_request: Request,
        mock_manual_broadcast_service: ManualBroadcastService,
    ) -> None:
        test_app.state.manual_broadcast_service = mock_manual_broadcast_service

        result = get_manual_broadcast_service(test_request)

        assert result is mock_manual_broadcast_service

    def test_get_manual_broadcast_service_not_initialized(self, test_app: FastAPI, test_request: Request) -> None:
        with pytest.raises(RuntimeError, match="Manual broadcast service not initialised"):
            get_manual_broadcast_service(test_request)
