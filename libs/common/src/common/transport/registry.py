from __future__ import annotations

from common.connectors import ConnectorCapability, ConnectorTypeCatalogEntry

# AICODE-NOTE: Canonical source of truth for all well-known connector types.
# Keyed by compound identifier: for hub-style transports like wappi that serve
# multiple platforms, the key is "{transport}-{channel}" (e.g. "wappi-whatsapp").
# Single-platform transports use just their name (e.g. "telegram").
CONNECTOR_TYPE_CATALOG: dict[str, ConnectorTypeCatalogEntry] = {
    "telegram": ConnectorTypeCatalogEntry(
        connector_type="telegram",
        display_name="Telegram Bot",
        description="Telegram Bot API via aiogram",
        managed=True,
        supported_capabilities=[
            ConnectorCapability.INBOUND_TEXT,
            ConnectorCapability.INBOUND_VOICE,
            ConnectorCapability.INBOUND_AUDIO,
            ConnectorCapability.INBOUND_IMAGE,
            ConnectorCapability.OUTBOUND_TEXT,
            ConnectorCapability.OUTBOUND_MEDIA,
        ],
    ),
    "wappi-whatsapp": ConnectorTypeCatalogEntry(
        connector_type="wappi-whatsapp",
        display_name="WhatsApp (Wappi)",
        description="WhatsApp через Wappi API",
        managed=True,
        supported_capabilities=[
            ConnectorCapability.INBOUND_TEXT,
            ConnectorCapability.INBOUND_VOICE,
            ConnectorCapability.INBOUND_AUDIO,
            ConnectorCapability.OUTBOUND_TEXT,
            ConnectorCapability.OUTBOUND_MEDIA,
            ConnectorCapability.HISTORY_SYNC,
        ],
    ),
    "wappi-telegram": ConnectorTypeCatalogEntry(
        connector_type="wappi-telegram",
        display_name="Telegram Personal (Wappi)",
        description="Telegram user-proxy через Wappi API",
        managed=True,
        supported_capabilities=[
            ConnectorCapability.INBOUND_TEXT,
            ConnectorCapability.INBOUND_VOICE,
            ConnectorCapability.INBOUND_AUDIO,
            ConnectorCapability.OUTBOUND_TEXT,
            ConnectorCapability.OUTBOUND_MEDIA,
            ConnectorCapability.HISTORY_SYNC,
        ],
    ),
    "wappi-vk": ConnectorTypeCatalogEntry(
        connector_type="wappi-vk",
        display_name="VK (Wappi)",
        description="ВКонтакте через Wappi API",
        managed=True,
        supported_capabilities=[
            ConnectorCapability.INBOUND_TEXT,
            ConnectorCapability.INBOUND_VOICE,
            ConnectorCapability.INBOUND_AUDIO,
            ConnectorCapability.OUTBOUND_TEXT,
            ConnectorCapability.OUTBOUND_MEDIA,
            ConnectorCapability.HISTORY_SYNC,
        ],
    ),
    "wazzup-instagram": ConnectorTypeCatalogEntry(
        connector_type="wazzup-instagram",
        display_name="Instagram (Wazzup)",
        description="Instagram через Wazzup24 API",
        managed=True,
        supported_capabilities=[
            ConnectorCapability.INBOUND_TEXT,
            ConnectorCapability.INBOUND_VOICE,
            ConnectorCapability.INBOUND_AUDIO,
            ConnectorCapability.OUTBOUND_TEXT,
        ],
    ),
}


def resolve_catalog_key(connector_type: str, channel_type: str) -> str:
    """Derive the catalog key from DB connector fields.

    Hub-style transports (wappi) store a generic ``type`` in the DB but serve
    multiple platforms distinguished by ``channel_type``.  The compound key
    ``{type}-{channel_type}`` is tried first; if absent, falls back to ``type``.
    """
    compound = f"{connector_type}-{channel_type}"
    if compound in CONNECTOR_TYPE_CATALOG:
        return compound
    return connector_type


def register_connector_type(entry: ConnectorTypeCatalogEntry) -> None:
    """Register a connector type in the global catalog.

    Used for dynamic/custom connector types not known at library build time.
    Well-known managed types are pre-registered above.
    """
    CONNECTOR_TYPE_CATALOG[entry.connector_type] = entry
