"""Backend client — write operations only.

All read operations (company spec, prompts, customer answers, history, langfuse)
are now assembled by Backend into the envelope's AgentContext.
"""

from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from pydantic import BaseModel, Field, SecretStr

from common import SalesAgentSettings
from common.models import OutboundDeliveryRequest

log = structlog.get_logger(__name__)


class ConnectorTransportRetryPayload(BaseModel):
    max_attempts: int | None = None
    backoff_schedule_ms: list[int] | None = None
    connect_timeout_s: float | None = None
    read_timeout_s: float | None = None
    total_timeout_s: float | None = None


class ConnectorTransportPayload(BaseModel):
    enabled: bool | None = None
    endpoint: str | None = None
    retries: ConnectorTransportRetryPayload | None = None


class ConnectorCallbackPayload(BaseModel):
    delivery_url: str | None = None
    poll_url: str | None = None
    proxy_url: str | None = None
    handoff_url: str | None = None


class ConnectorSecretPayload(BaseModel):
    token: SecretStr | None = None
    extra: dict[str, SecretStr] = Field(default_factory=dict)


class ConnectorDebouncePayload(BaseModel):
    window_seconds: int | None = None
    max_batch_messages: int | None = None
    storage_key_template: str | None = None


class BackendConnectorPayload(BaseModel):
    model_config = {"extra": "allow"}

    connector_id: str
    type: str | None = None
    channel_type: str | None = None
    channel_types: list[str] | None = None
    debounce: ConnectorDebouncePayload | None = None
    secrets: ConnectorSecretPayload | None = None
    callbacks: ConnectorCallbackPayload | None = None
    transport: ConnectorTransportPayload | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    enabled: bool | None = None
    debounce_window_seconds: int | None = None
    debounce_storage_key_template: str | None = None


class BackendConnectorListResponse(BaseModel):
    connectors: list[BackendConnectorPayload] = Field(default_factory=list)
    ttl_seconds: int | None = None


