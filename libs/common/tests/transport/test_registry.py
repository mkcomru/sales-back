"""Tests for connector type catalog and registry."""

from __future__ import annotations

from common.connectors import ConnectorCapability
from common.transport.registry import CONNECTOR_TYPE_CATALOG, resolve_catalog_key


class TestConnectorTypeCatalog:
    def test_wappi_vk_registered(self) -> None:
        assert "wappi-vk" in CONNECTOR_TYPE_CATALOG

    def test_wappi_vk_capabilities(self) -> None:
        entry = CONNECTOR_TYPE_CATALOG["wappi-vk"]
        assert ConnectorCapability.INBOUND_TEXT in entry.supported_capabilities
        assert ConnectorCapability.OUTBOUND_TEXT in entry.supported_capabilities
        assert ConnectorCapability.HISTORY_SYNC in entry.supported_capabilities

    def test_wappi_vk_display_name(self) -> None:
        entry = CONNECTOR_TYPE_CATALOG["wappi-vk"]
        assert entry.display_name == "VK (Wappi)"
        assert entry.managed is True

    def test_telegram_inbound_image_registered(self) -> None:
        entry = CONNECTOR_TYPE_CATALOG["telegram"]
        assert ConnectorCapability.INBOUND_IMAGE in entry.supported_capabilities


class TestResolveCatalogKey:
    def test_resolve_wappi_vk(self) -> None:
        assert resolve_catalog_key("wappi", "vk") == "wappi-vk"

    def test_resolve_wappi_whatsapp(self) -> None:
        assert resolve_catalog_key("wappi", "whatsapp") == "wappi-whatsapp"

    def test_resolve_wappi_telegram(self) -> None:
        assert resolve_catalog_key("wappi", "telegram") == "wappi-telegram"

    def test_resolve_single_platform_falls_back(self) -> None:
        assert resolve_catalog_key("telegram", "telegram") == "telegram"
