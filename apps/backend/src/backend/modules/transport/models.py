from __future__ import annotations

from enum import Enum

from tortoise import fields

from src.backend.modules.core.base_model import BaseModel


class ConnectorType(str, Enum):
    """Connector platform types for the unified Connector model."""

    TELEGRAM = "telegram"
    WAPPI = "wappi"
    WAZZUP = "wazzup"
    CUSTOM = "custom"


class SyncStatus(str, Enum):
    """History synchronization status for connectors."""

    IDLE = "idle"
    INITIAL = "initial"
    BACKFILL = "backfill"
    CATCHUP = "catchup"
    COMPLETED = "completed"
    FAILED = "failed"


class Connector(BaseModel):
    """Unified connector model replacing separate TelegramBot/WappiConnector tables.

    - `managed=True`: We run the connector module (telegram-module, wappi-module).
      Auth via X-Service-Key + X-Connector-Id headers.
    - `managed=False`: Customer runs their own code, sends to our API.
      Auth via Bearer sk_xxx token (ConnectorApiKey).
    """

    id = fields.IntField(primary_key=True)
    connector_id = fields.CharField(max_length=100, unique=True)
    company: fields.ForeignKeyRelation = fields.ForeignKeyField(
        "models.Company",
        related_name="connectors",
        on_delete=fields.CASCADE,
    )
    type = fields.CharEnumField(ConnectorType, max_length=20)
    channel_type = fields.CharField(max_length=50)
    display_name = fields.CharField(max_length=255)
    managed = fields.BooleanField(default=True)
    config = fields.JSONField(default=dict)
    enabled = fields.BooleanField(default=True)
    debounce_window_seconds = fields.IntField(default=45)
    debounce_storage_key_template = fields.CharField(max_length=255, default="{connector_id}:{conversation_id}")
    sync_status = fields.CharEnumField(SyncStatus, max_length=30, default=SyncStatus.IDLE)
    sync_started_at = fields.DatetimeField(null=True)
    sync_completed_at = fields.DatetimeField(null=True)
    sync_progress = fields.JSONField(default=dict)
    prompt_addon: fields.ForeignKeyNullableRelation = fields.ForeignKeyField(
        "models.PromptAddon",
        related_name="connectors",
        on_delete=fields.SET_NULL,
        null=True,
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    @property
    def is_syncing(self) -> bool:
        """Check if connector is currently syncing."""
        return self.sync_status in (SyncStatus.INITIAL, SyncStatus.BACKFILL, SyncStatus.CATCHUP)

    api_keys: fields.ReverseRelation[ConnectorApiKey]

    class Meta(BaseModel.Meta):
        table = "connectors"
        schema = "backend"


class ConnectorApiKey(BaseModel):
    """API key for custom (unmanaged) connectors.

    Key format: sk_<random> (displayed once on creation).
    Stored as sha256 hash for security.
    """

    id = fields.IntField(primary_key=True)
    key_hash = fields.CharField(max_length=64, unique=True)
    connector: fields.ForeignKeyRelation[Connector] = fields.ForeignKeyField(
        "models.Connector",
        related_name="api_keys",
        on_delete=fields.CASCADE,
    )
    enabled = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta(BaseModel.Meta):
        table = "connector_api_keys"
        schema = "backend"
