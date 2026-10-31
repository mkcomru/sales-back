"""Connector capability definitions — single source of truth for transport modules."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ConnectorCapability(StrEnum):
    INBOUND_TEXT = "inbound_text"
    INBOUND_VOICE = "inbound_voice"
    INBOUND_AUDIO = "inbound_audio"
    INBOUND_IMAGE = "inbound_image"
    INBOUND_VIDEO = "inbound_video"
    INBOUND_DOCUMENT = "inbound_document"
    OUTBOUND_TEXT = "outbound_text"
    OUTBOUND_MEDIA = "outbound_media"
    HISTORY_SYNC = "history_sync"


class ConfigFieldSchema(BaseModel):
    """Describes one config field a connector type accepts (for frontend form rendering)."""

    key: str
    label: str
    field_type: str = "string"
    required: bool = False
    placeholder: str = ""
    default: Any = None


class ConnectorTypeCatalogEntry(BaseModel):
    """Self-describing metadata for a single connector type.

    Populated by transport modules at import time via register_connector_type().
    Served to the frontend so it knows what each connector type can do.
    """

    connector_type: str = Field(description="Unique connector type identifier, e.g. 'telegram'")
    display_name: str = Field(description="Human-readable name, e.g. 'Telegram Bot'")
    description: str = ""
    managed: bool = True
    supported_capabilities: list[ConnectorCapability] = Field(description="Capabilities this connector type supports")
    config_fields: list[ConfigFieldSchema] = Field(default_factory=list)
