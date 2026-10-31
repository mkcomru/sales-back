from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from common.config import BackendSettings, EventingSettings
from wazzup_module.config import Settings
from wazzup_module.connectors.manager import ConnectorManager
from wazzup_module.connectors.models import WazzupConnectorConfig
from wazzup_module.services.backend import WazzupBackendClient
from wazzup_module.services.inbound import BackendInboundClient
from wazzup_module.services.wazzup_api import WazzupApiClient
from wazzup_module.transport.service import TransportDeliveryService


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        backend=BackendSettings(url="http://backend.test/api/v1"),
        service_api_key="test-api-key",  # pragma: allowlist secret
        app_environment="test",
        app_debug=False,
        config_refresh_interval_s=0,
        request_timeout_s=10.0,
        max_delivery_attempts=3,
        eventing=EventingSettings(enabled=False),
        webhook_url="https://our-domain.com/wazzup/webhook",
    )


@pytest.fixture
def sample_connector_config() -> WazzupConnectorConfig:
    return WazzupConnectorConfig(
        connector_id="test-connector",
        company_id="123",
        wazzup_api_key=SecretStr("test-api-key-wazzup"),
        channel_id="channel-uuid-123",
        channel_type="instagram",
        metadata={},
    )


@pytest.fixture
def mock_backend_client(mock_settings: Settings) -> WazzupBackendClient:
    return WazzupBackendClient(mock_settings)


@pytest.fixture
def mock_wazzup_client() -> WazzupApiClient:
    return WazzupApiClient(api_base_url="https://wazzup.test/v3")


@pytest.fixture
def mock_connector_manager(
    mock_settings: Settings,
    mock_backend_client: WazzupBackendClient,
    mock_wazzup_client: WazzupApiClient,
) -> ConnectorManager:
    return ConnectorManager(mock_settings, mock_backend_client, mock_wazzup_client)


@pytest.fixture
def mock_inbound_client(mock_settings: Settings, mock_backend_client: WazzupBackendClient) -> BackendInboundClient:
    return BackendInboundClient(mock_settings, mock_backend_client)


@pytest.fixture
def mock_transport_service(
    mock_settings: Settings, mock_connector_manager: ConnectorManager
) -> TransportDeliveryService:
    return TransportDeliveryService(mock_settings, mock_connector_manager)


@pytest.fixture
def sample_transport_payload() -> dict[str, Any]:
    return {
        "connector_id": "test-connector",
        "company_id": "123",
        "channel_type": "instagram",
        "user_id": "user123",
        "conversation_id": "conv123",
        "correlation_id": "corr123",
        "replies": ["Test message"],
        "metadata": {"chat_id": "insta-user-123"},
    }


@pytest.fixture
def sample_webhook_payload() -> dict[str, Any]:
    return {
        "messages": [
            {
                "messageId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "channelId": "channel-uuid-123",
                "chatType": "instagram",
                "chatId": "insta-user-123",
                "dateTime": "2026-03-19T12:00:00.000Z",
                "type": "text",
                "isEcho": False,
                "text": "Hello from Instagram",
                "contact": {
                    "name": "Test User",
                    "username": "testuser",
                },
                "status": "inbound",
            }
        ]
    }


@pytest.fixture
def mock_app(
    mock_settings: Settings,
    mock_connector_manager: ConnectorManager,
    mock_inbound_client: BackendInboundClient,
    mock_backend_client: WazzupBackendClient,
    mock_transport_service: TransportDeliveryService,
    mock_wazzup_client: WazzupApiClient,
) -> FastAPI:
    from wazzup_module.api.routes import (
        admin_router,
        health_router,
        transport_router,
        wazzup_router,
    )

    app = FastAPI(title="Test Wazzup Module")
    app.state.settings = mock_settings
    app.state.connector_manager = mock_connector_manager
    app.state.inbound_client = mock_inbound_client
    app.state.backend_client = mock_backend_client
    app.state.transport_service = mock_transport_service
    app.state.wazzup_client = mock_wazzup_client

    app.include_router(transport_router)
    app.include_router(admin_router)
    app.include_router(health_router)
    app.include_router(wazzup_router)

    return app


@pytest.fixture
def client(mock_app: FastAPI) -> TestClient:
    return TestClient(mock_app)
