from __future__ import annotations

import asyncio
from collections.abc import Mapping

import structlog
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse

from common.models.transport import TransportDeliveryPayload
from common.transport.base_delivery import BaseTransportDeliveryService
from wazzup_module.config import Settings
from wazzup_module.connectors.manager import ConnectorManager
from wazzup_module.connectors.models import WazzupConnectorConfig
from wazzup_module.services.wazzup_api import WazzupApiClient, WazzupApiError

log = structlog.get_logger(__name__)


class TransportDeliveryError(RuntimeError):
    """Raised when wazzup transport delivery fails after retries."""


class _IdempotencyStore:
    """In-memory tracker preventing duplicate correlation deliveries."""

    def __init__(self, ttl_seconds: float = 86_400.0) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def reserve(self, key: str) -> bool:
        async with self._lock:
            now = asyncio.get_running_loop().time()
            self._purge(now)
            expires_at = self._entries.get(key)
            if expires_at is not None and expires_at > now:
                return False
            self._entries[key] = now + self._ttl
            return True

    def _purge(self, now: float) -> None:
        expired = [key for key, expires in self._entries.items() if expires <= now]
        for key in expired:
            self._entries.pop(key, None)


class TransportDeliveryService(BaseTransportDeliveryService):
    """Handle deliveries from Backend to Wazzup API."""

    def __init__(self, settings: Settings, connectors: ConnectorManager) -> None:
        self._settings = settings
        self._connectors = connectors
        self._idempotency = _IdempotencyStore()
        header = settings.service.resolved_header()
        self._service_header = header.lower()
        api_key = settings.service.api_key
        if api_key is None:
            raise RuntimeError("SERVICE__API_KEY must be configured for transport")
        self._service_key = api_key.get_secret_value()
        self._connector_header = "x-connector-id"

    async def handle(
        self,
        *,
        payload: TransportDeliveryPayload,
        headers: Mapping[str, str],
    ) -> JSONResponse:
        connector = self._connectors.get(payload.connector_id)
        if connector is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unknown connector_id '{payload.connector_id}'",
            )

        normalized_headers = {key.lower(): value for key, value in headers.items()}
        connector_header = normalized_headers.get(self._connector_header)
        if connector_header is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing connector header",
            )
        if connector_header.strip() != payload.connector_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Connector header mismatch",
            )

        provided_key = normalized_headers.get(self._service_header)
        if provided_key is None or provided_key != self._service_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid service credentials",
            )

        correlation_id = payload.correlation_id.strip()
        if not correlation_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Correlation id must be provided",
            )

        is_new = await self._idempotency.reserve(f"{payload.connector_id}:{correlation_id}")
        if not is_new:
            log.info(
                "transport.delivery.duplicate",
                connector_id=payload.connector_id,
                correlation_id=payload.correlation_id,
            )
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "status": "duplicate",
                    "connector_id": payload.connector_id,
                    "correlation_id": payload.correlation_id,
                },
            )

        try:
            await self._deliver_replies(connector, payload)
        except TransportDeliveryError as exc:
            log.error(
                "transport.delivery.failed",
                connector_id=payload.connector_id,
                correlation_id=payload.correlation_id,
                error=str(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to deliver to Wazzup",
            ) from exc

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "status": "accepted",
                "connector_id": payload.connector_id,
                "correlation_id": payload.correlation_id,
            },
        )

    async def _deliver_replies(self, connector: WazzupConnectorConfig, payload: TransportDeliveryPayload) -> None:
        recipient = self.resolve_recipient(payload)

        api_base_url = connector.metadata.get("api_base_url", "https://api.wazzup24.com/v3")
        wazzup_client = WazzupApiClient(api_base_url=api_base_url)

        attempts_limit = self._settings.max_delivery_attempts

        for index, reply in enumerate(payload.replies):
            text = reply.strip()
            if not text:
                continue

            await self._send_with_retry(
                wazzup_client=wazzup_client,
                api_key=connector.wazzup_api_key.get_secret_value(),
                channel_id=connector.channel_id,
                chat_id=recipient,
                chat_type=connector.channel_type,
                text=text,
                crm_message_id=f"{payload.correlation_id}:{index}",
                attempts_limit=attempts_limit,
                delivery_index=index,
                payload=payload,
            )

    async def _send_with_retry(
        self,
        *,
        wazzup_client: WazzupApiClient,
        api_key: str,
        channel_id: str,
        chat_id: str,
        chat_type: str,
        text: str,
        crm_message_id: str,
        attempts_limit: int,
        delivery_index: int,
        payload: TransportDeliveryPayload,
    ) -> None:
        attempt = 0
        delay = 0.0
        while True:
            attempt += 1
            try:
                await wazzup_client.send_message(
                    api_key=api_key,
                    channel_id=channel_id,
                    chat_id=chat_id,
                    chat_type=chat_type,
                    text=text,
                    crm_message_id=crm_message_id,
                )
                log.info(
                    "transport.delivery.delivered",
                    connector_id=payload.connector_id,
                    correlation_id=payload.correlation_id,
                    delivery_index=delivery_index,
                    attempt=attempt,
                )
                return
            except WazzupApiError as exc:
                if "429" in str(exc) or "rate" in str(exc).lower():
                    delay = min(5.0 * attempt, 30.0)
                    log.warning(
                        "transport.delivery.rate_limit",
                        connector_id=payload.connector_id,
                        attempt=attempt,
                        delay=delay,
                    )
                elif "400" in str(exc) or "bad request" in str(exc).lower():
                    raise TransportDeliveryError(f"Wazzup API rejected payload: {exc}") from exc
                else:
                    delay = min(5.0 * attempt, 30.0)
                    log.warning(
                        "transport.delivery.wazzup_error",
                        connector_id=payload.connector_id,
                        attempt=attempt,
                        error=str(exc),
                    )
            except Exception as exc:
                raise TransportDeliveryError(f"Unexpected Wazzup error: {exc}") from exc

            if attempt >= attempts_limit:
                raise TransportDeliveryError("Exceeded delivery retry limit")

            await asyncio.sleep(delay)
