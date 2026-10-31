"""Sales Agent client for inbound message forwarding with retry logic."""

import asyncio
from typing import Any

import httpx
import structlog

from common.models import InternalInboundRequest, TaskExecutionRequest

from src.backend.modules.core.settings import Settings

log = structlog.get_logger(__name__)

MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 1.0
TRANSCRIPTION_READ_TIMEOUT_S = 120.0


class SalesAgentClientError(Exception):
    """Raised when Sales Agent forwarding fails after all retries."""


class SalesAgentClient:
    """HTTP client for forwarding messages to Sales Agent with retry."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._service_header = settings.service.resolved_header()
        self._service_key = settings.service.api_key
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            sales_agent_url = self._settings.sales_agent.url
            if not sales_agent_url:
                raise SalesAgentClientError("Sales Agent URL is not configured")

            headers: dict[str, str] = {
                "Content-Type": "application/json",
            }
            if self._service_key:
                headers[self._service_header] = self._service_key.get_secret_value()

            self._client = httpx.AsyncClient(
                base_url=str(sales_agent_url).rstrip("/"),
                headers=headers,
                timeout=httpx.Timeout(30.0, connect=5.0),
            )
        return self._client

    async def _post_with_retry(
        self,
        path: str,
        payload: dict,
        *,
        log_context: dict,
        parse_json: bool = False,
        request_timeout: httpx.Timeout | None = None,
    ) -> dict[str, Any] | None:
        """POST with exponential backoff retries on 5xx / connection errors.

        When parse_json is True, returns the parsed JSON object on success.
        Otherwise returns None after a successful empty-body POST.
        """
        client = self._get_client()
        last_exc: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                post_kwargs: dict[str, Any] = {"json": payload}
                if request_timeout is not None:
                    post_kwargs["timeout"] = request_timeout
                response = await client.post(path, **post_kwargs)
                if response.status_code < 500:
                    response.raise_for_status()
                    if parse_json:
                        return response.json()
                    return None
                last_exc = httpx.HTTPStatusError(
                    f"Server error {response.status_code}",
                    request=response.request,
                    response=response,
                )
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
                last_exc = exc
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500:
                    raise SalesAgentClientError(str(exc)) from exc
                last_exc = exc

            backoff = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
            log.warning(
                "sales_agent.retry",
                attempt=attempt,
                max_retries=MAX_RETRIES,
                backoff_seconds=backoff,
                error=str(last_exc),
                **log_context,
            )
            if attempt < MAX_RETRIES:
                await asyncio.sleep(backoff)

        raise SalesAgentClientError(f"Failed after {MAX_RETRIES} attempts: {last_exc}") from last_exc

    async def forward_inbound(self, request: InternalInboundRequest) -> None:
        await self._post_with_retry(
            "/api/v1/internal/messages/inbound",
            request.model_dump(mode="json"),
            log_context={"connector_id": request.context.connector_id},
        )

    async def cancel_debounce(self, thread_id: str) -> None:
        """Cancel debounce bucket for thread when assistant is deactivated."""
        await self._post_with_retry(
            "/api/v1/internal/debounce/cancel",
            {"thread_id": thread_id},
            log_context={"thread_id": thread_id},
        )

    async def execute_task(self, request: TaskExecutionRequest) -> None:
        """Dispatch task to sales-agent (fire-and-forget, expects 202)."""
        await self._post_with_retry(
            "/api/v1/internal/tasks/execute",
            request.model_dump(mode="json"),
            log_context={"task_id": request.task_id},
        )

    async def request_transcription(self, artifact_id: str, mime: str | None = None) -> str:
        timeout = httpx.Timeout(TRANSCRIPTION_READ_TIMEOUT_S, connect=5.0)
        body: dict[str, Any] = {"artifact_id": artifact_id}
        if mime is not None:
            body["mime"] = mime
        data = await self._post_with_retry(
            "/api/v1/internal/transcription/transcribe",
            body,
            log_context={"artifact_id": artifact_id},
            parse_json=True,
            request_timeout=timeout,
        )
        if not isinstance(data, dict):
            raise SalesAgentClientError("Transcription response is not a JSON object")
        text = data.get("text")
        if not isinstance(text, str):
            raise SalesAgentClientError("Transcription response missing string 'text'")
        return text

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
