from __future__ import annotations

from typing import Any

import httpx
import structlog

from common.transport.base_backend_client import BaseTransportBackendClient, TransportBackendClientError
from wappi_module.config import Settings
from wappi_module.connectors.models import WappiConnectorConfig

log = structlog.get_logger(__name__)

WappiBackendClientError = TransportBackendClientError

__all__ = ["WappiBackendClient", "WappiBackendClientError"]


class WappiBackendClient(BaseTransportBackendClient[WappiConnectorConfig]):
    """Loads Wappi connector configuration from backend API using unified connectors endpoint."""

    def __init__(self, settings: Settings) -> None:
        backend_url = (settings.backend.url or "").strip()
        if not backend_url:
            raise ValueError("Backend URL must be configured for wappi-module")
        self._base_url = backend_url.rstrip("/")
        self._settings = settings
        self._timeout = settings.request_timeout_s
        self._auth_header = settings.service.resolved_header()
        api_key = settings.service.api_key
        if api_key is None:
            raise ValueError("SERVICE__API_KEY must be configured for wappi-module")
        self._api_key = api_key
        self._artifact_upload_max_retries = settings.artifact_upload.max_retries
        self._artifact_upload_retry_delay_s = settings.artifact_upload.retry_delay_s

    async def fetch_connectors(self) -> list[WappiConnectorConfig]:
        """Fetch active Wappi connectors configuration from backend."""
        url = f"{self._base_url}/transport/connectors"
        log.debug("backend.wappi.fetch_connectors", url=url)

        headers: dict[str, str] = {self._auth_header: self._api_key.get_secret_value()}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    url,
                    headers=headers,
                    params={"type": "wappi", "enabled": "true"},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TransportBackendClientError(f"Failed to load Wappi connectors: {exc}") from exc

        payload = response.json()
        raw_connectors: list[dict[str, Any]] = payload.get("connectors", [])

        connectors: list[WappiConnectorConfig] = []
        for connector in raw_connectors:
            try:
                config = self._connector_to_wappi_config(connector)
                if config:
                    connectors.append(config)
            except Exception as exc:
                log.warning(
                    "backend.wappi.connector_config_invalid",
                    error=str(exc),
                    connector_id=connector.get("connector_id"),
                )

        log.debug("backend.wappi.fetch_connectors.success", count=len(connectors))
        return connectors

    def _connector_to_wappi_config(self, connector: dict[str, Any]) -> WappiConnectorConfig | None:
        """Transform unified Connector response to WappiConnectorConfig."""
        if connector.get("type") != "wappi":
            return None

        config = connector.get("config", {})
        wappi_token = config.get("wappi_token")
        wappi_profile_id = config.get("wappi_profile_id")

        if not wappi_token:
            log.warning(
                "backend.wappi.missing_token",
                connector_id=connector.get("connector_id"),
            )
            return None

        if not wappi_profile_id:
            log.warning(
                "backend.wappi.missing_profile_id",
                connector_id=connector.get("connector_id"),
            )
            return None

        return WappiConnectorConfig(
            connector_id=connector["connector_id"],
            company_id=str(connector["company_id"]),
            wappi_token=wappi_token,
            wappi_profile_id=wappi_profile_id,
            channel_type=connector.get("channel_type", "telegram"),
            metadata=config.get("metadata", {}),
        )

    async def get_thread_by_conversation(
        self,
        connector_id: str,
        conversation_id: str,
    ) -> tuple[str, bool] | None:
        """Get thread by conversation ID.

        Returns:
            Tuple of (thread_id, history_synced) if thread exists, None otherwise
        """
        url = f"{self._base_url}/internal/chat/threads/by-conversation"
        headers = {self._auth_header: self._api_key.get_secret_value()}
        params = {
            "connector_id": connector_id,
            "conversation_id": conversation_id,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, headers=headers, params=params)
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                data = response.json()
                thread_id = data.get("thread_id")
                history_synced = data.get("history_synced", False)
                if thread_id:
                    return (thread_id, history_synced)
                return None
        except Exception as e:
            log.warning(
                "backend.get_thread_by_conversation.failed",
                connector_id=connector_id,
                conversation_id=conversation_id,
                error=str(e),
            )
            return None

    async def mark_thread_history_synced(self, thread_id: str) -> bool:
        """Mark thread history as fully synced.

        Returns:
            True if successful, False otherwise
        """
        url = f"{self._base_url}/internal/chat/threads/{thread_id}/history-synced"
        headers = {self._auth_header: self._api_key.get_secret_value()}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.patch(url, headers=headers)
                response.raise_for_status()
                return True
        except Exception as e:
            log.warning(
                "backend.mark_thread_history_synced.failed",
                thread_id=thread_id,
                error=str(e),
            )
            return False
