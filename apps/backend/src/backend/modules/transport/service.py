from __future__ import annotations

import asyncio
import hashlib
import secrets
from binascii import Error as BinAsciiError
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from cryptography.fernet import InvalidToken
from pydantic import ValidationError

from common.crypto import EncryptedPayload, EnvelopeEncryption
from common.events.contracts import ChangeType, ResourceType
from common.models import ConnectorContext, DebounceConfig

from src.backend.modules.companies.exceptions import CompanyNotFoundError
from src.backend.modules.companies.models import Company
from src.backend.modules.companies.repository import CompaniesRepository
from src.backend.modules.core.settings import get_settings
from src.backend.modules.prompt_addon.exceptions import PromptAddonNotFoundError
from src.backend.modules.prompt_addon.models import PromptAddon
from src.backend.modules.transport.exceptions import ConnectorNotFoundError
from src.backend.modules.transport.models import Connector, ConnectorType, SyncStatus
from src.backend.modules.transport.repository import ConnectorApiKeysRepository, ConnectorsRepository
from src.backend.modules.transport.schemas import (
    ConnectorApiKeyListItem,
    ConnectorApiKeyResponse,
    ConnectorCreateRequest,
    ConnectorResponse,
    ConnectorTypeEnum,
    ConnectorUpdateRequest,
    SyncStatusEnum,
)
from src.backend.modules.transport.sync_commander import SyncCommander, SyncCommanderError
from src.backend.services.events.publisher import publish_transport_connectors_changed

log = structlog.get_logger(__name__)

SENSITIVE_FIELDS: dict[ConnectorType, frozenset[str]] = {
    ConnectorType.TELEGRAM: frozenset({"bot_token", "webhook_secret"}),
    ConnectorType.WAPPI: frozenset({"wappi_token"}),
    ConnectorType.WAZZUP: frozenset({"wazzup_api_key"}),
    ConnectorType.CUSTOM: frozenset(),
}

# intentionally not configurable
API_KEY_PREFIX = "sk_"  # pragma: allowlist secret


