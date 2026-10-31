from __future__ import annotations

from abc import ABC, abstractmethod
from http import HTTPStatus

import httpx
import structlog
from pydantic import SecretStr

from common.schemas import FileType
from common.utils.retry import RetryStrategy, retry_with_backoff

log = structlog.get_logger(__name__)


class TransportBackendClientError(RuntimeError):
    """Signals a failure communicating with the backend service."""


class BaseTransportBackendClient[TConfig](ABC):
    """Contract and shared utilities for backend clients in transport modules.

    Subclasses must initialize the following instance attributes in __init__:
        _base_url: str
        _auth_header: str
        _api_key: SecretStr
        _timeout: float
        _artifact_upload_max_retries: int
        _artifact_upload_retry_delay_s: float
    """

    _base_url: str
    _auth_header: str
    _api_key: SecretStr
    _timeout: float
    _artifact_upload_max_retries: int
    _artifact_upload_retry_delay_s: float

    @abstractmethod
    async def fetch_connectors(self) -> list[TConfig]:
        """Fetch active connector configurations from backend."""
        ...

    async def upload_artifact(
        self,
        file_bytes: bytes,
        file_type: FileType | str,
        company_id: int,
        connector_id: str,
    ) -> str:
        """Upload file to Backend and return artifact_id.

        Raises:
            TransportBackendClientError: If upload fails after retries
        """
        file_type_str = file_type.value if isinstance(file_type, FileType) else file_type

        async def _do_upload() -> str:
            url = f"{self._base_url}/internal/artifacts/upload"
            headers: dict[str, str] = {
                self._auth_header: self._api_key.get_secret_value(),
                "X-Connector-Id": connector_id,
            }
            files = {"file": ("audio.mp3", file_bytes, "audio/mpeg")}
            data = {"file_type": file_type_str, "company_id": str(company_id)}

            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, files=files, data=data, headers=headers)
                response.raise_for_status()

                if response.status_code != HTTPStatus.OK:
                    raise TransportBackendClientError(
                        f"Backend responded with status {response.status_code}: {response.text}"
                    )

                result = response.json()
                artifact_id = result.get("artifact_id")
                if not artifact_id:
                    raise TransportBackendClientError("Backend response missing artifact_id")

                log.info(
                    "artifact.uploaded",
                    artifact_id=artifact_id,
                    company_id=company_id,
                    file_type=file_type_str,
                    size_bytes=len(file_bytes),
                )
                return artifact_id

        def _should_retry(exc: Exception) -> bool:
            return not isinstance(exc, TransportBackendClientError)

        strategy = RetryStrategy(
            max_attempts=self._artifact_upload_max_retries,
            base_delay_s=self._artifact_upload_retry_delay_s,
            backoff_type="linear",
        )

        try:
            return await retry_with_backoff(
                _do_upload,
                strategy=strategy,
                retry_on=_should_retry,
                log_context={
                    "company_id": company_id,
                    "file_type": file_type_str,
                    "size_bytes": len(file_bytes),
                },
            )
        except Exception as e:
            raise TransportBackendClientError(
                f"Failed to upload artifact after {strategy.max_attempts} attempts: {e}"
            ) from e

    async def get_artifact_download_url(self, artifact_id: str) -> str:
        """Get a presigned S3 download URL for an artifact.

        Raises:
            TransportBackendClientError: If the request fails or URL is missing
        """
        url = f"{self._base_url}/internal/artifacts/{artifact_id}/presigned-url"
        headers: dict[str, str] = {self._auth_header: self._api_key.get_secret_value()}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TransportBackendClientError(f"Failed to get presigned URL for {artifact_id}: {exc}") from exc

        result = response.json()
        download_url = result.get("url")
        if not download_url:
            raise TransportBackendClientError(f"Backend response missing url for {artifact_id}")
        return download_url

    async def download_artifact(self, artifact_id: str) -> bytes:
        """Download artifact bytes via presigned URL.

        Raises:
            TransportBackendClientError: If download fails
        """
        download_url = await self.get_artifact_download_url(artifact_id)

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(download_url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TransportBackendClientError(f"Failed to download artifact {artifact_id}: {exc}") from exc

        return response.content
