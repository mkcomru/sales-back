from __future__ import annotations

import asyncio
import mimetypes
from collections.abc import Mapping

import structlog
from fastapi import HTTPException, status
from fastapi.responses import JSONResponse

from common.models.transport import AttachmentDescriptor, TransportDeliveryPayload
from common.transport.base_backend_client import TransportBackendClientError
from common.transport.base_delivery import BaseTransportDeliveryService
from wappi_module.config import Settings
from wappi_module.connectors.manager import ConnectorManager
from wappi_module.connectors.models import WappiConnectorConfig
from wappi_module.services.backend import WappiBackendClient
from wappi_module.services.wappi_api import WappiApiClient, WappiApiError

log = structlog.get_logger(__name__)


class TransportDeliveryError(RuntimeError):
    """Raised when wappi transport delivery fails after retries."""


class _IdempotencyStore:
    """In-memory tracker preventing duplicate correlation deliveries."""

    def __init__(self, ttl_seconds: float = 86_400.0) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def reserve(self, key: str) -> bool:
        """Store key if absent; return False when key still active."""

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
    """Handle deliveries from Sales Agent to Wappi API."""

    def __init__(self, settings: Settings, connectors: ConnectorManager, backend_client: WappiBackendClient) -> None:
        self._settings = settings
        self._connectors = connectors
        self._backend_client = backend_client
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
            log.warning(
                "transport.delivery.missing_connector_header",
                connector_id=payload.connector_id,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing connector header",
            )
        if connector_header.strip() != payload.connector_id:
            log.warning(
                "transport.delivery.connector_mismatch",
                connector_id=payload.connector_id,
                header_value=connector_header,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Connector header mismatch",
            )

        provided_key = normalized_headers.get(self._service_header)
        if provided_key is None:
            log.warning(
                "transport.delivery.missing_service_key",
                connector_id=payload.connector_id,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing service credentials",
            )
        if provided_key != self._service_key:
            log.warning(
                "transport.delivery.invalid_service_key",
                connector_id=payload.connector_id,
            )
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
                company_id=payload.company_id,
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
                company_id=payload.company_id,
                correlation_id=payload.correlation_id,
                error=str(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to deliver to Wappi",
            ) from exc

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "status": "accepted",
                "connector_id": payload.connector_id,
                "correlation_id": payload.correlation_id,
            },
        )

    async def _deliver_replies(self, connector: WappiConnectorConfig, payload: TransportDeliveryPayload) -> None:
        metadata = payload.metadata or {}
        extra = metadata.get("extra")
        if isinstance(extra, Mapping):
            extra_meta = dict(extra)
        else:
            extra_meta = {}

        chat_id = metadata.get("chat_id") or extra_meta.get("chat_id")
        if not chat_id:
            chat_id = payload.conversation_id

        recipient = str(chat_id)

        api_base_url = connector.metadata.get("api_base_url", "https://wappi.pro")
        wappi_client = WappiApiClient(api_base_url=api_base_url)

        attempts_limit = self._settings.max_delivery_attempts

        log.debug(
            "transport.delivery.preparing",
            connector_id=payload.connector_id,
            company_id=payload.company_id,
            correlation_id=payload.correlation_id,
            recipient=recipient,
            profile_id=connector.wappi_profile_id,
            api_base_url=api_base_url,
            replies_count=len(payload.replies),
        )

        for index, reply in enumerate(payload.replies):
            text = reply.strip()
            if not text:
                continue

            await self._send_with_retry(
                wappi_client=wappi_client,
                wappi_token=connector.wappi_token.get_secret_value(),
                profile_id=connector.wappi_profile_id,
                recipient=recipient,
                body=text,
                channel_type=connector.channel_type,
                attempts_limit=attempts_limit,
                delivery_index=index,
                payload=payload,
            )

        for attachment in payload.attachments or []:
            await self._deliver_attachment(
                wappi_client=wappi_client,
                wappi_token=connector.wappi_token.get_secret_value(),
                profile_id=connector.wappi_profile_id,
                recipient=recipient,
                channel_type=connector.channel_type,
                attachment=attachment,
                attempts_limit=attempts_limit,
                payload=payload,
            )

    async def _send_with_retry(
        self,
        *,
        wappi_client: WappiApiClient,
        wappi_token: str,
        profile_id: str,
        recipient: str,
        body: str,
        channel_type: str,
        attempts_limit: int,
        delivery_index: int,
        payload: TransportDeliveryPayload,
    ) -> None:
        attempt = 0
        while True:
            attempt += 1
            try:
                await wappi_client.send_message(
                    wappi_token=wappi_token,
                    profile_id=profile_id,
                    recipient=recipient,
                    body=body,
                    channel_type=channel_type,
                )
                log.info(
                    "transport.delivery.delivered",
                    connector_id=payload.connector_id,
                    company_id=payload.company_id,
                    correlation_id=payload.correlation_id,
                    delivery_index=delivery_index,
                    attempt=attempt,
                )
                return
            except WappiApiError as exc:
                if "429" in str(exc) or "rate" in str(exc).lower():
                    delay = min(5.0 * attempt, 30.0)
                    log.warning(
                        "transport.delivery.rate_limit",
                        connector_id=payload.connector_id,
                        attempt=attempt,
                        delay=delay,
                    )
                elif "400" in str(exc) or "bad request" in str(exc).lower():
                    log.error(
                        "transport.delivery.wappi_400_error",
                        connector_id=payload.connector_id,
                        company_id=payload.company_id,
                        correlation_id=payload.correlation_id,
                        profile_id=profile_id,
                        recipient=recipient,
                        error=str(exc),
                        attempt=attempt,
                    )
                    raise TransportDeliveryError(f"Wappi API rejected payload: {exc}") from exc
                else:
                    delay = min(5.0 * attempt, 30.0)
                    log.warning(
                        "transport.delivery.wappi_error",
                        connector_id=payload.connector_id,
                        company_id=payload.company_id,
                        profile_id=profile_id,
                        recipient=recipient,
                        attempt=attempt,
                        error=str(exc),
                    )
            except Exception as exc:
                raise TransportDeliveryError(f"Unexpected Wappi error: {exc}") from exc

            if attempt >= attempts_limit:
                raise TransportDeliveryError("Exceeded delivery retry limit")

            await asyncio.sleep(delay)

    async def _deliver_attachment(
        self,
        *,
        wappi_client: WappiApiClient,
        wappi_token: str,
        profile_id: str,
        recipient: str,
        channel_type: str,
        attachment: AttachmentDescriptor,
        attempts_limit: int,
        payload: TransportDeliveryPayload,
    ) -> None:
        try:
            file_bytes = await self._backend_client.download_artifact(attachment.artifact_id)
        except TransportBackendClientError as exc:
            raise TransportDeliveryError(f"Failed to download artifact {attachment.artifact_id}: {exc}") from exc

        attempt = 0
        delay = 0.0
        while True:
            attempt += 1
            try:
                await self._send_attachment(
                    wappi_client=wappi_client,
                    wappi_token=wappi_token,
                    profile_id=profile_id,
                    recipient=recipient,
                    channel_type=channel_type,
                    attachment=attachment,
                    file_bytes=file_bytes,
                )
                log.info(
                    "transport.delivery.attachment_delivered",
                    connector_id=payload.connector_id,
                    artifact_id=attachment.artifact_id,
                    attachment_type=attachment.type,
                    attempt=attempt,
                )
                return
            except WappiApiError as exc:
                if "429" in str(exc) or "rate" in str(exc).lower():
                    delay = min(5.0 * attempt, 30.0)
                    log.warning(
                        "transport.delivery.attachment_rate_limit",
                        connector_id=payload.connector_id,
                        artifact_id=attachment.artifact_id,
                        attempt=attempt,
                        delay=delay,
                    )
                elif "400" in str(exc) or "bad request" in str(exc).lower():
                    log.error(
                        "transport.delivery.attachment_wappi_400_error",
                        connector_id=payload.connector_id,
                        artifact_id=attachment.artifact_id,
                        attachment_type=attachment.type,
                        attempt=attempt,
                        error=str(exc),
                    )
                    raise TransportDeliveryError(f"Wappi API rejected attachment: {exc}") from exc
                else:
                    delay = min(5.0 * attempt, 30.0)
                    log.warning(
                        "transport.delivery.attachment_wappi_error",
                        connector_id=payload.connector_id,
                        artifact_id=attachment.artifact_id,
                        attachment_type=attachment.type,
                        attempt=attempt,
                        error=str(exc),
                    )
            except Exception as exc:
                raise TransportDeliveryError(f"Unexpected Wappi error sending attachment: {exc}") from exc

            if attempt >= attempts_limit:
                raise TransportDeliveryError("Exceeded attachment delivery retry limit")

            await asyncio.sleep(delay)

    async def _send_attachment(
        self,
        *,
        wappi_client: WappiApiClient,
        wappi_token: str,
        profile_id: str,
        recipient: str,
        channel_type: str,
        attachment: AttachmentDescriptor,
        file_bytes: bytes,
    ) -> None:
        match attachment.type:
            case "image":
                await wappi_client.send_image(
                    wappi_token=wappi_token,
                    profile_id=profile_id,
                    recipient=recipient,
                    file_bytes=file_bytes,
                    channel_type=channel_type,
                    caption=attachment.caption,
                )
            case "audio":
                await wappi_client.send_audio(
                    wappi_token=wappi_token,
                    profile_id=profile_id,
                    recipient=recipient,
                    file_bytes=file_bytes,
                    channel_type=channel_type,
                    caption=attachment.caption,
                )
            case "document":
                ext = mimetypes.guess_extension(attachment.mime_type, strict=False) or ""
                filename = f"document{ext}"
                await wappi_client.send_document(
                    wappi_token=wappi_token,
                    profile_id=profile_id,
                    recipient=recipient,
                    file_bytes=file_bytes,
                    channel_type=channel_type,
                    filename=filename,
                    caption=attachment.caption,
                )
            case "video":
                ext = mimetypes.guess_extension(attachment.mime_type, strict=False) or ""
                filename = f"video{ext}"
                await wappi_client.send_video(
                    wappi_token=wappi_token,
                    profile_id=profile_id,
                    recipient=recipient,
                    file_bytes=file_bytes,
                    channel_type=channel_type,
                    filename=filename,
                    caption=attachment.caption,
                )
            case _:
                raise TransportDeliveryError(f"Unsupported attachment type for Wappi: {attachment.type}")
