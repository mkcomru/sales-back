from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from telegram_module.api.routes import (
    admin_router,
    health_router,
    telegram_router,
    transport_router,
)
from telegram_module.config import Settings, get_settings

DEFAULT_ENV = {
    "APP__ENVIRONMENT": "test",
    "BACKEND__URL": "http://test-backend",
    "SALES_AGENT__URL": "http://test-sales-agent",
    "CONFIG__REFRESH_INTERVAL_S": "0",
    "SERVICE__API_KEY": "test-service-key",  # pragma: allowlist secret
    "EVENTING__ENABLED": "false",
    "S3__ENDPOINT_URL": "http://localhost:9000",
    "S3__ACCESS_KEY_ID": "test-access-key",  # pragma: allowlist secret
    "S3__SECRET_ACCESS_KEY": "test-secret-key",  # pragma: allowlist secret
    "S3__BUCKET_NAME": "test-bucket",
}

for key, value in DEFAULT_ENV.items():
    os.environ.setdefault(key, value)


@pytest.fixture(scope="session")
def settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
def fastapi_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Sales Bot Telegram Module - Test")
    app.include_router(health_router)
    app.include_router(transport_router)
    app.include_router(admin_router)
    app.include_router(telegram_router)
    app.state.settings = settings
    return app


@pytest.fixture
def api_client(fastapi_app: FastAPI) -> TestClient:
    return TestClient(fastapi_app)


@pytest.fixture
def mock_bot_manager() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_backend_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_sales_agent_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_transport_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_manual_broadcast_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service_headers(settings: Settings) -> dict[str, str]:
    api_key = settings.service.api_key
    if api_key is None:
        raise RuntimeError("SERVICE__API_KEY must be configured for tests")
    return {settings.service.resolved_header(): api_key.get_secret_value()}
