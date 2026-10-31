"""Sales Agent inbound client for connector modules."""

from __future__ import annotations

import httpx
import structlog
from pydantic import AnyHttpUrl, SecretStr

from common.models import AudioData, InboundEnvelope

log = structlog.get_logger(__name__)


class SalesAgentInboundError(Exception):
    """Raised when Sales Agent inbound request fails."""

    def __init__(self, status_code: int, error: str, detail: str | None = None):
        self.status_code = status_code
        self.error = error
        self.detail = detail
        super().__init__(f"Sales Agent error: {error} (status={status_code})")


class SalesAgentInboundClient:
    """Client for sending inbound messages to Sales Agent unified endpoint.

    Supports managed connector auth (service key + connector ID).
    """

    def __init__(
        self,
        *,
        base_url: AnyHttpUrl | str,
        service_key: SecretStr,
        service_header: str = "X-Service-Key",
        timeout: float = 10.0,
    ) -> None:
        self._base_url = str(base_url).rstrip("/")
        self._service_key = service_key
        self._service_header = service_header
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout, connect=5.0),
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def send_inbound(
        self,
        *,
        connector_id: str,
        envelope: InboundEnvelope,
    ) -> None:
        """Send normalized inbound message to Sales Agent.

        Args:
            connector_id: Connector identifier for X-Connector-Id header
            envelope: Normalized message envelope

        Raises:
            SalesAgentInboundError: If request fails or returns error status
        """
        client = await self._get_client()

        headers = {
            self._service_header: self._service_key.get_secret_value(),
            "X-Connector-Id": connector_id,
            "Content-Type": "application/json",
        }

        try:
            response = await client.post(
                "/api/v1/messages/inbound",
                headers=headers,
                json=envelope.model_dump(mode="json"),
            )
        except httpx.HTTPError as exc:
            log.warning(
                "sales_agent.inbound.network_error",
                connector_id=connector_id,
                error=str(exc),
            )
            raise SalesAgentInboundError(
                status_code=503,
                error="network_error",
                detail=str(exc),
            ) from exc

        if response.status_code == 202:
            log.debug(
                "sales_agent.inbound.accepted",
                connector_id=connector_id,
                conversation_id=envelope.conversation_id,
            )
            return

        try:
            data = response.json()
            error = data.get("error", "unknown_error")
            detail = data.get("detail")
        except Exception:
            error = "unknown_error"
            detail = response.text

        log.warning(
            "sales_agent.inbound.error",
            connector_id=connector_id,
            status=response.status_code,
            error=error,
        )

        raise SalesAgentInboundError(
            status_code=response.status_code,
            error=error,
            detail=str(detail) if detail else None,
        )

    async def send_message(
        self,
        *,
        connector_id: str,
        conversation_id: str,
        user_id: str,
        text: str | None = None,
        ts: float,
        audio_bytes_base64: str | None = None,
        audio_mime: str = "audio/ogg",
    ) -> None:
        """Convenience method to send a message with separate parameters.

        Args:
            connector_id: Connector identifier
            conversation_id: Provider conversation ID (chat ID)
            user_id: Message sender ID
            text: Message text (optional if audio provided)
            ts: Unix timestamp
            audio_bytes_base64: Base64-encoded audio bytes (optional)
            audio_mime: Audio MIME type (default: audio/ogg)
        """
        audio: AudioData | None = None
        if audio_bytes_base64:
            audio = AudioData(bytes_base64=audio_bytes_base64, mime=audio_mime)

        envelope = InboundEnvelope(
            conversation_id=conversation_id,
            user_id=user_id,
            text=text,
            ts=ts,
            audio=audio,
        )

        await self.send_inbound(connector_id=connector_id, envelope=envelope)