def _generate_api_key() -> str:
    """Generate a new API key with sk_ prefix."""
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def _hash_key(raw_key: str) -> str:
    """Hash an API key using SHA-256."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


class ConnectorsService:
    """Service for unified Connector model operations."""

    connectors_repo: ConnectorsRepository = ConnectorsRepository()
    api_keys_repo: ConnectorApiKeysRepository = ConnectorApiKeysRepository()
    companies_repo: CompaniesRepository = CompaniesRepository()
    _sync_commander: SyncCommander | None = None

    @property
    def sync_commander(self) -> SyncCommander:
        """Lazy initialization of SyncCommander."""
        if self._sync_commander is None:
            self._sync_commander = SyncCommander()
        return self._sync_commander

    def _get_encryption(self) -> EnvelopeEncryption:
        settings = get_settings()
        master_key = settings.encryption.master_key
        if not master_key:
            raise RuntimeError("ENCRYPTION__MASTER_KEY is not configured")
        return EnvelopeEncryption(master_key.get_secret_value())

    def _encrypt_config(self, connector_type: ConnectorType, config: dict[str, Any]) -> dict[str, Any]:
        sensitive = SENSITIVE_FIELDS[connector_type]
        if not sensitive:
            return config
        enc = self._get_encryption()
        result = dict(config)
        for field in sensitive:
            if field in result and isinstance(result[field], str):
                payload = enc.encrypt(result[field].encode())
                result[field] = payload.model_dump()
        return result

    def _decrypt_config(self, connector_type: ConnectorType, config: dict[str, Any]) -> dict[str, Any]:
        sensitive = SENSITIVE_FIELDS[connector_type]
        if not sensitive:
            return config
        enc = self._get_encryption()
        result = dict(config)
        for field in sensitive:
            if field in result and isinstance(result[field], dict):
                try:
                    payload = EncryptedPayload.model_validate(result[field])
                    result[field] = enc.decrypt(payload).decode()
                except (ValidationError, InvalidToken, ValueError, BinAsciiError) as exc:
                    raise RuntimeError(f"Decryption failed for field '{field}'") from exc
        return result

    def _strip_credentials(self, connector_type: ConnectorType, config: dict[str, Any]) -> dict[str, Any]:
        sensitive = SENSITIVE_FIELDS[connector_type]
        return {k: v for k, v in config.items() if k not in sensitive}

    async def list_connectors(
        self,
        type_filter: str | None = None,
        enabled_filter: bool | None = None,
    ) -> list[ConnectorResponse]:
        connectors = await self.connectors_repo.list_filtered(
            type_filter=type_filter,
            enabled_filter=enabled_filter,
        )
        return [self._to_response(c) for c in connectors]

    async def list_by_company(self, company_id: int) -> list[ConnectorResponse]:
        connectors = await self.connectors_repo.list_by_company(company_id)
        return [self._to_response(c) for c in connectors]

    async def get_connector(self, connector_db_id: int) -> ConnectorResponse:
        connector = await self.connectors_repo.get_by_id(connector_db_id)
        if not connector:
            raise ConnectorNotFoundError()
        return self._to_response(connector)

    async def get_by_connector_id(self, connector_id: str) -> Connector | None:
        """Get connector by public connector_id (for managed connector lookup)."""
        return await self.connectors_repo.get_by_connector_id(connector_id)

    async def get_context_by_connector_id(self, connector_id: str) -> ConnectorContext:
        """Build ConnectorContext for managed connector (service key auth)."""
        connector = await self.connectors_repo.get_by_connector_id(connector_id)
        if not connector:
            raise ConnectorNotFoundError()
        if not connector.enabled:
            raise ConnectorNotFoundError()
        return self._build_context(connector)

    async def validate_api_key(self, raw_key: str) -> ConnectorContext:
        """Validate Bearer token and return ConnectorContext (custom connector auth)."""
        if not raw_key.startswith(API_KEY_PREFIX):
            raise ConnectorNotFoundError()

        key_hash = _hash_key(raw_key)
        api_key = await self.api_keys_repo.get_enabled_by_hash(key_hash)
        if not api_key:
            raise ConnectorNotFoundError()

        connector = api_key.connector
        if not isinstance(connector, Connector):
            raise ConnectorNotFoundError()

        if not connector.enabled:
            raise ConnectorNotFoundError()

        return self._build_context(connector)

    async def create_connector(self, payload: ConnectorCreateRequest) -> ConnectorResponse:
        await self._ensure_company(payload.company_id)

        config_dict = dict(payload.config or {})

        if payload.managed and payload.type != ConnectorTypeEnum.CUSTOM and not config_dict.get("transport_endpoint"):
            settings = get_settings()
            match payload.type:
                case ConnectorTypeEnum.TELEGRAM:
                    if settings.transport.telegram.url:
                        config_dict["transport_endpoint"] = str(settings.transport.telegram.url)
                case ConnectorTypeEnum.WAPPI:
                    if settings.transport.wappi.url:
                        config_dict["transport_endpoint"] = str(settings.transport.wappi.url)
                case ConnectorTypeEnum.WAZZUP:
                    if settings.transport.wazzup.url:
                        config_dict["transport_endpoint"] = str(settings.transport.wazzup.url)

        connector_type = ConnectorType(payload.type.value)
        config_dict = self._encrypt_config(connector_type, config_dict)

        connector = await self.connectors_repo.create_connector(
            connector_id=payload.connector_id,
            company_id=payload.company_id,
            connector_type=connector_type,
            channel_type=payload.channel_type,
            display_name=payload.display_name,
            managed=payload.managed,
            config=config_dict,
            enabled=payload.enabled,
            debounce_window_seconds=payload.debounce_window_seconds,
            debounce_storage_key_template=payload.debounce_storage_key_template,
        )
        await connector.fetch_related("company")

        await publish_transport_connectors_changed(
            change_type=ChangeType.UPSERT,
            resource=ResourceType.CONNECTORS_AGGREGATE,
            company_id=payload.company_id,
            connector_id=payload.connector_id,
        )

        # AICODE-NOTE: Auto-start initial sync for managed connectors in background
        if payload.managed and payload.enabled:
            asyncio.create_task(self._auto_start_initial_sync(payload.connector_id))

        return self._to_response(connector)

    async def update_connector(self, connector_db_id: int, payload: ConnectorUpdateRequest) -> ConnectorResponse:
        connector = await self.connectors_repo.get_by_id(connector_db_id)
        if not connector:
            raise ConnectorNotFoundError()

        updates: dict[str, Any] = {}

        if payload.company_id is not None:
            await self._ensure_company(payload.company_id)
            updates["company_id"] = payload.company_id
        if payload.connector_id is not None:
            updates["connector_id"] = payload.connector_id
        if payload.type is not None:
            updates["type"] = ConnectorType(payload.type.value)
        if payload.channel_type is not None:
            updates["channel_type"] = payload.channel_type
        if payload.display_name is not None:
            updates["display_name"] = payload.display_name
        if payload.managed is not None:
            updates["managed"] = payload.managed
        if payload.config is not None:
            effective_type = ConnectorType(payload.type.value) if payload.type is not None else connector.type
            merged = {**(connector.config or {}), **payload.config}
            updates["config"] = self._encrypt_config(effective_type, merged)
        if payload.enabled is not None:
            updates["enabled"] = payload.enabled
        if payload.prompt_addon_id is not None:
            if payload.prompt_addon_id:
                addon = await PromptAddon.get_or_none(id=payload.prompt_addon_id)
                if not addon:
                    raise PromptAddonNotFoundError()

                if addon.company_id != connector.company_id:
                    raise PromptAddonNotFoundError()

            updates["prompt_addon_id"] = payload.prompt_addon_id
        if payload.debounce_window_seconds is not None:
            updates["debounce_window_seconds"] = payload.debounce_window_seconds
        if payload.debounce_storage_key_template is not None:
            updates["debounce_storage_key_template"] = payload.debounce_storage_key_template

        # AICODE-NOTE: Check if connector is being enabled and needs sync
        # Get current connector state before update
        was_enabled = connector.enabled

        connector = await self.connectors_repo.update_connector(connector_db_id, updates)
        if not connector:
            raise ConnectorNotFoundError()

        await connector.fetch_related("company")
        company = self._require_company(connector)

        # AICODE-NOTE: Auto-start initial sync if connector was enabled and sync never completed
        if payload.enabled is not None:
            is_now_enabled = payload.enabled
            was_disabled = was_enabled is False
            if was_disabled and is_now_enabled:
                # Connector was just enabled - check if sync is needed
                if connector.sync_completed_at is None and connector.managed:
                    log.info(
                        "sync.auto_start.on_enable",
                        connector_id=connector.connector_id,
                        was_enabled=was_enabled,
                        is_now_enabled=is_now_enabled,
                    )
                    asyncio.create_task(self._auto_start_initial_sync(connector.connector_id))

        await publish_transport_connectors_changed(
            change_type=ChangeType.UPSERT,
            resource=ResourceType.CONNECTORS_AGGREGATE,
            company_id=company.id,
            connector_id=connector.connector_id,
        )

        return self._to_response(connector)

    async def update_connector_prompt_addon(
        self, company_id: int, connector_id: str, prompt_addon_id: int | None
    ) -> ConnectorResponse:
        """Update prompt_addon_id for a connector by connector_id.

        Args:
            company_id: Company identifier
            connector_id: Public connector identifier
            prompt_addon_id: Prompt addon ID to assign, or None to remove

        Returns:
            Updated connector response
        """
        connector = await self.connectors_repo.get_by_connector_id(connector_id)
        if not connector:
            raise ConnectorNotFoundError()

        if connector.company_id != company_id:
            raise ConnectorNotFoundError()

        if prompt_addon_id is not None:
            addon = await PromptAddon.get_or_none(id=prompt_addon_id)
            if not addon:
                raise PromptAddonNotFoundError()
            if addon.company_id != company_id:
                raise PromptAddonNotFoundError()

        connector.prompt_addon_id = prompt_addon_id
        await connector.save(update_fields=["prompt_addon_id"])

        await connector.fetch_related("company")
        company = self._require_company(connector)

        await publish_transport_connectors_changed(
            change_type=ChangeType.UPSERT,
            resource=ResourceType.CONNECTORS_AGGREGATE,
            company_id=company.id,
            connector_id=connector.connector_id,
        )

        return self._to_response(connector)

    async def delete_connector(self, connector_db_id: int) -> None:
        connector = await self.connectors_repo.get_by_id(connector_db_id)
        if not connector:
            raise ConnectorNotFoundError()

        company_id = connector.company_id
        connector_id = connector.connector_id

        removed = await self.connectors_repo.delete_connector(connector_db_id)
        if not removed:
            raise ConnectorNotFoundError()

        await publish_transport_connectors_changed(
            change_type=ChangeType.DELETE,
            resource=ResourceType.CONNECTORS_AGGREGATE,
            company_id=company_id,
            connector_id=connector_id,
        )

    async def create_api_key(self, connector_db_id: int) -> ConnectorApiKeyResponse:
        """Create new API key for a connector (custom connectors only)."""
        connector = await self.connectors_repo.get_by_id(connector_db_id)
        if not connector:
            raise ConnectorNotFoundError()

        raw_key = _generate_api_key()
        key_hash = _hash_key(raw_key)

        api_key = await self.api_keys_repo.create_key(
            key_hash=key_hash,
            connector_id=connector_db_id,
            enabled=True,
        )
        return ConnectorApiKeyResponse(
            id=api_key.id,
            connector_id=connector.connector_id,
            raw_key=raw_key,
            created_at=api_key.created_at,
        )

    async def list_api_keys(self, connector_db_id: int) -> list[ConnectorApiKeyListItem]:
        keys = await self.api_keys_repo.list_by_connector(connector_db_id)
        return [
            ConnectorApiKeyListItem(
                id=k.id,
                enabled=k.enabled,
                created_at=k.created_at,
            )
            for k in keys
        ]

    async def disable_api_key(self, key_id: int) -> None:
        key = await self.api_keys_repo.disable_key(key_id)
        if not key:
            raise ConnectorNotFoundError()

    async def delete_api_key(self, key_id: int) -> None:
        removed = await self.api_keys_repo.delete_key(key_id)
        if not removed:
            raise ConnectorNotFoundError()

    async def list_connectors_decrypted(
        self,
        type_filter: str | None = None,
        enabled_filter: bool | None = None,
    ) -> list[ConnectorResponse]:
        """Return connectors with decrypted credentials in config (for internal service use)."""
        connectors = await self.connectors_repo.list_filtered(
            type_filter=type_filter,
            enabled_filter=enabled_filter,
        )
        result = []
        for c in connectors:
            try:
                result.append(self._to_response_decrypted(c))
            except RuntimeError:
                log.error("connector.decrypt.failed", connector_id=c.connector_id, connector_type=c.type.value)
        return result

    async def get_connector_decrypted(self, connector_db_id: int) -> ConnectorResponse:
        """Return connector with decrypted credentials in config (for internal service use)."""
        connector = await self.connectors_repo.get_by_id(connector_db_id)
        if not connector:
            raise ConnectorNotFoundError()
        return self._to_response_decrypted(connector)

    async def _ensure_company(self, company_id: int) -> None:
        company = await self.companies_repo.get_by_id(company_id)
        if not company:
            raise CompanyNotFoundError()

    def _require_company(self, connector: Connector) -> Company:
        company = connector.company
        if not isinstance(company, Company):
            raise RuntimeError("Connector company relation is not loaded; ensure prefetch_related is applied.")
        return company

    def _build_context(self, connector: Connector) -> ConnectorContext:
        company = self._require_company(connector)
        return ConnectorContext(
            connector_id=connector.connector_id,
            company_id=company.id,
            type=connector.type.value,
            channel_type=connector.channel_type,
            debounce=DebounceConfig(
                window_seconds=connector.debounce_window_seconds,
                storage_key_template=connector.debounce_storage_key_template,
            ),
        )

    def _to_response(self, connector: Connector) -> ConnectorResponse:
        public_config = self._strip_credentials(connector.type, dict(connector.config or {}))
        return self._build_response(connector, public_config)

    def _to_response_decrypted(self, connector: Connector) -> ConnectorResponse:
        decrypted_config = self._decrypt_config(connector.type, dict(connector.config or {}))
        return self._build_response(connector, decrypted_config)

    def _build_response(self, connector: Connector, config: dict[str, Any]) -> ConnectorResponse:
        company = self._require_company(connector)
        return ConnectorResponse(
            id=connector.id,
            connector_id=connector.connector_id,
            company_id=company.id,
            type=ConnectorTypeEnum(connector.type.value),
            channel_type=connector.channel_type,
            display_name=connector.display_name,
            managed=connector.managed,
            config=config,
            enabled=connector.enabled,
            debounce_window_seconds=connector.debounce_window_seconds,
            debounce_storage_key_template=connector.debounce_storage_key_template,
            sync_status=SyncStatusEnum(connector.sync_status.value),
            sync_started_at=connector.sync_started_at,
            sync_completed_at=connector.sync_completed_at,
            sync_progress=dict(connector.sync_progress or {}),
            prompt_addon_id=connector.prompt_addon_id,
            created_at=connector.created_at,
            updated_at=connector.updated_at,
        )

    async def start_sync(
        self,
        connector_id: str,
        sync_type: str,
        since: datetime | None = None,
    ) -> str:
        """Start sync for a connector by sending command to connector module.

        Args:
            connector_id: Connector identifier
            sync_type: Type of sync (initial, backfill, catchup)
            since: Optional start date for catchup sync

        Returns:
            Correlation ID for tracking sync job

        Raises:
            ConnectorNotFoundError: If connector not found
            ValueError: If connector is not managed or sync already running
        """
        connector = await self.connectors_repo.get_by_connector_id(connector_id)
        if not connector:
            raise ConnectorNotFoundError()

        if not connector.managed:
            raise ValueError(f"Connector {connector_id} is not managed, cannot start sync")

        if connector.sync_status not in (SyncStatus.IDLE, SyncStatus.COMPLETED, SyncStatus.FAILED):
            raise ValueError(f"Sync already running for connector {connector_id}")

        # Generate correlation ID
        correlation_id = SyncCommander.generate_correlation_id()

        # Get cursor for resume if available
        cursor = connector.sync_progress.get("cursor") if connector.sync_progress else None

        # Update status to INITIAL
        await self.connectors_repo.update_connector(
            connector.id,
            {
                "sync_status": SyncStatus.INITIAL,
                "sync_started_at": datetime.now(UTC),
            },
        )

        # Send command to connector (fire-and-forget with timeout handling)
        asyncio.create_task(self._send_sync_command(connector, sync_type, correlation_id, cursor, since))

        log.info(
            "sync.start.command_sent",
            connector_id=connector_id,
            correlation_id=correlation_id,
            sync_type=sync_type,
        )

        return correlation_id

    async def _send_sync_command(
        self,
        connector: Connector,
        sync_type: str,
        correlation_id: str,
        cursor: str | None,
        since: datetime | None,
    ) -> None:
        """Send sync command to connector module (background task).

        Errors are logged but not raised to avoid breaking the main flow.
        """
        try:
            await self.sync_commander.send_start(
                connector=connector,
                sync_type=sync_type,
                correlation_id=correlation_id,
                cursor=cursor,
                since=since,
            )
            log.info(
                "sync.command.sent",
                connector_id=connector.connector_id,
                correlation_id=correlation_id,
                sync_type=sync_type,
            )
        except SyncCommanderError as exc:
            # Command failed - mark sync as FAILED
            await self.connectors_repo.update_connector(
                connector.id,
                {
                    "sync_status": SyncStatus.FAILED,
                    "sync_completed_at": datetime.now(UTC),
                },
            )
            log.error(
                "sync.command.failed",
                connector_id=connector.connector_id,
                correlation_id=correlation_id,
                error=str(exc),
            )
        except Exception as exc:
            log.exception(
                "sync.command.unexpected_error",
                connector_id=connector.connector_id,
                correlation_id=correlation_id,
                error=str(exc),
            )

    async def cancel_sync(self, connector_id: str) -> None:
        """Cancel sync for a connector by sending command to connector module.

        Args:
            connector_id: Connector identifier

        Raises:
            ConnectorNotFoundError: If connector not found
            ValueError: If connector is not managed or sync not running
        """
        connector = await self.connectors_repo.get_by_connector_id(connector_id)
        if not connector:
            raise ConnectorNotFoundError()

        if not connector.managed:
            raise ValueError(f"Connector {connector_id} is not managed, cannot cancel sync")

        if connector.sync_status not in (SyncStatus.INITIAL, SyncStatus.BACKFILL, SyncStatus.CATCHUP):
            raise ValueError(f"Sync not running for connector {connector_id}")

        # Send cancel command (fire-and-forget)
        asyncio.create_task(self._send_cancel_command(connector))

        log.info("sync.cancel.command_sent", connector_id=connector_id)

    async def _send_cancel_command(self, connector: Connector) -> None:
        """Send cancel command to connector module (background task).

        Errors are logged but not raised.
        """
        try:
            await self.sync_commander.send_cancel(connector=connector)
            log.info("sync.cancel.command_sent", connector_id=connector.connector_id)
        except SyncCommanderError as exc:
            log.error(
                "sync.cancel.command.failed",
                connector_id=connector.connector_id,
                error=str(exc),
            )
        except Exception as exc:
            log.exception(
                "sync.cancel.command.unexpected_error",
                connector_id=connector.connector_id,
                error=str(exc),
            )

    async def sync_more_chats(self, connector_id: str) -> None:
        """Load more chats for a connector by calling transport module directly.

        This endpoint is used to continue loading chats that weren't loaded during
        initial sync (which is limited by initial_sync_dialogs_limit).

        Args:
            connector_id: Connector identifier

        Raises:
            ConnectorNotFoundError: If connector not found
            ValueError: If connector is not managed or unsupported type
        """
        settings = get_settings()

        connector = await self.connectors_repo.get_by_connector_id(connector_id)
        if not connector:
            raise ConnectorNotFoundError()

        if not connector.managed:
            raise ValueError(f"Connector {connector_id} is not managed, cannot sync more chats")

        # Determine transport module URL based on connector type
        transport_url: str | None = None
        sync_path: str = ""

        if connector.type == ConnectorType.WAPPI:
            transport_url = settings.transport.wappi.url
            sync_path = f"wappi/sync/{connector_id}/more-chats"
        else:
            raise ValueError(f"Sync more chats not supported for connector type: {connector.type}")

        if not transport_url:
            raise ValueError(f"Transport module URL not configured for type: {connector.type}")

        # Trigger sync in transport module (background task)
        asyncio.create_task(self._call_sync_more_chats(connector, transport_url, sync_path))

        log.info(
            "sync.more_chats.triggered",
            connector_id=connector_id,
            connector_type=connector.type.value,
        )

    async def _call_sync_more_chats(
        self,
        connector: Connector,
        transport_url: str,
        sync_path: str,
    ) -> None:
        """Call transport module to sync more chats (background task)."""
        settings = get_settings()

        try:
            url = f"{str(transport_url).rstrip('/')}/{sync_path}"
            headers = {"X-Service-Key": settings.service.api_key.get_secret_value()}

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers)
                response.raise_for_status()

            log.info(
                "sync.more_chats.success",
                connector_id=connector.connector_id,
            )
        except httpx.HTTPError as exc:
            log.error(
                "sync.more_chats.failed",
                connector_id=connector.connector_id,
                error=str(exc),
            )
        except Exception as exc:
            log.exception(
                "sync.more_chats.unexpected_error",
                connector_id=connector.connector_id,
                error=str(exc),
            )

    async def _auto_start_initial_sync(self, connector_id: str) -> None:
        """Auto-start initial sync in background (non-blocking).

        This method is called as a background task and should not block the main response.
        Errors are logged but not raised to avoid breaking the main flow.
        """
        try:
            log.info("sync.auto_start.triggered", connector_id=connector_id)
            await self.start_sync(connector_id, sync_type="initial")
            log.info("sync.auto_start.started", connector_id=connector_id)
        except (ConnectorNotFoundError, ValueError) as exc:
            # Connector not found, already syncing, or invalid - log but don't fail
            log.warning("sync.auto_start.skipped", connector_id=connector_id, reason=str(exc))
        except Exception as exc:
            # Any other error - log but don't fail
            log.exception("sync.auto_start.failed", connector_id=connector_id, error=str(exc))
