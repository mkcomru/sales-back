"""Tests for s3_storage artifact endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from src.backend.modules.s3_storage.dependencies import get_s3_client
from src.backend.modules.s3_storage.exceptions import S3FileNotFoundError, S3StorageError
from src.backend.modules.s3_storage.s3_client import S3Client


@pytest.fixture
def mock_s3(fastapi_app) -> AsyncMock:
    """Override the S3 client with a mock for all tests in this module."""
    mock = AsyncMock(spec=S3Client)
    fastapi_app.dependency_overrides[get_s3_client] = lambda: mock
    yield mock
    fastapi_app.dependency_overrides.pop(get_s3_client, None)


class TestInternalUploadEndpoint:
    """Tests for POST /api/v1/internal/artifacts/upload."""

    @pytest.mark.asyncio
    async def test_upload_success(
        self,
        api_client: httpx.AsyncClient,
        service_headers: dict[str, str],
        mock_s3: AsyncMock,
    ) -> None:
        mock_s3.upload_file = AsyncMock(return_value="company_1/image/photo.jpg")

        response = await api_client.post(
            "/api/v1/internal/artifacts/upload",
            headers={**service_headers, "X-Connector-Id": "conn-1"},
            data={"file_type": "image", "company_id": "1"},
            files={"file": ("photo.jpg", b"fake_image_data", "image/jpeg")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["artifact_id"] == "company_1/image/photo.jpg"
        mock_s3.upload_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_requires_service_key(
        self,
        api_client: httpx.AsyncClient,
        mock_s3: AsyncMock,
    ) -> None:
        response = await api_client.post(
            "/api/v1/internal/artifacts/upload",
            data={"file_type": "image", "company_id": "1"},
            files={"file": ("photo.jpg", b"data", "image/jpeg")},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_invalid_file_type(
        self,
        api_client: httpx.AsyncClient,
        service_headers: dict[str, str],
        mock_s3: AsyncMock,
    ) -> None:
        response = await api_client.post(
            "/api/v1/internal/artifacts/upload",
            headers=service_headers,
            data={"file_type": "unsupported_type", "company_id": "1"},
            files={"file": ("file.xyz", b"data", "application/octet-stream")},
        )

        assert response.status_code == 400
        assert "Invalid file_type" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_file_too_large(
        self,
        api_client: httpx.AsyncClient,
        service_headers: dict[str, str],
        mock_s3: AsyncMock,
    ) -> None:
        large_file = b"x" * (50 * 1024 * 1024 + 1)

        response = await api_client.post(
            "/api/v1/internal/artifacts/upload",
            headers=service_headers,
            data={"file_type": "image", "company_id": "1"},
            files={"file": ("big.jpg", large_file, "image/jpeg")},
        )

        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_upload_s3_error_returns_500(
        self,
        api_client: httpx.AsyncClient,
        service_headers: dict[str, str],
        mock_s3: AsyncMock,
    ) -> None:
        mock_s3.upload_file = AsyncMock(side_effect=S3StorageError("S3 unavailable"))

        response = await api_client.post(
            "/api/v1/internal/artifacts/upload",
            headers=service_headers,
            data={"file_type": "audio", "company_id": "1"},
            files={"file": ("audio.mp3", b"audio_data", "audio/mpeg")},
        )

        assert response.status_code == 500
        assert "Failed to upload file" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_voice_type(
        self,
        api_client: httpx.AsyncClient,
        service_headers: dict[str, str],
        mock_s3: AsyncMock,
    ) -> None:
        mock_s3.upload_file = AsyncMock(return_value="company_1/voice/voice.ogg")

        response = await api_client.post(
            "/api/v1/internal/artifacts/upload",
            headers=service_headers,
            data={"file_type": "voice", "company_id": "1"},
            files={"file": ("voice.ogg", b"voice_data", "audio/ogg")},
        )

        assert response.status_code == 200
        assert response.json()["artifact_id"] == "company_1/voice/voice.ogg"


class TestManagerUploadEndpoint:
    """Tests for POST /api/v1/companies/{company_id}/artifacts/upload."""

    @pytest.mark.asyncio
    async def test_manager_upload_success(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
        mock_s3: AsyncMock,
    ) -> None:
        auth = authenticated_user_with_company
        company_id = auth["company"].id
        mock_s3.upload_file = AsyncMock(return_value=f"company_{company_id}/image/photo.jpg")

        response = await api_client.post(
            f"/api/v1/companies/{company_id}/artifacts/upload",
            headers=auth["headers"],
            data={"file_type": "image"},
            files={"file": ("photo.jpg", b"image_bytes", "image/jpeg")},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["artifact_id"] == f"company_{company_id}/image/photo.jpg"
        mock_s3.upload_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_manager_upload_requires_auth(
        self,
        api_client: httpx.AsyncClient,
        company_factory,
        mock_s3: AsyncMock,
    ) -> None:
        company = await company_factory()

        response = await api_client.post(
            f"/api/v1/companies/{company.id}/artifacts/upload",
            data={"file_type": "image"},
            files={"file": ("photo.jpg", b"data", "image/jpeg")},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_manager_upload_file_too_large(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
        mock_s3: AsyncMock,
    ) -> None:
        auth = authenticated_user_with_company
        company_id = auth["company"].id
        large_file = b"x" * (50 * 1024 * 1024 + 1)

        response = await api_client.post(
            f"/api/v1/companies/{company_id}/artifacts/upload",
            headers=auth["headers"],
            data={"file_type": "image"},
            files={"file": ("big.jpg", large_file, "image/jpeg")},
        )

        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_manager_upload_document(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
        mock_s3: AsyncMock,
    ) -> None:
        auth = authenticated_user_with_company
        company_id = auth["company"].id
        mock_s3.upload_file = AsyncMock(return_value=f"company_{company_id}/document/report.pdf")

        response = await api_client.post(
            f"/api/v1/companies/{company_id}/artifacts/upload",
            headers=auth["headers"],
            data={"file_type": "document"},
            files={"file": ("report.pdf", b"pdf_data", "application/pdf")},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_manager_upload_s3_error(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
        mock_s3: AsyncMock,
    ) -> None:
        auth = authenticated_user_with_company
        company_id = auth["company"].id
        mock_s3.upload_file = AsyncMock(side_effect=S3StorageError("S3 unavailable"))

        response = await api_client.post(
            f"/api/v1/companies/{company_id}/artifacts/upload",
            headers=auth["headers"],
            data={"file_type": "image"},
            files={"file": ("photo.jpg", b"data", "image/jpeg")},
        )

        assert response.status_code == 500


class TestPresignedUrlEndpoint:
    """Tests for GET /api/v1/internal/artifacts/{artifact_id}/presigned-url."""

    @pytest.mark.asyncio
    async def test_presigned_url_success(
        self,
        api_client: httpx.AsyncClient,
        service_headers: dict[str, str],
        mock_s3: AsyncMock,
    ) -> None:
        artifact_id = "company_1/image/photo.jpg"
        presigned_url = "https://s3.example.com/photo.jpg?Signature=abc&Expires=1234567890"
        mock_s3.get_presigned_url = AsyncMock(return_value=presigned_url)

        response = await api_client.get(
            f"/api/v1/internal/artifacts/{artifact_id}/presigned-url",
            headers=service_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["url"] == presigned_url
        assert data["expires_in"] == 3600
        mock_s3.get_presigned_url.assert_called_once_with(artifact_id)

    @pytest.mark.asyncio
    async def test_presigned_url_requires_service_key(
        self,
        api_client: httpx.AsyncClient,
        mock_s3: AsyncMock,
    ) -> None:
        response = await api_client.get(
            "/api/v1/internal/artifacts/company_1/image/photo.jpg/presigned-url",
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_presigned_url_not_found(
        self,
        api_client: httpx.AsyncClient,
        service_headers: dict[str, str],
        mock_s3: AsyncMock,
    ) -> None:
        mock_s3.get_presigned_url = AsyncMock(side_effect=S3FileNotFoundError("Not found"))

        response = await api_client.get(
            "/api/v1/internal/artifacts/company_1/image/missing.jpg/presigned-url",
            headers=service_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_presigned_url_s3_error(
        self,
        api_client: httpx.AsyncClient,
        service_headers: dict[str, str],
        mock_s3: AsyncMock,
    ) -> None:
        mock_s3.get_presigned_url = AsyncMock(side_effect=S3StorageError("S3 error"))

        response = await api_client.get(
            "/api/v1/internal/artifacts/company_1/image/photo.jpg/presigned-url",
            headers=service_headers,
        )

        assert response.status_code == 500
        assert "Failed to generate presigned URL" in response.json()["detail"]


class TestInternalGetArtifactEndpoint:
    """Tests for GET /api/v1/internal/artifacts/{artifact_id}."""

    @pytest.mark.asyncio
    async def test_get_artifact_success(
        self,
        api_client: httpx.AsyncClient,
        service_headers: dict[str, str],
        mock_s3: AsyncMock,
    ) -> None:
        file_bytes = b"fake_image_content"
        mock_s3.download_file = AsyncMock(return_value=file_bytes)

        response = await api_client.get(
            "/api/v1/internal/artifacts/company_1/image/photo.jpg",
            headers=service_headers,
        )

        assert response.status_code == 200
        assert response.content == file_bytes
        assert "image/jpeg" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_get_artifact_requires_service_key(
        self,
        api_client: httpx.AsyncClient,
        mock_s3: AsyncMock,
    ) -> None:
        response = await api_client.get(
            "/api/v1/internal/artifacts/company_1/image/photo.jpg",
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_artifact_not_found(
        self,
        api_client: httpx.AsyncClient,
        service_headers: dict[str, str],
        mock_s3: AsyncMock,
    ) -> None:
        mock_s3.download_file = AsyncMock(side_effect=S3FileNotFoundError("Not found"))

        response = await api_client.get(
            "/api/v1/internal/artifacts/company_1/image/missing.jpg",
            headers=service_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_artifact_s3_error(
        self,
        api_client: httpx.AsyncClient,
        service_headers: dict[str, str],
        mock_s3: AsyncMock,
    ) -> None:
        mock_s3.download_file = AsyncMock(side_effect=S3StorageError("S3 error"))

        response = await api_client.get(
            "/api/v1/internal/artifacts/company_1/image/photo.jpg",
            headers=service_headers,
        )

        assert response.status_code == 500
        assert "Failed to download artifact" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_artifact_octet_stream_for_unknown_type(
        self,
        api_client: httpx.AsyncClient,
        service_headers: dict[str, str],
        mock_s3: AsyncMock,
    ) -> None:
        mock_s3.download_file = AsyncMock(return_value=b"binary_data")

        response = await api_client.get(
            "/api/v1/internal/artifacts/company_1/document/report.unknownext9999",
            headers=service_headers,
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/octet-stream"


class TestManagerPresignedUpload:
    """Tests for POST /api/v1/companies/{company_id}/artifacts/presigned-upload."""

    @pytest.mark.asyncio
    async def test_presigned_upload_audio_mp3(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
        mock_s3: AsyncMock,
    ) -> None:
        auth = authenticated_user_with_company
        company_id = auth["company"].id
        put_url = "https://s3.example.com/bucket/key?X-Amz-Signature=abc"
        mock_s3.get_presigned_put_url = AsyncMock(return_value=put_url)

        response = await api_client.post(
            f"/api/v1/companies/{company_id}/artifacts/presigned-upload",
            headers={**auth["headers"], "Content-Type": "application/json"},
            json={
                "file_type": "audio",
                "filename": "voice.mp3",
                "content_type": "audio/mpeg",
                "byte_size": 1024,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["upload_url"] == put_url
        assert data["expires_in"] == 3600
        assert data["required_headers"]["Content-Type"] == "audio/mpeg"
        assert data["artifact_id"].startswith(f"company_{company_id}/audio/")
        assert data["artifact_id"].endswith(".mp3")
        mock_s3.get_presigned_put_url.assert_called_once()
        call_kw = mock_s3.get_presigned_put_url.call_args
        assert call_kw[0][1] == "audio/mpeg"

    @pytest.mark.asyncio
    async def test_presigned_upload_rejects_non_mp3_audio(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
        mock_s3: AsyncMock,
    ) -> None:
        auth = authenticated_user_with_company
        company_id = auth["company"].id

        response = await api_client.post(
            f"/api/v1/companies/{company_id}/artifacts/presigned-upload",
            headers={**auth["headers"], "Content-Type": "application/json"},
            json={
                "file_type": "audio",
                "filename": "clip.webm",
                "content_type": "audio/webm",
                "byte_size": 100,
            },
        )

        assert response.status_code == 400
        mock_s3.get_presigned_put_url.assert_not_called()

    @pytest.mark.asyncio
    async def test_presigned_upload_too_large(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
        mock_s3: AsyncMock,
    ) -> None:
        auth = authenticated_user_with_company
        company_id = auth["company"].id

        response = await api_client.post(
            f"/api/v1/companies/{company_id}/artifacts/presigned-upload",
            headers={**auth["headers"], "Content-Type": "application/json"},
            json={
                "file_type": "image",
                "filename": "x.jpg",
                "content_type": "image/jpeg",
                "byte_size": 50 * 1024 * 1024 + 1,
            },
        )

        assert response.status_code == 413
        mock_s3.get_presigned_put_url.assert_not_called()


class TestCompanyArtifactPresignedGet:
    """Tests for GET /api/v1/companies/{company_id}/artifacts/presigned-url."""

    @pytest.mark.asyncio
    async def test_company_presigned_get_success(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
        mock_s3: AsyncMock,
    ) -> None:
        auth = authenticated_user_with_company
        company_id = auth["company"].id
        artifact_id = f"company_{company_id}/audio/abc123voice.mp3"
        presigned = "https://s3.example.com/get?sig=1"
        mock_s3.get_presigned_url = AsyncMock(return_value=presigned)

        response = await api_client.get(
            f"/api/v1/companies/{company_id}/artifacts/presigned-url",
            params={"artifact_id": artifact_id},
            headers=auth["headers"],
        )

        assert response.status_code == 200
        data = response.json()
        assert data["url"] == presigned
        assert data["expires_in"] == 3600
        mock_s3.get_presigned_url.assert_called_once_with(artifact_id)

    @pytest.mark.asyncio
    async def test_company_presigned_get_wrong_company_prefix(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
        mock_s3: AsyncMock,
    ) -> None:
        auth = authenticated_user_with_company
        company_id = auth["company"].id

        response = await api_client.get(
            f"/api/v1/companies/{company_id}/artifacts/presigned-url",
            params={"artifact_id": "company_99999/audio/x.mp3"},
            headers=auth["headers"],
        )

        assert response.status_code == 403
        mock_s3.get_presigned_url.assert_not_called()
