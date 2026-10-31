"""Additional edge case tests for ConnectorManager."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from wappi_module.config import Settings
from wappi_module.connectors.manager import ConnectorManager
from wappi_module.connectors.models import WappiConnectorConfig
from wappi_module.services.backend import WappiBackendClient


class TestConnectorManagerEdgeCases:
    @pytest.mark.asyncio
    async def test_reload_cancelled_after_fetch(
        self, mock_settings: Settings, mock_backend_client: WappiBackendClient
    ) -> None:
        manager = ConnectorManager(mock_settings, mock_backend_client)

        async def fetch_with_cancel():
            await asyncio.sleep(0.01)
            raise asyncio.CancelledError()

        with patch.object(mock_backend_client, "fetch_connectors", side_effect=fetch_with_cancel):
            with pytest.raises(asyncio.CancelledError):
                await manager.reload()

    @pytest.mark.asyncio
    async def test_reload_cancelled_during_lock(
        self, mock_settings: Settings, mock_backend_client: WappiBackendClient
    ) -> None:
        manager = ConnectorManager(mock_settings, mock_backend_client)

        connector = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
        )

        async def blocking_reload():
            async with manager._lock:
                await asyncio.sleep(10)

        reload_task = asyncio.create_task(blocking_reload())
        await asyncio.sleep(0.01)

        with patch.object(mock_backend_client, "fetch_connectors", return_value=[connector]):
            with pytest.raises(asyncio.CancelledError):
                current_task = asyncio.current_task()
                if current_task is not None:
                    current_task.cancel()
                await manager.reload()

        reload_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reload_task

    @pytest.mark.asyncio
    async def test_config_changed_detects_connector_id_change(
        self, mock_settings: Settings, mock_backend_client: WappiBackendClient
    ) -> None:
        manager = ConnectorManager(mock_settings, mock_backend_client)

        old_config = WappiConnectorConfig(
            connector_id="old-id",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
        )

        new_config = WappiConnectorConfig(
            connector_id="new-id",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
        )

        assert manager._config_changed(old_config, new_config) is True
