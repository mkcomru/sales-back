from __future__ import annotations

import asyncio

import structlog

from common.transport.base_manager import BaseConnectorManager
from wazzup_module.config import Settings
from wazzup_module.connectors.models import WazzupConnectorConfig
from wazzup_module.services.backend import WazzupBackendClient
from wazzup_module.services.wazzup_api import WazzupApiClient

log = structlog.get_logger(__name__)


class ConnectorManager(BaseConnectorManager[WazzupConnectorConfig]):
    """Manage Wazzup connectors lifecycle and config reloads."""

    def __init__(
        self,
        settings: Settings,
        backend: WazzupBackendClient,
        wazzup_client: WazzupApiClient,
    ) -> None:
        self._settings = settings
        self._backend = backend
        self._wazzup_client = wazzup_client
        self._webhook_url = settings.webhook_url
        self._connectors: dict[str, WazzupConnectorConfig] = {}
        self._lock = asyncio.Lock()

    def get(self, connector_id: str) -> WazzupConnectorConfig | None:
        return self._connectors.get(connector_id)

    async def reload(self) -> None:
        current_task = asyncio.current_task()
        if current_task is not None and current_task.cancelled():
            raise asyncio.CancelledError

        try:
            connector_configs = await self._backend.fetch_connectors()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("connector.reload.failed", error=str(exc))
            raise

        current_task = asyncio.current_task()
        if current_task is not None and current_task.cancelled():
            raise asyncio.CancelledError

        added_connectors: list[WazzupConnectorConfig] = []

        async with self._lock:
            new_configs_dict = {cfg.connector_id: cfg for cfg in connector_configs}
            existing_ids = set(self._connectors.keys())
            new_ids = set(new_configs_dict.keys())

            for connector_id in existing_ids - new_ids:
                del self._connectors[connector_id]
                log.info("connector.removed", connector_id=connector_id)

            for connector_id in new_ids - existing_ids:
                cfg = new_configs_dict[connector_id]
                self._connectors[connector_id] = cfg
                log.info("connector.added", connector_id=connector_id)
                added_connectors.append(cfg)

            for connector_id in existing_ids & new_ids:
                old_config = self._connectors[connector_id]
                new_config = new_configs_dict[connector_id]
                if self._config_changed(old_config, new_config):
                    self._connectors[connector_id] = new_config
                    log.info("connector.updated", connector_id=connector_id)
                else:
                    log.debug("connector.unchanged", connector_id=connector_id)

        log.debug("connector.reload.completed", count=len(connector_configs))

        for cfg in added_connectors:
            await self._register_webhook(cfg.connector_id, cfg)

    async def shutdown(self) -> None:
        try:
            await asyncio.wait_for(self._acquire_lock_and_shutdown(), timeout=5.0)
        except TimeoutError:
            log.warning("connector.shutdown.lock_timeout", message="Lock timeout, forcing shutdown")
            await self._shutdown_all()

    async def _acquire_lock_and_shutdown(self) -> None:
        async with self._lock:
            await self._shutdown_all()

    async def _shutdown_all(self) -> None:
        self._connectors.clear()

    def get_by_channel_id(self, channel_id: str) -> WazzupConnectorConfig | None:
        for connector in self._connectors.values():
            if connector.channel_id == channel_id:
                return connector
        return None

    async def _register_webhook(self, connector_id: str, config: WazzupConnectorConfig) -> None:
        if not self._webhook_url:
            log.warning("connector.webhook.url_not_configured", connector_id=connector_id)
            return
        try:
            await self._wazzup_client.register_webhook(
                api_key=config.wazzup_api_key.get_secret_value(),
                webhook_uri=str(self._webhook_url),
            )
            log.info("connector.webhook.registered", connector_id=connector_id)
        except Exception as exc:
            log.error("connector.webhook.registration_failed", connector_id=connector_id, error=str(exc))

    def _config_changed(self, old: WazzupConnectorConfig, new: WazzupConnectorConfig) -> bool:
        old_dict = old.model_dump(exclude={"wazzup_api_key"})
        new_dict = new.model_dump(exclude={"wazzup_api_key"})
        if old_dict != new_dict:
            return True
        if old.wazzup_api_key.get_secret_value() != new.wazzup_api_key.get_secret_value():
            return True
        return False
