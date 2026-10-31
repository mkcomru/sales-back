"""Base integration client with shared HTTP plumbing.

All provider-specific HTTP clients inherit from BaseIntegrationClient
and get retry, rate limiting, structured logging, and auth header injection.
"""

from __future__ import annotations

import asyncio
import time
from types import TracebackType

import httpx
import structlog

log = structlog.get_logger(__name__)

DEFAULT_TIMEOUT_S = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE_S = 1.0
DEFAULT_RATE_LIMIT_RPS = 10.0


class BaseIntegrationClient:
    """Async HTTP client with retry, rate limiting, and structured logging."""

    provider_type: str = "base"

    def __init__(
        self,
        *,
        base_url: str,
        headers: dict[str, str] | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base_s: float = DEFAULT_BACKOFF_BASE_S,
        rate_limit_rps: float = DEFAULT_RATE_LIMIT_RPS,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = headers or {}
        self._timeout = httpx.Timeout(timeout_s)
        self._max_retries = max_retries
        self._backoff_base_s = backoff_base_s
        self._client: httpx.AsyncClient | None = None

        self._rate_limit_rps = rate_limit_rps
        self._tokens = rate_limit_rps
        self._last_refill = time.monotonic()

    async def __aenter__(self) -> BaseIntegrationClient:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=self._timeout,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _wait_for_token(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._rate_limit_rps, self._tokens + elapsed * self._rate_limit_rps)
        self._last_refill = now
        if self._tokens < 1:
            wait = (1 - self._tokens) / self._rate_limit_rps
            await asyncio.sleep(wait)
            self._tokens = 0
        else:
            self._tokens -= 1

    async def request(
        self,
        method: str,
        path: str,
        **kwargs: object,
    ) -> httpx.Response:
        if not self._client:
            raise RuntimeError("Client not initialized — use async context manager")

        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            await self._wait_for_token()
            try:
                response = await self._client.request(method, path, **kwargs)
                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", self._backoff_base_s * attempt))
                    log.warning(
                        "integration.rate_limited",
                        provider=self.provider_type,
                        attempt=attempt,
                        retry_after=retry_after,
                    )
                    await asyncio.sleep(retry_after)
                    continue
                if response.status_code >= 500 and attempt < self._max_retries:
                    delay = self._backoff_base_s * (2 ** (attempt - 1))
                    log.warning(
                        "integration.server_error",
                        provider=self.provider_type,
                        status=response.status_code,
                        attempt=attempt,
                        retry_in=delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError:
                raise
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    delay = self._backoff_base_s * (2 ** (attempt - 1))
                    log.warning(
                        "integration.request_error",
                        provider=self.provider_type,
                        error=str(exc),
                        attempt=attempt,
                        retry_in=delay,
                    )
                    await asyncio.sleep(delay)

        raise last_exc or RuntimeError("Exhausted retries with no response")

    async def get(self, path: str, **kwargs: object) -> httpx.Response:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: object) -> httpx.Response:
        return await self.request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: object) -> httpx.Response:
        return await self.request("PUT", path, **kwargs)

    async def delete(self, path: str, **kwargs: object) -> httpx.Response:
        return await self.request("DELETE", path, **kwargs)
