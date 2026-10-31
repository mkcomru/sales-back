"""Sync controller for managing history synchronization."""

from __future__ import annotations

import asyncio
from datetime import datetime

import structlog

from common.contracts.sync import SyncCancelCommand, SyncStartCommand
from common.sync.client import BackendSyncClient
from common.sync.runner import SyncRunner, SyncRunnerError
from wappi_module.config import Settings
from wappi_module.connectors.manager import ConnectorManager
from wappi_module.services.backend import WappiBackendClient
from wappi_module.services.wappi_api import WappiApiClient
from wappi_module.sync.provider import WappiSyncProvider

log = structlog.get_logger(__name__)


class SyncController:
    """Manages sync jobs for Wappi connectors."""

    def __init__(
        self,
        *,
        settings: Settings,
        connector_manager: ConnectorManager,
        wappi_client: WappiApiClient,
        backend_client: WappiBackendClient,
    ):
        """Initialize sync controller.

        Args:
            settings: Application settings
            connector_manager: Connector manager for retrieving configs
            wappi_client: Wappi API client
            backend_client: Backend client for media uploads
        """
        self._settings = settings
        self._connector_manager = connector_manager
        self._wappi_client = wappi_client
        self._backend_client = backend_client
        self._active_syncs: dict[str, SyncRunner] = {}
        self._sync_tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def start_sync(self, command: SyncStartCommand) -> None:
        """Start sync job for a connector.

        Args:
            command: Sync start command from backend

        Raises:
            ValueError: If connector not found or sync already running
        """
        async with self._lock:
            if command.correlation_id in self._active_syncs:
                raise ValueError(f"Sync with correlation_id {command.correlation_id} already running")

            connector_config = self._connector_manager.get(command.connector_id)
            if not connector_config:
                # AICODE-NOTE: Reload connectors if not found - connector might have been just created
                log.debug(
                    "sync.controller.connector_not_found_reloading",
                    connector_id=command.connector_id,
                )
                try:
                    await self._connector_manager.reload()
                except Exception as exc:
                    log.warning(
                        "sync.controller.reload_failed",
                        connector_id=command.connector_id,
                        error=str(exc),
                    )
                connector_config = self._connector_manager.get(command.connector_id)
                if not connector_config:
                    raise ValueError(f"Connector {command.connector_id} not found")

            # Create provider and client
            provider = WappiSyncProvider(
                connector_config=connector_config,
                wappi_client=self._wappi_client,
                backend_client=self._backend_client,
                initial_sync_messages_limit=self._settings.initial_sync_messages_limit,
                initial_sync_dialogs_limit=self._settings.initial_sync_dialogs_limit,
            )

            backend_url = self._settings.backend.url
            if not backend_url:
                raise ValueError("Backend URL not configured")

            service_key = self._settings.service.api_key
            if not service_key:
                raise ValueError("Service API key not configured")

            client = BackendSyncClient(
                base_url=backend_url,
                service_key=service_key.get_secret_value(),
                service_header=self._settings.service.resolved_header(),
            )

            # Create runner
            runner = SyncRunner(
                provider=provider,
                client=client,
                connector_id=command.connector_id,
                correlation_id=command.correlation_id,
            )

            # Store runner
            self._active_syncs[command.correlation_id] = runner

            # Start sync in background task
            task = asyncio.create_task(
                self._run_sync(
                    runner=runner,
                    correlation_id=command.correlation_id,
                    sync_type=command.sync_type,
                    cursor=command.cursor,
                    since=command.since,
                )
            )
            self._sync_tasks[command.correlation_id] = task

            log.info(
                "sync.controller.started",
                connector_id=command.connector_id,
                correlation_id=command.correlation_id,
                sync_type=command.sync_type,
            )

    async def cancel_sync(self, command: SyncCancelCommand) -> None:
        """Cancel sync job.

        Args:
            command: Sync cancel command from backend

        Raises:
            ValueError: If sync not found
        """
        async with self._lock:
            runner = self._active_syncs.get(command.correlation_id)
            if not runner:
                raise ValueError(f"Sync with correlation_id {command.correlation_id} not found")

            # Cancel runner
            runner.cancel()

            # Cancel task
            task = self._sync_tasks.get(command.correlation_id)
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Cleanup
            del self._active_syncs[command.correlation_id]
            if command.correlation_id in self._sync_tasks:
                del self._sync_tasks[command.correlation_id]

            log.info(
                "sync.controller.cancelled",
                connector_id=command.connector_id,
                correlation_id=command.correlation_id,
            )

    async def _run_sync(
        self,
        runner: SyncRunner,
        correlation_id: str,
        sync_type: str,
        cursor: str | None,
        since: datetime | None,
    ) -> None:
        """Run sync job and cleanup on completion.

        Args:
            runner: Sync runner instance
            correlation_id: Correlation ID for tracking
            sync_type: Type of sync
            cursor: Optional cursor for resume
            since: Optional start date for catchup
        """
        try:
            await runner.run(
                sync_type=sync_type,
                cursor=cursor,
                since=since,
            )
        except SyncRunnerError as exc:
            log.error(
                "sync.controller.runner_failed",
                correlation_id=correlation_id,
                error=str(exc),
            )
        except Exception as exc:
            log.exception(
                "sync.controller.unexpected_error",
                correlation_id=correlation_id,
                error=str(exc),
            )
        finally:
            # Cleanup
            async with self._lock:
                if correlation_id in self._active_syncs:
                    del self._active_syncs[correlation_id]
                if correlation_id in self._sync_tasks:
                    del self._sync_tasks[correlation_id]

            # Close client
            await runner.client.close()

            log.info(
                "sync.controller.completed",
                correlation_id=correlation_id,
            )
