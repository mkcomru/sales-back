"""Sync runner for orchestrating history synchronization."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING

import structlog

from common.contracts.sync import SyncProgress, SyncStatus
from common.sync.base import BaseSyncProvider
from common.sync.client import BackendSyncClient, BackendSyncClientError
from common.sync.rate_limiter import RateLimiter

if TYPE_CHECKING:
    pass

log = structlog.get_logger(__name__)

BATCH_SIZE = 50
MAX_RETRIES = 3
RETRY_DELAY_BASE = 1.0
HEARTBEAT_INTERVAL_SECONDS = 30.0


class SyncRunnerError(Exception):
    """Raised when sync runner encounters unrecoverable error."""


class SyncRunner:
    """Orchestrates sync process using provider and backend client.

    Handles:
    - Fetching dialogs and messages from provider
    - Transforming messages to SyncMessage format
    - Batching and sending to backend
    - Progress tracking
    - Error handling with retry
    - Background heartbeat
    """

    def __init__(
        self,
        *,
        provider: BaseSyncProvider,
        client: BackendSyncClient,
        connector_id: str,
        correlation_id: str,
    ):
        """Initialize sync runner.

        Args:
            provider: Sync provider implementation
            client: Backend sync client
            connector_id: Connector identifier
            correlation_id: Correlation ID for tracking
        """
        self.provider = provider
        self.client = client
        self.connector_id = connector_id
        self.correlation_id = correlation_id
        self.rate_limiter = RateLimiter(rate=provider.get_rate_limit())
        self._cancelled = False
        self._heartbeat_task: asyncio.Task | None = None

    async def run(
        self,
        *,
        sync_type: str,
        cursor: str | None = None,
        since: datetime | None = None,
    ) -> None:
        """Run sync process.

        Args:
            sync_type: Type of sync (initial, backfill, catchup)
            cursor: Optional cursor for resume
            since: Optional start date for catchup

        Raises:
            SyncRunnerError: If sync fails unrecoverably
        """
        log.info(
            "sync.runner.started",
            connector_id=self.connector_id,
            correlation_id=self.correlation_id,
            sync_type=sync_type,
            cursor=cursor,
        )

        try:
            # Start background heartbeat task
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            # Update status to INITIAL/BACKFILL/CATCHUP
            status_map = {
                "initial": SyncStatus.INITIAL,
                "backfill": SyncStatus.BACKFILL,
                "catchup": SyncStatus.CATCHUP,
            }
            status = status_map.get(sync_type, SyncStatus.INITIAL)

            await self.client.update_status(
                connector_id=self.connector_id,
                correlation_id=self.correlation_id,
                status=status,
            )

            # Fetch dialogs
            total_chats = 0
            processed_chats = 0
            total_messages = 0
            processed_messages = 0

            since_str = since.isoformat() if since else None

            # For initial sync, limit messages per dialog and total dialogs
            max_messages = self.provider.get_initial_sync_limit() if sync_type == "initial" else None
            max_dialogs = self.provider.get_initial_dialogs_limit() if sync_type == "initial" else None

            async for dialog in self.provider.fetch_dialogs(cursor=cursor, max_dialogs=max_dialogs):
                if self._cancelled:
                    log.info(
                        "sync.runner.cancelled",
                        connector_id=self.connector_id,
                        correlation_id=self.correlation_id,
                    )
                    break

                total_chats += 1

                try:
                    dialog_messages = await self._process_dialog(
                        dialog_id=dialog.id,
                        cursor=None,  # Dialog-level cursor if needed
                        since=since_str,
                        max_messages=max_messages,
                    )
                    processed_chats += 1
                    processed_messages += len(dialog_messages)
                    total_messages += len(dialog_messages)

                    # Update progress periodically
                    if processed_chats % 10 == 0:
                        await self.client.update_status(
                            connector_id=self.connector_id,
                            correlation_id=self.correlation_id,
                            status=status,
                            progress=SyncProgress(
                                total_chats=total_chats,
                                processed_chats=processed_chats,
                                total_messages=total_messages,
                                processed_messages=processed_messages,
                            ),
                        )
                except Exception as exc:
                    log.exception(
                        "sync.runner.dialog.failed",
                        connector_id=self.connector_id,
                        correlation_id=self.correlation_id,
                        dialog_id=dialog.id,
                        error=str(exc),
                    )
                    # Continue with next dialog

            # Final progress update
            await self.client.update_status(
                connector_id=self.connector_id,
                correlation_id=self.correlation_id,
                status=SyncStatus.COMPLETED,
                progress=SyncProgress(
                    total_chats=total_chats,
                    processed_chats=processed_chats,
                    total_messages=total_messages,
                    processed_messages=processed_messages,
                ),
            )

            log.info(
                "sync.runner.completed",
                connector_id=self.connector_id,
                correlation_id=self.correlation_id,
                total_chats=total_chats,
                processed_messages=processed_messages,
            )

        except asyncio.CancelledError:
            log.info(
                "sync.runner.cancelled",
                connector_id=self.connector_id,
                correlation_id=self.correlation_id,
            )
            await self.client.update_status(
                connector_id=self.connector_id,
                correlation_id=self.correlation_id,
                status=SyncStatus.FAILED,
                error="Sync cancelled",
            )
            raise
        except Exception as exc:
            log.exception(
                "sync.runner.failed",
                connector_id=self.connector_id,
                correlation_id=self.correlation_id,
                error=str(exc),
            )
            await self.client.update_status(
                connector_id=self.connector_id,
                correlation_id=self.correlation_id,
                status=SyncStatus.FAILED,
                error=str(exc),
            )
            raise SyncRunnerError(f"Sync failed: {exc}") from exc
        finally:
            # Stop heartbeat task
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass

    async def _process_dialog(
        self,
        dialog_id: str,
        cursor: str | None,
        since: str | None,
        max_messages: int | None = None,
    ) -> list:
        """Process messages from a single dialog.

        Args:
            dialog_id: Dialog identifier
            cursor: Optional cursor for resume
            since: Optional date string for catchup
            max_messages: Optional maximum number of messages to fetch

        Returns:
            List of processed message IDs
        """
        batch: list = []
        processed_ids: list = []

        async for raw_message in self.provider.fetch_messages(
            dialog_id=dialog_id,
            cursor=cursor,
            since=since,
            max_messages=max_messages,
        ):
            if self._cancelled:
                break

            try:
                # Transform to SyncMessage (async for media processing)
                sync_message = await self.provider.transform_message(raw_message)
                batch.append(sync_message)
                processed_ids.append(sync_message.provider_message_id)

                # Send batch when full
                if len(batch) >= BATCH_SIZE:
                    await self._send_batch_with_retry(batch)
                    batch.clear()

                    # Rate limiting
                    await self.rate_limiter.acquire()
                    self.rate_limiter.on_success()

            except Exception as exc:
                log.exception(
                    "sync.runner.message.transform_failed",
                    connector_id=self.connector_id,
                    correlation_id=self.correlation_id,
                    dialog_id=dialog_id,
                    error=str(exc),
                )
                # Continue with next message

        # Send remaining batch
        if batch:
            await self._send_batch_with_retry(batch)

        return processed_ids

    async def _send_batch_with_retry(self, messages: Sequence) -> None:
        """Send batch with retry logic.

        Args:
            messages: List of SyncMessage objects

        Raises:
            BackendSyncClientError: If all retries fail
        """
        last_exc = None

        for attempt in range(MAX_RETRIES):
            try:
                await self.client.send_batch(
                    connector_id=self.connector_id,
                    correlation_id=self.correlation_id,
                    messages=messages,
                )
                return
            except BackendSyncClientError as exc:
                last_exc = exc

                # Check for rate limit (429)
                if exc.status_code == 429:
                    self.rate_limiter.on_rate_limit()
                    delay = RETRY_DELAY_BASE * (2**attempt)
                    log.warning(
                        "sync.runner.batch.rate_limit",
                        connector_id=self.connector_id,
                        correlation_id=self.correlation_id,
                        attempt=attempt + 1,
                        delay=delay,
                    )
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(delay)
                        continue

                # Check for server errors (5xx) - retry
                if exc.status_code and exc.status_code >= 500:
                    delay = RETRY_DELAY_BASE * (2**attempt)
                    log.warning(
                        "sync.runner.batch.server_error",
                        connector_id=self.connector_id,
                        correlation_id=self.correlation_id,
                        attempt=attempt + 1,
                        status_code=exc.status_code,
                        delay=delay,
                    )
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(delay)
                        continue

                # Other errors - don't retry
                raise

        # All retries exhausted
        raise last_exc

    async def _heartbeat_loop(self) -> None:
        """Background task that sends heartbeat signals periodically."""
        try:
            while not self._cancelled:
                await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
                if not self._cancelled:
                    await self.client.heartbeat(
                        connector_id=self.connector_id,
                        correlation_id=self.correlation_id,
                    )
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.warning(
                "sync.runner.heartbeat.error",
                connector_id=self.connector_id,
                correlation_id=self.correlation_id,
                error=str(exc),
            )

    def cancel(self) -> None:
        """Cancel sync process."""
        self._cancelled = True
        log.info(
            "sync.runner.cancel_requested",
            connector_id=self.connector_id,
            correlation_id=self.correlation_id,
        )
