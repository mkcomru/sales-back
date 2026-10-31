from __future__ import annotations

from typing import Any

import httpx
import structlog

from common.transport.base_backend_client import BaseTransportBackendClient, TransportBackendClientError
from wazzup_module.config import Settings
from wazzup_module.connectors.models import WazzupConnectorConfig

log = structlog.get_logger(__name__)

WazzupBackendClientError = TransportBackendClientError

__all__ = ["WazzupBackendClient", "WazzupBackendClientError"]


class WazzupBackendClient(BaseTransportBackendClient[WazzupConnectorConfig]):
    """Loads Wazzup connector configuration from backend API using unified connectors endpoint."""

    def __init__(self, settings: Settings) -> None:
        backend_url = (settings.backend.url or "").strip()
        if not backend_url:
            raise ValueError("Backend URL must be configured for wazzup-module")
        self._base_url = backend_url.rstrip("/")
        self._settings = settings
        self._timeout = settings.request_timeout_s
        self._auth_header = settings.service.resolved_header()
        api_key = settings.service.api_key
        if api_key is None:
            raise ValueError("SERVICE__API_KEY must be configured for wazzup-module")
        self._api_key = api_key
        self._artifact_upload_max_retries = settings.artifact_upload.max_retries
        self._artifact_upload_retry_delay_s = settings.artifact_upload.retry_delay_s

    async def fetch_connectors(self) -> list[WazzupConnectorConfig]:
        url = f"{self._base_url}/transport/connectors"
        log.debug("backend.wazzup.fetch_connectors", url=url)

        headers: dict[str, str] = {self._auth_header: self._api_key.get_secret_value()}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    url,
                    headers=headers,
                    params={"type": "wazzup", "enabled": "true"},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TransportBackendClientError(f"Failed to load Wazzup connectors: {exc}") from exc

        payload = response.json()
        raw_connectors: list[dict[str, Any]] = payload.get("connectors", [])

        connectors: list[WazzupConnectorConfig] = []
        for connector in raw_connectors:
            try:
                config = self._connector_to_wazzup_config(connector)
                if config:
                    connectors.append(config)
            except Exception as exc:
                log.warning(
                    "backend.wazzup.connector_config_invalid",
                    error=str(exc),
                    connector_id=connector.get("connector_id"),
                )

        log.debug("backend.wazzup.fetch_connectors.success", count=len(connectors))
        return connectors

    def _connector_to_wazzup_config(self, connector: dict[str, Any]) -> WazzupConnectorConfig | None:
        if connector.get("type") != "wazzup":
            return None

        config = connector.get("config", {})
        wazzup_api_key = config.get("wazzup_api_key")
        channel_id = config.get("channel_id")

        if not wazzup_api_key:
            log.warning(
                "backend.wazzup.missing_api_key",
                connector_id=connector.get("connector_id"),
            )
            return None

        if not channel_id:
            log.warning(
                "backend.wazzup.missing_channel_id",
                connector_id=connector.get("connector_id"),
            )
            return None

        return WazzupConnectorConfig(
            connector_id=connector["connector_id"],
            company_id=str(connector["company_id"]),
            wazzup_api_key=wazzup_api_key,
            channel_id=channel_id,
            channel_type=connector.get("channel_type", "instagram"),
            metadata=config.get("metadata", {}),
        )
