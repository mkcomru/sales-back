from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from common.connectors import ConnectorCapability, ConnectorTypeCatalogEntry


class TelegramConnectorConfig(BaseModel):
    """Platform credentials for telegram-module (managed connector)."""

    bot_token: str = Field(min_length=1)
    mode: Literal["auto", "webhook", "polling"] = "auto"
    webhook_secret: str | None = None
    webhook_path: str | None = None


class WappiConnectorConfig(BaseModel):
    """Platform credentials for wappi-module (managed connector).

    transport_endpoint is injected by the service from settings, not user-provided.
    """

    wappi_token: str = Field(min_length=1)
    wappi_profile_id: str = Field(min_length=1)


class WazzupConnectorConfig(BaseModel):
    wazzup_api_key: str = Field(min_length=1)
    channel_id: str = Field(min_length=1)


class CustomConnectorConfig(BaseModel):
    """No platform credentials — customer handles their side."""

    pass


class ConnectorTypeEnum(str, Enum):
    TELEGRAM = "telegram"
    WAPPI = "wappi"
    WAZZUP = "wazzup"
    CUSTOM = "custom"


class SyncStatusEnum(str, Enum):
    """History synchronization status for connectors."""

    IDLE = "idle"
    INITIAL = "initial"
    BACKFILL = "backfill"
    CATCHUP = "catchup"
    COMPLETED = "completed"
    FAILED = "failed"


class ConnectorBase(BaseModel):
    connector_id: str = Field(min_length=1)
    company_id: int
    type: ConnectorTypeEnum
    channel_type: str = Field(min_length=1)
    display_name: str = Field(min_length=1, max_length=255)
    managed: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    debounce_window_seconds: int = Field(default=45, ge=1, le=300)
    debounce_storage_key_template: str = Field(default="{connector_id}:{conversation_id}")


class ConnectorCreateRequest(ConnectorBase):
    @model_validator(mode="after")
    def validate_config_for_type(self) -> ConnectorCreateRequest:
        """Validate config field matches connector type."""
        if not self.config:
            if self.managed and self.type != ConnectorTypeEnum.CUSTOM:
                raise ValueError(f"Managed {self.type.value} connector requires config")
            return self

        match self.type:
            case ConnectorTypeEnum.TELEGRAM:
                TelegramConnectorConfig.model_validate(self.config)
            case ConnectorTypeEnum.WAPPI:
                WappiConnectorConfig.model_validate(self.config)
            case ConnectorTypeEnum.WAZZUP:
                WazzupConnectorConfig.model_validate(self.config)
            case ConnectorTypeEnum.CUSTOM:
                CustomConnectorConfig.model_validate(self.config)
        return self


class ConnectorUpdateRequest(BaseModel):
    connector_id: str | None = Field(default=None, min_length=1)
    company_id: int | None = None
    type: ConnectorTypeEnum | None = None
    channel_type: str | None = Field(default=None, min_length=1)
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    managed: bool | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None
    debounce_window_seconds: int | None = Field(default=None, ge=1, le=300)
    debounce_storage_key_template: str | None = None
    prompt_addon_id: int | None = None


class ConnectorResponse(ConnectorBase):
    id: int
    sync_status: SyncStatusEnum = Field(default=SyncStatusEnum.IDLE)
    sync_started_at: datetime | None = None
    sync_completed_at: datetime | None = None
    sync_progress: dict[str, Any] = Field(default_factory=dict)
    prompt_addon_id: int | None = None
    created_at: datetime
    updated_at: datetime


class ConnectorListResponse(BaseModel):
    connectors: list[ConnectorResponse] = Field(default_factory=list)


class ConnectorApiKeyResponse(BaseModel):
    """Response when creating a new API key - shows raw key once."""

    id: int
    connector_id: str
    raw_key: str
    created_at: datetime


class ConnectorApiKeyListItem(BaseModel):
    """API key in list response - no raw key exposed."""

    id: int
    enabled: bool
    created_at: datetime


class SyncTypeEnum(str, Enum):
    """Type of synchronization to start."""

    INITIAL = "initial"
    BACKFILL = "backfill"
    CATCHUP = "catchup"


class SyncJobResponse(BaseModel):
    """Response when starting a sync job."""

    connector_id: str
    sync_type: SyncTypeEnum
    status: SyncStatusEnum
    message: str = Field(default="Sync job started")


class SyncStatusResponse(BaseModel):
    """Response with current sync status and progress."""

    connector_id: str
    status: SyncStatusEnum
    started_at: datetime | None = None
    completed_at: datetime | None = None
    progress: dict[str, Any] = Field(default_factory=dict)


class ConnectorTypeCatalogResponse(BaseModel):
    """Response for GET /api/v1/transport/catalog."""

    connector_type: str
    display_name: str
    description: str
    managed: bool
    supported_capabilities: list[ConnectorCapability]

    @classmethod
    def from_entry(cls, entry: ConnectorTypeCatalogEntry) -> ConnectorTypeCatalogResponse:
        return cls(
            connector_type=entry.connector_type,
            display_name=entry.display_name,
            description=entry.description,
            managed=entry.managed,
            supported_capabilities=entry.supported_capabilities,
        )


class ConnectorCatalogListResponse(BaseModel):
    catalog: list[ConnectorTypeCatalogResponse] = Field(default_factory=list)