class BackendClient:
    def __init__(self, settings: SalesAgentSettings):
        if not settings.backend.url:
            raise ValueError("Backend URL is required")
        self.base_url = settings.backend.url.rstrip("/")
        self.timeout = 10.0
        self._service_header = settings.service.resolved_header()
        self._service_key = settings.service.api_key
        self._chat_client: httpx.AsyncClient | None = None

    def _get_chat_client(self) -> httpx.AsyncClient:
        if self._chat_client is None:
            headers = {}
            if self._service_key:
                headers[self._service_header] = self._service_key.get_secret_value()
            self._chat_client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(10.0, connect=5.0),
            )
        return self._chat_client

    async def close_chat_client(self) -> None:
        if self._chat_client is not None:
            await self._chat_client.aclose()
            self._chat_client = None

    async def list_connectors(self) -> BackendConnectorListResponse | None:
        if self._service_key is None:
            log.warning("backend.connectors.skipped", reason="service_key_missing")
            return None

        url = f"{self.base_url}/transport/connectors"
        headers = {self._service_header: self._service_key.get_secret_value()}

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 404:
                log.info("backend.connectors.endpoint_missing", url=url, status=status)
                return None
            log.warning("backend.connectors.http_error", url=url, status=status, error=str(exc))
            return None
        except httpx.HTTPError as exc:
            log.warning("backend.connectors.network_error", url=url, error=str(exc))
            return None

        payload = response.json()
        try:
            return BackendConnectorListResponse.model_validate(payload)
        except Exception as exc:
            log.warning("backend.connectors.invalid_payload", error=str(exc))
            return None

    # --- Write operations ---

    async def send_outbound_message(self, request: OutboundDeliveryRequest) -> None:
        if self._service_key is None:
            raise RuntimeError("Service API key is not configured")

        client = self._get_chat_client()
        try:
            response = await client.post(
                "/internal/messages/outbound",
                json=request.model_dump(mode="json"),
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            log.error(
                "backend.outbound.delivery_failed",
                connector_id=request.connector_id,
                conversation_id=request.conversation_id,
                error=str(exc),
            )
            raise

    async def update_customer_fields(self, user_id: str, company_id: int, updates: dict[str, Any]) -> None:
        client = self._get_chat_client()
        response = await client.patch(
            f"/internal/chat/customers/{user_id}/fields",
            json={"company_id": company_id, "updates": updates},
        )
        response.raise_for_status()

    async def mark_customer_rejected(self, user_id: str, company_id: int, reason: str = "") -> None:
        client = self._get_chat_client()
        response = await client.post(
            f"/internal/chat/customers/{user_id}/reject",
            json={"company_id": company_id, "reason": reason},
        )
        response.raise_for_status()

    async def reset_customer_profile(self, user_id: str, company_id: int) -> None:
        client = self._get_chat_client()
        response = await client.delete(
            f"/internal/chat/customers/{user_id}/profile",
            params={"company_id": company_id},
        )
        response.raise_for_status()

    async def update_order_stage(self, order_id: int, stage: str) -> dict[str, Any]:
        client = self._get_chat_client()
        response = await client.patch(
            f"/internal/orders/{order_id}/stage",
            json={"stage": stage},
        )
        response.raise_for_status()
        return response.json()

    async def update_fields(
        self, user_id: str, company_id: int, updates: dict[str, Any], order_id: int | None = None
    ) -> dict[str, Any]:
        client = self._get_chat_client()
        payload: dict[str, Any] = {"company_id": company_id, "updates": updates}
        if order_id is not None:
            payload["order_id"] = order_id
        response = await client.patch(
            f"/internal/chat/customers/{user_id}/fields",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def create_order_task(self, company_id: int, order_id: int, data: dict[str, Any]) -> dict[str, Any]:
        client = self._get_chat_client()
        response = await client.post(
            f"/internal/tasks/companies/{company_id}/orders/{order_id}",
            json=data,
        )
        response.raise_for_status()
        return response.json()

    async def close_order(self, order_id: int, result: str) -> dict[str, Any]:
        client = self._get_chat_client()
        response = await client.post(
            f"/internal/orders/{order_id}/close",
            json={"result": result},
        )
        response.raise_for_status()
        return response.json()

    async def request_handoff(
        self,
        order_id: int,
        summary: str = "Передача менеджеру",
        reason: str = "Требуется участие менеджера",
        *,
        escalate: bool = False,
    ) -> dict[str, Any]:
        client = self._get_chat_client()
        response = await client.post(
            f"/internal/orders/{order_id}/handoff",
            json={"summary": summary, "reason": reason, "escalate": escalate},
        )
        response.raise_for_status()
        return response.json()

    async def append_history_batch(
        self,
        thread_id: str,
        messages: list[tuple[str, str] | tuple[str, str, dict]],
    ) -> None:
        client = self._get_chat_client()
        message_envelopes = []
        for item in messages:
            if len(item) == 3:
                role, content, metadata = item
                delivered_at = None
                if isinstance(metadata, dict) and "__delivered_at" in metadata:
                    delivered_at = metadata.pop("__delivered_at")

                delivered_at_iso: str
                if isinstance(delivered_at, str) and delivered_at.strip():
                    delivered_at_iso = delivered_at.strip()
                elif isinstance(delivered_at, (int, float)):
                    delivered_at_iso = datetime.fromtimestamp(float(delivered_at), tz=UTC).isoformat()
                elif isinstance(delivered_at, datetime):
                    delivered_at_iso = delivered_at.astimezone(UTC).isoformat()
                elif delivered_at is None:
                    delivered_at_iso = datetime.now(UTC).isoformat()
                else:
                    raise TypeError(f"Unsupported __delivered_at type: {type(delivered_at).__name__}")

                message_envelopes.append(
                    {
                        "role": role,
                        "content": content,
                        "metadata": metadata,
                        "status": "sent",
                        "delivered_at": delivered_at_iso,
                    }
                )
            else:
                role, content = item
                message_envelopes.append(
                    {
                        "role": role,
                        "content": content,
                        "metadata": {},
                        "status": "sent",
                        "delivered_at": datetime.now(UTC).isoformat(),
                    }
                )

        response = await client.post(
            f"/internal/chat/threads/{thread_id}/messages",
            json={"source": "sales_agent", "messages": message_envelopes},
        )
        response.raise_for_status()

    async def get_message_by_id(self, message_id: str) -> dict[str, Any]:
        client = self._get_chat_client()
        response = await client.get(f"/internal/chat/messages/{message_id}")
        response.raise_for_status()
        return response.json()

    async def save_transcription(self, message_id: str, transcribed_text: str) -> dict[str, Any]:
        client = self._get_chat_client()
        response = await client.post(
            f"/internal/chat/messages/{message_id}/transcription",
            json={"transcribed_text": transcribed_text},
        )
        response.raise_for_status()
        return response.json()

    async def download_artifact(self, artifact_id: str) -> bytes:
        client = self._get_chat_client()
        response = await client.get(f"/internal/artifacts/{artifact_id}")
        response.raise_for_status()
        log.debug("artifact.downloaded", artifact_id=artifact_id, size_bytes=len(response.content))
        return response.content

    # --- Capability endpoints (scheduling) ---

    async def get_booking_services(self, company_id: int, staff_id: int | None = None) -> dict[str, Any]:
        client = self._get_chat_client()
        payload: dict[str, Any] = {"company_id": company_id}
        if staff_id is not None:
            payload["staff_id"] = staff_id
        response = await client.post("/internal/capabilities/scheduling/services", json=payload)
        response.raise_for_status()
        return response.json()

    async def list_staff(self, company_id: int, service_ids: list[int] | None = None) -> dict[str, Any]:
        client = self._get_chat_client()
        payload: dict[str, Any] = {"company_id": company_id}
        if service_ids:
            payload["service_ids"] = service_ids
        response = await client.post("/internal/capabilities/scheduling/staff", json=payload)
        response.raise_for_status()
        return response.json()

    async def get_available_dates(
        self,
        company_id: int,
        staff_id: int,
        service_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        client = self._get_chat_client()
        payload: dict[str, Any] = {
            "company_id": company_id,
            "staff_id": staff_id,
        }
        if service_ids:
            payload["service_ids"] = service_ids
        response = await client.post("/internal/capabilities/scheduling/dates", json=payload)
        response.raise_for_status()
        return response.json()

    async def get_available_slots(
        self,
        company_id: int,
        staff_id: int,
        date: str,
        service_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        client = self._get_chat_client()
        payload: dict[str, Any] = {
            "company_id": company_id,
            "staff_id": staff_id,
            "date": date,
        }
        if service_ids:
            payload["service_ids"] = service_ids
        response = await client.post("/internal/capabilities/scheduling/slots", json=payload)
        response.raise_for_status()
        return response.json()

    async def create_booking(
        self,
        company_id: int,
        phone: str,
        fullname: str,
        email: str = "",
        comment: str = "",
        appointments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        client = self._get_chat_client()
        payload: dict[str, Any] = {
            "company_id": company_id,
            "phone": phone,
            "fullname": fullname,
            "email": email,
            "comment": comment,
            "appointments": appointments or [],
        }
        response = await client.post("/internal/capabilities/scheduling/bookings", json=payload)
        response.raise_for_status()
        return response.json()
