from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from wazzup_module.connectors.manager import ConnectorManager
from wazzup_module.connectors.models import WazzupConnectorConfig


def _make_config(
    connector_id: str = "c1",
    channel_id: str = "chan-1",
    api_key: str = "key-1",
) -> WazzupConnectorConfig:
    return WazzupConnectorConfig(
        connector_id=connector_id,
        company_id="company-1",
        wazzup_api_key=SecretStr(api_key),
        channel_id=channel_id,
        channel_type="instagram",
    )


class TestConnectorManagerGet:
    def test_get_existing(self, mock_connector_manager: ConnectorManager) -> None:
        cfg = _make_config()
        mock_connector_manager._connectors["c1"] = cfg
        assert mock_connector_manager.get("c1") is cfg

    def test_get_missing(self, mock_connector_manager: ConnectorManager) -> None:
        assert mock_connector_manager.get("nonexistent") is None


class TestConnectorManagerGetByChannelId:
    def test_found(self, mock_connector_manager: ConnectorManager) -> None:
        cfg = _make_config(channel_id="chan-abc")
        mock_connector_manager._connectors["c1"] = cfg
        assert mock_connector_manager.get_by_channel_id("chan-abc") is cfg

    def test_not_found(self, mock_connector_manager: ConnectorManager) -> None:
        assert mock_connector_manager.get_by_channel_id("unknown") is None

    def test_multiple_connectors(self, mock_connector_manager: ConnectorManager) -> None:
        cfg1 = _make_config(connector_id="c1", channel_id="chan-1")
        cfg2 = _make_config(connector_id="c2", channel_id="chan-2")
        mock_connector_manager._connectors["c1"] = cfg1
        mock_connector_manager._connectors["c2"] = cfg2
        assert mock_connector_manager.get_by_channel_id("chan-2") is cfg2


class TestConnectorManagerReload:
    @pytest.mark.anyio
    async def test_reload_adds_new_connectors(self, mock_connector_manager: ConnectorManager) -> None:
        cfg = _make_config()
        with (
            patch.object(
                mock_connector_manager._backend, "fetch_connectors", new_callable=AsyncMock, return_value=[cfg]
            ),
            patch.object(mock_connector_manager, "_register_webhook", new_callable=AsyncMock) as mock_register,
        ):
            await mock_connector_manager.reload()

        assert mock_connector_manager.get("c1") is cfg
        mock_register.assert_called_once_with("c1", cfg)

    @pytest.mark.anyio
    async def test_reload_removes_stale_connectors(self, mock_connector_manager: ConnectorManager) -> None:
        mock_connector_manager._connectors["old"] = _make_config(connector_id="old")

        with (
            patch.object(mock_connector_manager._backend, "fetch_connectors", new_callable=AsyncMock, return_value=[]),
            patch.object(mock_connector_manager, "_register_webhook", new_callable=AsyncMock),
        ):
            await mock_connector_manager.reload()

        assert mock_connector_manager.get("old") is None

    @pytest.mark.anyio
    async def test_reload_updates_changed_config(self, mock_connector_manager: ConnectorManager) -> None:
        old_cfg = _make_config(api_key="old-key")
        mock_connector_manager._connectors["c1"] = old_cfg

        new_cfg = _make_config(api_key="new-key")
        with (
            patch.object(
                mock_connector_manager._backend, "fetch_connectors", new_callable=AsyncMock, return_value=[new_cfg]
            ),
            patch.object(mock_connector_manager, "_register_webhook", new_callable=AsyncMock) as mock_register,
        ):
            await mock_connector_manager.reload()

        assert mock_connector_manager.get("c1") is new_cfg
        mock_register.assert_not_called()

    @pytest.mark.anyio
    async def test_reload_propagates_fetch_error(self, mock_connector_manager: ConnectorManager) -> None:
        with patch.object(
            mock_connector_manager._backend,
            "fetch_connectors",
            new_callable=AsyncMock,
            side_effect=RuntimeError("fetch failed"),
        ):
            with pytest.raises(RuntimeError, match="fetch failed"):
                await mock_connector_manager.reload()


class TestConnectorManagerWebhookRegistration:
    @pytest.mark.anyio
    async def test_register_webhook_called_on_new_connector(self, mock_connector_manager: ConnectorManager) -> None:
        cfg = _make_config()
        with patch.object(
            mock_connector_manager._wazzup_client,
            "register_webhook",
            new_callable=AsyncMock,
        ) as mock_reg:
            await mock_connector_manager._register_webhook("c1", cfg)

        mock_reg.assert_called_once_with(
            api_key="key-1",  # pragma: allowlist secret
            webhook_uri=str(mock_connector_manager._webhook_url),
        )

    @pytest.mark.anyio
    async def test_register_webhook_skipped_when_no_url(self, mock_connector_manager: ConnectorManager) -> None:
        mock_connector_manager._webhook_url = None
        cfg = _make_config()
        with patch.object(
            mock_connector_manager._wazzup_client,
            "register_webhook",
            new_callable=AsyncMock,
        ) as mock_reg:
            await mock_connector_manager._register_webhook("c1", cfg)

        mock_reg.assert_not_called()

    @pytest.mark.anyio
    async def test_register_webhook_error_does_not_raise(self, mock_connector_manager: ConnectorManager) -> None:
        cfg = _make_config()
        with patch.object(
            mock_connector_manager._wazzup_client,
            "register_webhook",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API down"),
        ):
            await mock_connector_manager._register_webhook("c1", cfg)
