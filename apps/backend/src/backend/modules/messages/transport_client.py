"""Transport client for routing outbound messages to transport modules."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import structlog

from common.connectors import ConnectorCapability
from common.transport.registry import CONNECTOR_TYPE_CATALOG, resolve_catalog_key

from src.backend.modules.core.settings import Settings

if TYPE_CHECKING:
    from src.backend.modules.transport.models import Connector

log = structlog.get_logger(__name__)


class TransportClientError(Exception):
    """Raised when transport delivery fails."""


class TransportClient:
    """HTTP client for routing deliveries to transport modules."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._service_header = settings.service.resolved_header()
        self._service_key = settings.service.api_key
        self._clients: dict[str, httpx.AsyncClient] = {}

    def _resolve_endpoint(self, connector_type: str, connector_config: dict[str, Any] | None = None) -> str:
        """Resolve transport endpoint URL based on connector type.

        Managed types (telegram, wappi) use static settings.
        Custom connectors read ``transport_endpoint`` from their DB config.
        """
        match connector_type:
            case "telegram":
                if not self._settings.transport.telegram.url:
                    raise TransportClientError(f"Transport endpoint not configured for type '{connector_type}'")
                return str(self._settings.transport.telegram.url).rstrip("/")
            case "wappi":
                if not self._settings.transport.wappi.url:
                    raise TransportClientError(f"Transport endpoint not configured for type '{connector_type}'")
                return str(self._settings.transport.wappi.url).rstrip("/")
            case "wazzup":
                if not self._settings.transport.wazzup.url:
                    raise TransportClientError(f"Transport endpoint not configured for type '{connector_type}'")
                return str(self._settings.transport.wazzup.url).rstrip("/")
            case "custom":
                url = (connector_config or {}).get("transport_endpoint")
                if not url:
                    raise TransportClientError("Custom connector missing 'transport_endpoint' in config")
                return str(url).rstrip("/")
            case _:
                raise TransportClientError(f"Unknown connector type '{connector_type}'")

    def _get_client(self, endpoint: str) -> httpx.AsyncClient:
        """Get or create HTTP client for endpoint with connection pooling."""
        if endpoint not in self._clients:
            headers: dict[str, str] = {
                "Content-Type": "application/json",
            }
            if self._service_key:
                headers[self._service_header] = self._service_key.get_secret_value()
            self._clients[endpoint] = httpx.AsyncClient(
                base_url=endpoint,
                headers=headers,
                timeout=httpx.Timeout(30.0, connect=5.0),
            )
        return self._clients[endpoint]

    async def deliver(self, *, connector: Connector, payload: dict[str, Any]) -> None:
        """Deliver message to transport module."""
        connector_id = connector.connector_id
        connector_type = connector.type.value
        channel_type = connector.channel_type

        catalog_key = resolve_catalog_key(connector_type, channel_type)
        catalog_entry = CONNECTOR_TYPE_CATALOG.get(catalog_key)
        if (
            catalog_entry
            and payload.get("attachments")
            and ConnectorCapability.OUTBOUND_MEDIA not in catalog_entry.supported_capabilities
        ):
            log.warning(
                "egress.delivery.attachments_unsupported",
                connector_id=connector_id,
                connector_type=connector_type,
                attachment_count=len(payload["attachments"]),
            )

        endpoint = self._resolve_endpoint(connector_type, connector.config)
        client = self._get_client(endpoint)

        headers: dict[str, str] = {
            "X-Connector-Id": connector_id,
        }

        try:
            response = await client.post("/transport/delivery", json=payload, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            log.error(
                "egress.delivery.failed",
                connector_id=connector_id,
                connector_type=connector_type,
                error=str(exc),
            )
            raise TransportClientError(f"Transport delivery failed for connector '{connector_id}'") from exc

        log.info(
            "egress.routed",
            connector_id=connector_id,
            connector_type=connector_type,
            conversation_id=payload.get("conversation_id"),
        )

    async def close(self) -> None:
        """Close all HTTP clients."""
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()
