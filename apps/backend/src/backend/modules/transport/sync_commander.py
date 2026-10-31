"""Commander for sending sync commands to connector modules."""

from datetime import datetime
from uuid import uuid4

import httpx
import structlog

from common.contracts.sync import SyncCancelCommand, SyncStartCommand

from src.backend.modules.core.settings import Settings, get_settings
from src.backend.modules.transport.models import Connector

log = structlog.get_logger(__name__)

SYNC_COMMAND_TIMEOUT = 10.0


class SyncCommanderError(Exception):
    """Raised when sync command fails."""


class SyncCommander:
    """Sends sync commands to connector modules via HTTP."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._service_header = self._settings.service.resolved_header()
        self._service_key = self._settings.service.api_key

    def _get_connector_endpoint(self, connector: Connector) -> str:
        """Get connector module endpoint URL from config.

        Args:
            connector: Connector instance

        Returns:
            Base URL of connector module

        Raises:
            SyncCommanderError: If transport_endpoint not configured
        """
        config = connector.config or {}
        transport_endpoint = config.get("transport_endpoint")
        if not transport_endpoint:
            raise SyncCommanderError(f"Connector {connector.connector_id} does not have transport_endpoint configured")
        return str(transport_endpoint).rstrip("/")

    def _get_headers(self, connector_id: str) -> dict[str, str]:
        """Build HTTP headers for connector request.

        Args:
            connector_id: Connector identifier

        Returns:
            Headers dict with service key and connector ID
        """
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "X-Connector-Id": connector_id,
        }
        if self._service_key:
            headers[self._service_header] = self._service_key.get_secret_value()
        return headers

    async def send_start(
        self,
        connector: Connector,
        sync_type: str,
        correlation_id: str,
        cursor: str | None = None,
        since: datetime | None = None,
    ) -> None:
        """Send start sync command to connector module.

        Args:
            connector: Connector instance
            sync_type: Type of sync (initial, backfill, catchup)
            correlation_id: Correlation ID for tracking
            cursor: Optional cursor for resume
            since: Optional start date for catchup

        Raises:
            SyncCommanderError: If command fails
        """
        endpoint = self._get_connector_endpoint(connector)
        url = f"{endpoint}/internal/sync/start"

        command = SyncStartCommand(
            connector_id=connector.connector_id,
            correlation_id=correlation_id,
            sync_type=sync_type,
            cursor=cursor,
            since=since,
        )

        headers = self._get_headers(connector.connector_id)

        try:
            async with httpx.AsyncClient(timeout=SYNC_COMMAND_TIMEOUT) as client:
                response = await client.post(url, json=command.model_dump(mode="json"), headers=headers)
                response.raise_for_status()

            log.info(
                "sync.command.start.sent",
                connector_id=connector.connector_id,
                correlation_id=correlation_id,
                sync_type=sync_type,
                endpoint=endpoint,
            )
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            error_text = exc.response.text[:500] if exc.response.text else None
            log.error(
                "sync.command.start.failed",
                connector_id=connector.connector_id,
                correlation_id=correlation_id,
                status_code=status_code,
                error=error_text,
            )
            raise SyncCommanderError(f"Failed to send start command: HTTP {status_code} - {error_text}") from exc
        except httpx.HTTPError as exc:
            log.error(
                "sync.command.start.network_error",
                connector_id=connector.connector_id,
                correlation_id=correlation_id,
                error=str(exc),
            )
            raise SyncCommanderError(f"Network error sending start command: {exc}") from exc

    async def send_cancel(self, connector: Connector) -> None:
        """Send cancel sync command to connector module.

        Args:
            connector: Connector instance

        Raises:
            SyncCommanderError: If command fails
        """
        endpoint = self._get_connector_endpoint(connector)
        url = f"{endpoint}/internal/sync/cancel"

        command = SyncCancelCommand(connector_id=connector.connector_id)

        headers = self._get_headers(connector.connector_id)

        try:
            async with httpx.AsyncClient(timeout=SYNC_COMMAND_TIMEOUT) as client:
                response = await client.post(url, json=command.model_dump(mode="json"), headers=headers)
                response.raise_for_status()

            log.info(
                "sync.command.cancel.sent",
                connector_id=connector.connector_id,
                endpoint=endpoint,
            )
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            error_text = exc.response.text[:500] if exc.response.text else None
            log.error(
                "sync.command.cancel.failed",
                connector_id=connector.connector_id,
                status_code=status_code,
                error=error_text,
            )
            raise SyncCommanderError(f"Failed to send cancel command: HTTP {status_code} - {error_text}") from exc
        except httpx.HTTPError as exc:
            log.error(
                "sync.command.cancel.network_error",
                connector_id=connector.connector_id,
                error=str(exc),
            )
            raise SyncCommanderError(f"Network error sending cancel command: {exc}") from exc

    @staticmethod
    def generate_correlation_id() -> str:
        """Generate unique correlation ID for sync job.

        Returns:
            Correlation ID string
        """
        return f"sync_{uuid4().hex[:16]}"
