from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from pydantic import SecretStr as PydanticSecretStr

from common.config import BackendSettings, EventingSettings, S3Settings
from wappi_module.config import Settings
from wappi_module.connectors.manager import ConnectorManager
from wappi_module.connectors.models import WappiConnectorConfig
from wappi_module.services.backend import WappiBackendClient
from wappi_module.services.sales_agent import BackendInboundClient
from wappi_module.services.wappi_api import WappiApiClient
from wappi_module.transport.service import TransportDeliveryService


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
        idempotency_cache_ttl_s=86400,
        eventing=EventingSettings(enabled=False),
        s3=S3Settings(
            endpoint_url="http://localhost:9000",
            access_key_id=PydanticSecretStr("test-access-key"),  # pragma: allowlist secret
            secret_access_key=PydanticSecretStr("test-secret-key"),  # pragma: allowlist secret
            bucket_name="test-bucket",
        ),
    )


@pytest.fixture
def sample_connector_config() -> WappiConnectorConfig:
    return WappiConnectorConfig(
        connector_id="test-connector",
        company_id="123",
        wappi_token=SecretStr("test-token"),
        wappi_profile_id="b51675ef-d41f-4891-9dd0-b74d76f5b9b5",
        channel_type="telegram",
        metadata={},
    )


@pytest.fixture
def mock_backend_client(mock_settings: Settings) -> WappiBackendClient:
    client = WappiBackendClient(mock_settings)
    return client


@pytest.fixture
def mock_connector_manager(mock_settings: Settings, mock_backend_client: WappiBackendClient) -> ConnectorManager:
    return ConnectorManager(mock_settings, mock_backend_client)


@pytest.fixture
def mock_sales_agent_client(mock_settings: Settings) -> BackendInboundClient:
    return BackendInboundClient(mock_settings)


@pytest.fixture
def mock_transport_service(
    mock_settings: Settings, mock_connector_manager: ConnectorManager, mock_backend_client: WappiBackendClient
) -> TransportDeliveryService:
    return TransportDeliveryService(mock_settings, mock_connector_manager, mock_backend_client)


@pytest.fixture
def mock_wappi_api_client() -> WappiApiClient:
    return WappiApiClient(api_base_url="https://wappi.test")


@pytest.fixture
def sample_transport_payload() -> dict[str, Any]:
    return {
        "connector_id": "test-connector",
        "company_id": "123",
        "channel_type": "telegram",
        "user_id": "user123",
        "conversation_id": "conv123",
        "correlation_id": "corr123",
        "replies": ["Test message"],
        "metadata": {"chat_id": "351311665"},
    }


@pytest.fixture
def sample_webhook_payload() -> dict[str, Any]:
    return {
        "messages": [
            {
                "id": "msg123",
                "wh_type": "incoming_message",
                "body": "Hello",
                "chatId": "351311665",
                "profile_id": "b51675ef-d41f",
                "type": "text",
                "platform": "telegram",
            }
        ]
    }


@pytest.fixture
def mock_app(
    mock_settings: Settings,
    mock_connector_manager: ConnectorManager,
    mock_sales_agent_client: BackendInboundClient,
    mock_backend_client: WappiBackendClient,
    mock_transport_service: TransportDeliveryService,
    mock_wappi_api_client: WappiApiClient,
) -> FastAPI:
    from wappi_module.api.routes import (
        admin_router,
        health_router,
        transport_router,
        wappi_router,
    )

    app = FastAPI(title="Test Wappi Module")
    app.state.settings = mock_settings
    app.state.connector_manager = mock_connector_manager
    app.state.sales_agent_client = mock_sales_agent_client
    app.state.backend_client = mock_backend_client
    app.state.transport_service = mock_transport_service
    app.state.wappi_client = mock_wappi_api_client

    app.include_router(transport_router)
    app.include_router(admin_router)
    app.include_router(health_router)
    app.include_router(wappi_router)

    return app


@pytest.fixture
def client(mock_app: FastAPI) -> TestClient:
    return TestClient(mock_app)


@pytest.fixture
def async_mock() -> AsyncMock:
    return AsyncMock()
