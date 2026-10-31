from __future__ import annotations

import asyncio

import structlog

from common.transport.base_manager import BaseConnectorManager
from wappi_module.config import Settings
from wappi_module.connectors.models import WappiConnectorConfig
from wappi_module.services.backend import WappiBackendClient

log = structlog.get_logger(__name__)


class ConnectorManager(BaseConnectorManager[WappiConnectorConfig]):
    """Manage Wappi connectors lifecycle and config reloads."""

    def __init__(self, settings: Settings, backend: WappiBackendClient) -> None:
        self._settings = settings
        self._backend = backend
        self._connectors: dict[str, WappiConnectorConfig] = {}
        self._lock = asyncio.Lock()

    def get(self, connector_id: str) -> WappiConnectorConfig | None:
        return self._connectors.get(connector_id)

    async def reload(self) -> None:
        """Reload connectors configuration from backend service."""
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

        async with self._lock:
            new_configs_dict = {cfg.connector_id: cfg for cfg in connector_configs}
            existing_ids = set(self._connectors.keys())
            new_ids = set(new_configs_dict.keys())

            to_remove = existing_ids - new_ids
            to_add = new_ids - existing_ids
            to_update = existing_ids & new_ids

            for connector_id in to_remove:
                del self._connectors[connector_id]
                log.info("connector.removed", connector_id=connector_id)

            for connector_id in to_add:
                self._connectors[connector_id] = new_configs_dict[connector_id]
                log.info("connector.added", connector_id=connector_id)

            for connector_id in to_update:
                old_config = self._connectors[connector_id]
                new_config = new_configs_dict[connector_id]
                if self._config_changed(old_config, new_config):
                    self._connectors[connector_id] = new_config
                    log.info("connector.updated", connector_id=connector_id)
                else:
                    log.debug("connector.unchanged", connector_id=connector_id)

        log.debug("connector.reload.completed", count=len(connector_configs))

    async def shutdown(self) -> None:
        try:
            await asyncio.wait_for(self._acquire_lock_and_shutdown(), timeout=5.0)
        except TimeoutError:
            log.warning(
                "connector.shutdown.lock_timeout",
                message="Lock timeout, forcing shutdown",
            )
            await self._shutdown_all()

    async def _acquire_lock_and_shutdown(self) -> None:
        async with self._lock:
            await self._shutdown_all()

    async def _shutdown_all(self) -> None:
        self._connectors.clear()

    def _config_changed(self, old: WappiConnectorConfig, new: WappiConnectorConfig) -> bool:
        old_dict = old.model_dump(exclude={"wappi_token"})
        new_dict = new.model_dump(exclude={"wappi_token"})
        if old_dict != new_dict:
            return True
        if old.wappi_token.get_secret_value() != new.wappi_token.get_secret_value():
            return True
        return False
