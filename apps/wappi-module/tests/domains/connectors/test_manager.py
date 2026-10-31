"""Tests for ConnectorManager."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from wappi_module.config import Settings
from wappi_module.connectors.manager import ConnectorManager
from wappi_module.connectors.models import WappiConnectorConfig
from wappi_module.services.backend import WappiBackendClient


class TestConnectorManager:
    @pytest.mark.asyncio
    async def test_get_existing_connector(
        self,
        mock_settings: Settings,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        manager = ConnectorManager(mock_settings, mock_backend_client)
        manager._connectors["test-connector"] = sample_connector_config

        result = manager.get("test-connector")

        assert result is not None
        assert result.connector_id == "test-connector"

    @pytest.mark.asyncio
    async def test_get_non_existing_connector(
        self, mock_settings: Settings, mock_backend_client: WappiBackendClient
    ) -> None:
        manager = ConnectorManager(mock_settings, mock_backend_client)

        result = manager.get("non-existent")

        assert result is None

    @pytest.mark.asyncio
    async def test_reload_add_new_connectors(
        self, mock_settings: Settings, mock_backend_client: WappiBackendClient
    ) -> None:
        manager = ConnectorManager(mock_settings, mock_backend_client)

        connector1 = WappiConnectorConfig(
            connector_id="conn1",
            company_id="123",
            wappi_token=SecretStr("token1"),
            wappi_profile_id="profile1",
        )
        connector2 = WappiConnectorConfig(
            connector_id="conn2",
            company_id="456",
            wappi_token=SecretStr("token2"),
            wappi_profile_id="profile2",
        )

        with patch.object(
            mock_backend_client,
            "fetch_connectors",
            return_value=[connector1, connector2],
        ):
            await manager.reload()

        assert manager.get("conn1") is not None
        assert manager.get("conn2") is not None
        assert len(manager._connectors) == 2

    @pytest.mark.asyncio
    async def test_reload_remove_old_connectors(
        self, mock_settings: Settings, mock_backend_client: WappiBackendClient
    ) -> None:
        manager = ConnectorManager(mock_settings, mock_backend_client)

        old_connector = WappiConnectorConfig(
            connector_id="old",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
        )
        manager._connectors["old"] = old_connector

        new_connector = WappiConnectorConfig(
            connector_id="new",
            company_id="456",
            wappi_token=SecretStr("token2"),
            wappi_profile_id="profile2",
        )

        with patch.object(mock_backend_client, "fetch_connectors", return_value=[new_connector]):
            await manager.reload()

        assert manager.get("old") is None
        assert manager.get("new") is not None
        assert len(manager._connectors) == 1

    @pytest.mark.asyncio
    async def test_reload_update_existing_connector(
        self, mock_settings: Settings, mock_backend_client: WappiBackendClient
    ) -> None:
        manager = ConnectorManager(mock_settings, mock_backend_client)

        old_connector = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("old-token"),
            wappi_profile_id="old-profile",
        )
        manager._connectors["test"] = old_connector

        updated_connector = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("new-token"),
            wappi_profile_id="new-profile",
        )

        with patch.object(mock_backend_client, "fetch_connectors", return_value=[updated_connector]):
            await manager.reload()

        result = manager.get("test")
        assert result is not None
        assert result.wappi_profile_id == "new-profile"
        assert result.wappi_token.get_secret_value() == "new-token"

    @pytest.mark.asyncio
    async def test_reload_no_changes(self, mock_settings: Settings, mock_backend_client: WappiBackendClient) -> None:
        manager = ConnectorManager(mock_settings, mock_backend_client)

        connector = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
        )
        manager._connectors["test"] = connector

        same_connector = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
        )

        with patch.object(mock_backend_client, "fetch_connectors", return_value=[same_connector]):
            await manager.reload()

        result = manager.get("test")
        assert result is not None
        assert result.connector_id == "test"

    @pytest.mark.asyncio
    async def test_reload_error_handling(
        self, mock_settings: Settings, mock_backend_client: WappiBackendClient
    ) -> None:
        manager = ConnectorManager(mock_settings, mock_backend_client)

        with patch.object(
            mock_backend_client,
            "fetch_connectors",
            side_effect=Exception("Backend error"),
        ):
            with pytest.raises(Exception, match="Backend error"):
                await manager.reload()

    @pytest.mark.asyncio
    async def test_reload_cancelled_error_propagates(
        self, mock_settings: Settings, mock_backend_client: WappiBackendClient
    ) -> None:
        manager = ConnectorManager(mock_settings, mock_backend_client)

        with patch.object(
            mock_backend_client,
            "fetch_connectors",
            side_effect=asyncio.CancelledError(),
        ):
            with pytest.raises(asyncio.CancelledError):
                await manager.reload()

    @pytest.mark.asyncio
    async def test_reload_empty_list(self, mock_settings: Settings, mock_backend_client: WappiBackendClient) -> None:
        manager = ConnectorManager(mock_settings, mock_backend_client)

        old_connector = WappiConnectorConfig(
            connector_id="old",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
        )
        manager._connectors["old"] = old_connector

        with patch.object(mock_backend_client, "fetch_connectors", return_value=[]):
            await manager.reload()

        assert len(manager._connectors) == 0
        assert manager.get("old") is None

    @pytest.mark.asyncio
    async def test_shutdown_clears_connectors(
        self,
        mock_settings: Settings,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        manager = ConnectorManager(mock_settings, mock_backend_client)
        manager._connectors["test"] = sample_connector_config

        await manager.shutdown()

        assert len(manager._connectors) == 0

    @pytest.mark.asyncio
    async def test_shutdown_timeout_handling(
        self,
        mock_settings: Settings,
        mock_backend_client: WappiBackendClient,
        sample_connector_config: WappiConnectorConfig,
    ) -> None:
        manager = ConnectorManager(mock_settings, mock_backend_client)
        manager._connectors["test"] = sample_connector_config

        async def blocking_lock():
            async with manager._lock:
                await asyncio.sleep(0.2)

        task = asyncio.create_task(blocking_lock())
        await asyncio.sleep(0.01)

        original_wait_for = asyncio.wait_for

        async def fast_wait_for(coro, timeout):
            return await original_wait_for(coro, timeout=0.1)

        with patch("wappi_module.connectors.manager.asyncio.wait_for", side_effect=fast_wait_for):
            await manager.shutdown()

        assert len(manager._connectors) == 0
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_config_changed_detects_token_change(
        self, mock_settings: Settings, mock_backend_client: WappiBackendClient
    ) -> None:
        manager = ConnectorManager(mock_settings, mock_backend_client)

        old_config = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("old-token"),
            wappi_profile_id="profile",
        )

        new_config = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("new-token"),
            wappi_profile_id="profile",
        )

        assert manager._config_changed(old_config, new_config) is True

    @pytest.mark.asyncio
    async def test_config_changed_detects_profile_id_change(
        self, mock_settings: Settings, mock_backend_client: WappiBackendClient
    ) -> None:
        manager = ConnectorManager(mock_settings, mock_backend_client)

        old_config = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="old-profile",
        )

        new_config = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="new-profile",
        )

        assert manager._config_changed(old_config, new_config) is True

    @pytest.mark.asyncio
    async def test_config_changed_no_changes(
        self, mock_settings: Settings, mock_backend_client: WappiBackendClient
    ) -> None:
        manager = ConnectorManager(mock_settings, mock_backend_client)

        config1 = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
        )

        config2 = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
        )

        assert manager._config_changed(config1, config2) is False

    @pytest.mark.asyncio
    async def test_config_changed_detects_metadata_change(
        self, mock_settings: Settings, mock_backend_client: WappiBackendClient
    ) -> None:
        manager = ConnectorManager(mock_settings, mock_backend_client)

        old_config = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
            metadata={"key": "old_value"},
        )

        new_config = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
            metadata={"key": "new_value"},
        )

        assert manager._config_changed(old_config, new_config) is True

    @pytest.mark.asyncio
    async def test_config_changed_detects_company_id_change(
        self, mock_settings: Settings, mock_backend_client: WappiBackendClient
    ) -> None:
        manager = ConnectorManager(mock_settings, mock_backend_client)

        old_config = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
        )

        new_config = WappiConnectorConfig(
            connector_id="test",
            company_id="456",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
        )

        assert manager._config_changed(old_config, new_config) is True

    @pytest.mark.asyncio
    async def test_config_changed_detects_channel_type_change(
        self, mock_settings: Settings, mock_backend_client: WappiBackendClient
    ) -> None:
        manager = ConnectorManager(mock_settings, mock_backend_client)

        old_config = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
            channel_type="telegram",
        )

        new_config = WappiConnectorConfig(
            connector_id="test",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile",
            channel_type="whatsapp",
        )

        assert manager._config_changed(old_config, new_config) is True
