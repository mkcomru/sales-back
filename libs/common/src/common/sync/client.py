"""HTTP client for sending sync data to backend."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import httpx
import structlog

from common.contracts.sync import (
    SyncBatchRequest,
    SyncHeartbeatRequest,
    SyncMessage,
    SyncProgress,
    SyncStatus,
    SyncStatusUpdate,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

log = structlog.get_logger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 30.0


class BackendSyncClientError(Exception):
    """Raised when backend sync request fails."""

    def __init__(self, status_code: int | None, error: str, detail: str | None = None):
        self.status_code = status_code
        self.error = error
        self.detail = detail
        super().__init__(f"Backend sync error: {error} (status={status_code})")


class BackendSyncClient:
    """HTTP client for sending sync batches and status updates to backend."""

    def __init__(
        self,
        *,
        base_url: str,
        service_key: str,
        service_header: str = "X-Service-Key",
        timeout: float = 30.0,
    ):
        """Initialize backend sync client.

        Args:
            base_url: Backend base URL (with or without /api/v1 prefix)
            service_key: Service API key for authentication
            service_header: HTTP header name for service key
            timeout: Request timeout in seconds
        """
        url = str(base_url).rstrip("/")
        # AICODE-NOTE: Ensure base_url contains /api/v1 prefix for consistency
        if not url.endswith("/api/v1"):
            url = f"{url}/api/v1"
        self._base_url = url
        self._service_key = service_key
        self._service_header = service_header
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            headers = {
                "Content-Type": "application/json",
                self._service_header: self._service_key,
            }
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=httpx.Timeout(self._timeout, connect=5.0),
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def send_batch(
        self,
        *,
        connector_id: str,
        correlation_id: str,
        messages: Sequence[SyncMessage],
        batch_id: str | None = None,
    ) -> None:
        """Send batch of messages to backend.

        Args:
            connector_id: Connector identifier
            correlation_id: Correlation ID for tracking
            messages: List of messages to send
            batch_id: Optional batch ID (generated if not provided)

        Raises:
            BackendSyncClientError: If request fails
        """
        if not messages:
            return

        batch_id = batch_id or f"batch_{uuid4().hex[:16]}"

        request = SyncBatchRequest(
            connector_id=connector_id,
            batch_id=batch_id,
            correlation_id=correlation_id,
            messages=list(messages),
        )

        client = await self._get_client()

        try:
            response = await client.post(
                "/internal/sync/batch",
                json=request.model_dump(mode="json"),
            )

            if response.status_code == 409:
                # Duplicate batch - already processed, safe to ignore
                log.debug(
                    "sync.client.batch.duplicate",
                    connector_id=connector_id,
                    batch_id=batch_id,
                    correlation_id=correlation_id,
                )
                return

            response.raise_for_status()

            log.debug(
                "sync.client.batch.sent",
                connector_id=connector_id,
                batch_id=batch_id,
                correlation_id=correlation_id,
                message_count=len(messages),
            )
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            error_text = exc.response.text[:500] if exc.response.text else None
            log.error(
                "sync.client.batch.failed",
                connector_id=connector_id,
                batch_id=batch_id,
                correlation_id=correlation_id,
                status_code=status_code,
                error=error_text,
            )
            raise BackendSyncClientError(
                status_code=status_code,
                error="batch_send_failed",
                detail=error_text,
            ) from exc
        except httpx.HTTPError as exc:
            log.error(
                "sync.client.batch.network_error",
                connector_id=connector_id,
                batch_id=batch_id,
                correlation_id=correlation_id,
                error=str(exc),
            )
            raise BackendSyncClientError(
                status_code=None,
                error="network_error",
                detail=str(exc),
            ) from exc

    async def update_status(
        self,
        *,
        connector_id: str,
        correlation_id: str,
        status: SyncStatus,
        progress: SyncProgress | None = None,
        error: str | None = None,
        cursor: str | None = None,
    ) -> None:
        """Update sync status in backend.

        Args:
            connector_id: Connector identifier
            correlation_id: Correlation ID for tracking
            status: Current sync status
            progress: Optional progress details
            error: Optional error message
            cursor: Optional cursor for resume

        Raises:
            BackendSyncClientError: If request fails
        """
        request = SyncStatusUpdate(
            connector_id=connector_id,
            correlation_id=correlation_id,
            status=status,
            progress=progress,
            error=error,
            cursor=cursor,
        )

        client = await self._get_client()

        try:
            response = await client.post(
                "/internal/sync/status",
                json=request.model_dump(mode="json"),
            )
            response.raise_for_status()

            log.debug(
                "sync.client.status.updated",
                connector_id=connector_id,
                correlation_id=correlation_id,
                status=status.value,
            )
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            error_text = exc.response.text[:500] if exc.response.text else None
            log.error(
                "sync.client.status.failed",
                connector_id=connector_id,
                correlation_id=correlation_id,
                status_code=status_code,
                error=error_text,
            )
            raise BackendSyncClientError(
                status_code=status_code,
                error="status_update_failed",
                detail=error_text,
            ) from exc
        except httpx.HTTPError as exc:
            log.error(
                "sync.client.status.network_error",
                connector_id=connector_id,
                correlation_id=correlation_id,
                error=str(exc),
            )
            raise BackendSyncClientError(
                status_code=None,
                error="network_error",
                detail=str(exc),
            ) from exc

    async def get_cursor(self, connector_id: str) -> str | None:
        """Get last cursor for connector to resume sync.

        Args:
            connector_id: Connector identifier

        Returns:
            Cursor string or None if not found

        Raises:
            BackendSyncClientError: If request fails
        """
        client = await self._get_client()

        try:
            response = await client.get(f"/internal/sync/cursor/{connector_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            return data.get("cursor")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            status_code = exc.response.status_code
            log.error(
                "sync.client.cursor.failed",
                connector_id=connector_id,
                status_code=status_code,
            )
            raise BackendSyncClientError(
                status_code=status_code,
                error="cursor_fetch_failed",
                detail=exc.response.text[:500] if exc.response.text else None,
            ) from exc
        except httpx.HTTPError as exc:
            log.error(
                "sync.client.cursor.network_error",
                connector_id=connector_id,
                error=str(exc),
            )
            raise BackendSyncClientError(
                status_code=None,
                error="network_error",
                detail=str(exc),
            ) from exc

    async def heartbeat(
        self,
        *,
        connector_id: str,
        correlation_id: str,
    ) -> None:
        """Send heartbeat signal to backend.

        Args:
            connector_id: Connector identifier
            correlation_id: Correlation ID for tracking

        Raises:
            BackendSyncClientError: If request fails
        """
        request = SyncHeartbeatRequest(
            connector_id=connector_id,
            correlation_id=correlation_id,
        )

        client = await self._get_client()

        try:
            response = await client.post(
                "/internal/sync/heartbeat",
                json=request.model_dump(mode="json"),
            )
            response.raise_for_status()

            log.debug(
                "sync.client.heartbeat.sent",
                connector_id=connector_id,
                correlation_id=correlation_id,
            )
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            log.warning(
                "sync.client.heartbeat.failed",
                connector_id=connector_id,
                correlation_id=correlation_id,
                status_code=status_code,
            )
            # Don't raise for heartbeat failures - they're not critical
        except httpx.HTTPError as exc:
            log.warning(
                "sync.client.heartbeat.network_error",
                connector_id=connector_id,
                correlation_id=correlation_id,
                error=str(exc),
            )
            # Don't raise for heartbeat failures - they're not critical
