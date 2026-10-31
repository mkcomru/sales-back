from __future__ import annotations

from typing import Any

import httpx
import structlog

from common.transport.base_backend_client import BaseTransportBackendClient, TransportBackendClientError
from telegram_module.bots.models import BotConfig
from telegram_module.config import Settings

__all__ = ["TransportBackendClient", "TransportBackendClientError"]

log = structlog.get_logger(__name__)


class TransportBackendClient(BaseTransportBackendClient[BotConfig]):
    """Loads telegram bot configuration from backend API using unified connectors endpoint."""

    def __init__(self, settings: Settings) -> None:
        backend_url = (settings.backend.url or "").strip()
        if not backend_url:
            raise ValueError("Backend URL must be configured for telegram-module")
        self._base_url = backend_url.rstrip("/")
        self._settings = settings
        self._timeout = settings.request_timeout_s
        self._auth_header = settings.service.resolved_header()
        api_key = settings.service.api_key
        if api_key is None:
            raise ValueError("SERVICE__API_KEY must be configured for telegram-module")
        self._api_key = api_key
        self._artifact_upload_max_retries = settings.artifact_upload.max_retries
        self._artifact_upload_retry_delay_s = settings.artifact_upload.retry_delay_s

    async def fetch_connectors(self) -> list[BotConfig]:
        """Fetch active telegram connector configurations from backend."""
        url = f"{self._base_url}/transport/connectors"
        log.debug("backend.transport.fetch_connectors", url=url)

        headers: dict[str, str] = {self._auth_header: self._api_key.get_secret_value()}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    url,
                    headers=headers,
                    params={"type": "telegram", "enabled": "true"},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TransportBackendClientError(f"Failed to load telegram connectors: {exc}") from exc

        payload = response.json()
        raw_connectors: list[dict[str, Any]] = payload.get("connectors", [])

        bots: list[BotConfig] = []
        for connector in raw_connectors:
            try:
                bot_config = self._connector_to_bot_config(connector)
                if bot_config:
                    bots.append(bot_config)
            except Exception as exc:
                log.warning(
                    "backend.transport.connector_config_invalid",
                    error=str(exc),
                    connector_id=connector.get("connector_id"),
                )

        return bots

    def _connector_to_bot_config(self, connector: dict[str, Any]) -> BotConfig | None:
        """Transform unified Connector response to BotConfig."""
        if connector.get("type") != "telegram":
            return None

        config = connector.get("config", {})
        bot_token = config.get("bot_token")
        if not bot_token:
            log.warning(
                "backend.transport.missing_bot_token",
                connector_id=connector.get("connector_id"),
            )
            return None

        return BotConfig(
            connector_id=connector["connector_id"],
            company_id=str(connector["company_id"]),
            bot_token=bot_token,
            mode=config.get("mode", "auto"),
            channel_type=connector.get("channel_type", "telegram"),
            webhook_secret=config.get("webhook_secret"),
            webhook_path=config.get("webhook_path"),
            metadata=config.get("metadata", {}),
        )
