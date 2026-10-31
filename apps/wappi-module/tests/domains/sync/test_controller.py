"""Tests for SyncController."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from common.contracts.sync import SyncCancelCommand, SyncStartCommand
from wappi_module.config import Settings
from wappi_module.connectors.manager import ConnectorManager
from wappi_module.connectors.models import WappiConnectorConfig
from wappi_module.services.wappi_api import WappiApiClient
from wappi_module.sync.controller import SyncController


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings."""
    from common.config import BackendSettings, EventingSettings

    return Settings(
        backend=BackendSettings(url="http://backend.test"),
        service_api_key="test-key",  # pragma: allowlist secret
        app_environment="test",
        app_debug=False,
        config_refresh_interval_s=0,
        request_timeout_s=10.0,
        max_delivery_attempts=3,
        idempotency_cache_ttl_s=86400,
        eventing=EventingSettings(enabled=False),
    )


@pytest.fixture
def mock_connector_manager() -> ConnectorManager:
    """Create mock connector manager."""
    manager = MagicMock(spec=ConnectorManager)
    manager.get = MagicMock(
        return_value=WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("test-token"),
            wappi_profile_id="profile-123",
            channel_type="telegram",
            metadata={},
        )
    )
    return manager


@pytest.fixture
def mock_wappi_client() -> WappiApiClient:
    """Create mock Wappi API client."""
    return MagicMock(spec=WappiApiClient)


@pytest.fixture
def mock_backend_client():
    """Create mock backend client."""
    from wappi_module.services.backend import WappiBackendClient

    return MagicMock(spec=WappiBackendClient)


@pytest.fixture
def controller(
    mock_settings: Settings,
    mock_connector_manager: ConnectorManager,
    mock_wappi_client: WappiApiClient,
    mock_backend_client,
) -> SyncController:
    """Create SyncController instance."""
    return SyncController(
        settings=mock_settings,
        connector_manager=mock_connector_manager,
        wappi_client=mock_wappi_client,
        backend_client=mock_backend_client,
    )


@pytest.mark.asyncio
async def test_start_sync_success(controller: SyncController, mock_connector_manager: ConnectorManager):
    """Test successful sync start."""
    command = SyncStartCommand(
        connector_id="test-connector",
        correlation_id="corr1",
        sync_type="initial",
    )

    await controller.start_sync(command)

    # Verify sync was started (check that active_syncs contains the correlation_id)
    assert "corr1" in controller._active_syncs
    assert "corr1" in controller._sync_tasks


@pytest.mark.asyncio
async def test_start_sync_connector_not_found(controller: SyncController, mock_connector_manager: ConnectorManager):
    """Test sync start with non-existent connector."""
    mock_connector_manager.get.return_value = None

    command = SyncStartCommand(
        connector_id="non-existent",
        correlation_id="corr1",
        sync_type="initial",
    )

    with pytest.raises(ValueError, match="Connector non-existent not found"):
        await controller.start_sync(command)


@pytest.mark.asyncio
async def test_start_sync_already_running(controller: SyncController):
    """Test that starting sync when already running raises error."""
    command = SyncStartCommand(
        connector_id="test-connector",
        correlation_id="corr1",
        sync_type="initial",
    )

    await controller.start_sync(command)

    # Try to start again with same correlation_id
    with pytest.raises(ValueError, match="already running"):
        await controller.start_sync(command)


@pytest.mark.asyncio
async def test_cancel_sync_success(controller: SyncController):
    """Test successful sync cancellation."""
    command = SyncStartCommand(
        connector_id="test-connector",
        correlation_id="corr1",
        sync_type="initial",
    )

    await controller.start_sync(command)

    cancel_command = SyncCancelCommand(
        connector_id="test-connector",
        correlation_id="corr1",
    )

    await controller.cancel_sync(cancel_command)

    # Verify sync was removed
    assert "corr1" not in controller._active_syncs
    assert "corr1" not in controller._sync_tasks


@pytest.mark.asyncio
async def test_cancel_sync_not_found(controller: SyncController):
    """Test cancel sync when not running."""
    cancel_command = SyncCancelCommand(
        connector_id="test-connector",
        correlation_id="non-existent",
    )

    with pytest.raises(ValueError, match="not found"):
        await controller.cancel_sync(cancel_command)


@pytest.mark.asyncio
async def test_start_sync_with_cursor(controller: SyncController):
    """Test starting sync with cursor for resume."""
    command = SyncStartCommand(
        connector_id="test-connector",
        correlation_id="corr1",
        sync_type="backfill",
        cursor="offset_100",
    )

    await controller.start_sync(command)

    assert "corr1" in controller._active_syncs


@pytest.mark.asyncio
async def test_start_sync_with_since(controller: SyncController):
    """Test starting catchup sync with since date."""
    command = SyncStartCommand(
        connector_id="test-connector",
        correlation_id="corr1",
        sync_type="catchup",
        since=datetime.now(),
    )

    await controller.start_sync(command)

    assert "corr1" in controller._active_syncs
