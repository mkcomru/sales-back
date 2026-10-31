"""API endpoints for artifact management."""

from __future__ import annotations

import mimetypes
import uuid
from typing import Literal

import structlog
from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Path,
    Query,
    Response,
    UploadFile,
    status,
)

from common import ArtifactService, FileType
from common.services.audio_converter import AudioConversionError

from src.backend.modules.auth.dependencies import CompanyManagerDep, CompanyViewerDep
from src.backend.modules.core.dependencies import require_service_api_key
from src.backend.modules.s3_storage.dependencies import AudioConverterDep, S3ClientDep
from src.backend.modules.s3_storage.exceptions import (
    PresignedUploadPolicyError,
    S3FileNotFoundError,
    S3StorageError,
)
from src.backend.modules.s3_storage.presigned_upload_policy import validate_presigned_upload_policy
from src.backend.modules.s3_storage.schemas import (
    ArtifactPresignedUploadRequest,
    ArtifactPresignedUploadResponse,
    ArtifactPresignedUrlResponse,
    ArtifactUploadResponse,
)

log = structlog.get_logger(__name__)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_VOICE_FILE_SIZE = 10 * 1024 * 1024  # 10MB
PRESIGNED_URL_EXPIRES_SECONDS = 3600

internal_router = APIRouter(prefix="/internal/artifacts", tags=["artifacts:internal"])
public_router = APIRouter(prefix="/companies/{company_id}", tags=["artifacts"])
public_direct_router = APIRouter(prefix="/artifacts/by-company", tags=["artifacts"])


@internal_router.post(
    "/upload",
    status_code=status.HTTP_200_OK,
    response_model=ArtifactUploadResponse,
    dependencies=[Depends(require_service_api_key)],
)
async def upload_artifact(
    s3_client: S3ClientDep,
    file: UploadFile = File(...),
    file_type: str = Form(...),
    company_id: int = Form(...),
    x_connector_id: str | None = Header(default=None, alias="X-Connector-Id"),
) -> ArtifactUploadResponse:
    """Upload file to S3 and return artifact_id.

    Args:
        file: File content as UploadFile
        file_type: File type (voice, audio, image, video, document)
        company_id: Company identifier
        x_connector_id: Connector ID from header (optional)
        s3_client: S3 client dependency

    Returns:
        Dictionary with artifact_id (S3 key)

    Raises:
        HTTPException: If file size exceeds limit or upload fails
    """
    file_bytes = await file.read()

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum allowed size of {MAX_FILE_SIZE} bytes",
        )

    try:
        file_type_enum = FileType(file_type)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file_type: {file_type}. Must be one of: {', '.join(ft.value for ft in FileType)}",
        ) from e

    try:
        artifact_id = await s3_client.upload_file(
            company_id=company_id,
            file_type=file_type_enum,
            file_bytes=file_bytes,
            mime_type=None,
        )

        log.info(
            "artifact.uploaded",
            artifact_id=artifact_id,
            company_id=company_id,
            file_type=file_type,
            size_bytes=len(file_bytes),
        )

        return ArtifactUploadResponse(artifact_id=artifact_id)

    except S3StorageError as e:
        log.error("artifact.upload_failed", company_id=company_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {e}",
        ) from e


@public_router.post(
    "/artifacts/upload",
    status_code=status.HTTP_200_OK,
    response_model=ArtifactUploadResponse,
)
async def upload_artifact_for_manager(
    s3_client: S3ClientDep,
    user: CompanyManagerDep,
    company_id: int = Path(...),
    file: UploadFile = File(...),
    file_type: Literal["image", "audio", "video", "document"] = Form(...),
) -> ArtifactUploadResponse:
    """Upload media file to S3 on behalf of a manager."""
    file_type_enum = FileType(file_type)

    file_bytes = await file.read()

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum allowed size of {MAX_FILE_SIZE} bytes",
        )

    try:
        artifact_id = await s3_client.upload_file(
            company_id=company_id,
            file_type=file_type_enum,
            file_bytes=file_bytes,
            filename=file.filename,
            mime_type=file.content_type,
        )

        log.info(
            "artifact.manager_uploaded",
            artifact_id=artifact_id,
            company_id=company_id,
            file_type=file_type,
            size_bytes=len(file_bytes),
            user_id=user.id,
        )

        return ArtifactUploadResponse(artifact_id=artifact_id)

    except S3StorageError as e:
        log.error("artifact.upload_failed", company_id=company_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {e}",
        ) from e


@public_router.post(
    "/artifacts/voice-upload",
    status_code=status.HTTP_200_OK,
    response_model=ArtifactUploadResponse,
)
async def upload_voice_for_manager(
    s3_client: S3ClientDep,
    audio_converter: AudioConverterDep,
    user: CompanyManagerDep,
    company_id: int = Path(...),
    file: UploadFile = File(...),
) -> ArtifactUploadResponse:
    """Accept raw audio from CRM frontend, convert to MP3 server-side, store in S3.

    This endpoint exists because browsers cannot run ffmpeg. Transport connectors
    must NOT use this — they convert to MP3 themselves via AudioConversionService
    before uploading through the internal /artifacts/upload endpoint.
    """
    file_bytes = await file.read()

    if len(file_bytes) > MAX_VOICE_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Voice file exceeds maximum allowed size of {MAX_VOICE_FILE_SIZE} bytes",
        )

    try:
        mp3_bytes = await audio_converter.convert_to_mp3(file_bytes)
    except AudioConversionError as e:
        log.error("artifact.voice_conversion_failed", company_id=company_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Audio conversion to MP3 failed",
        ) from e

    try:
        artifact_id = await s3_client.upload_file(
            company_id=company_id,
            file_type=FileType.AUDIO,
            file_bytes=mp3_bytes,
            mime_type="audio/mpeg",
        )
        log.info(
            "artifact.voice_uploaded",
            artifact_id=artifact_id,
            company_id=company_id,
            original_size=len(file_bytes),
            mp3_size=len(mp3_bytes),
            user_id=user.id,
        )
        return ArtifactUploadResponse(artifact_id=artifact_id)
    except S3StorageError as e:
        log.error("artifact.voice_upload_failed", company_id=company_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload voice: {e}",
        ) from e


@public_router.post(
    "/artifacts/presigned-upload",
    status_code=status.HTTP_200_OK,
    response_model=ArtifactPresignedUploadResponse,
)
async def create_manager_presigned_upload(
    s3_client: S3ClientDep,
    user: CompanyManagerDep,
    company_id: int = Path(...),
    body: ArtifactPresignedUploadRequest = Body(...),
) -> ArtifactPresignedUploadResponse:
    """Issue a presigned PUT URL so the browser uploads bytes directly to object storage."""
    if body.byte_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds maximum allowed size of {MAX_FILE_SIZE} bytes",
        )

    file_type_enum = FileType(body.file_type)
    try:
        validate_presigned_upload_policy(file_type_enum, body.filename, body.content_type)
    except PresignedUploadPolicyError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    file_id = uuid.uuid4().hex[:16]
    artifact_id = ArtifactService.build_artifact_id(
        company_id,
        file_type_enum,
        file_id,
        body.filename,
    )

    try:
        upload_url = await s3_client.get_presigned_put_url(artifact_id, body.content_type)
        log.info(
            "artifact.presigned_upload_issued",
            artifact_id=artifact_id,
            company_id=company_id,
            file_type=body.file_type,
            byte_size=body.byte_size,
            user_id=user.id,
        )
        return ArtifactPresignedUploadResponse(
            artifact_id=artifact_id,
            upload_url=upload_url,
            expires_in=PRESIGNED_URL_EXPIRES_SECONDS,
            required_headers={"Content-Type": body.content_type},
        )
    except S3StorageError as e:
        log.error("artifact.presigned_upload_failed", company_id=company_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate presigned upload URL: {e}",
        ) from e


@public_router.get(
    "/artifacts/presigned-url",
    response_model=ArtifactPresignedUrlResponse,
)
async def get_company_artifact_presigned_url(
    s3_client: S3ClientDep,
    user: CompanyViewerDep,
    company_id: int = Path(...),
    artifact_id: str = Query(..., min_length=1, description="S3 key (same as artifact_id in messages)"),
) -> ArtifactPresignedUrlResponse:
    """Presigned GET for chat/media clients (direct download from storage, not via API proxy)."""
    ArtifactService.validate_belongs_to_company(artifact_id, company_id)
    try:
        url = await s3_client.get_presigned_url(artifact_id)
        return ArtifactPresignedUrlResponse(url=url, expires_in=PRESIGNED_URL_EXPIRES_SECONDS)
    except S3FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found") from None
    except S3StorageError as e:
        log.error("artifact.presigned_get_failed", artifact_id=artifact_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate presigned URL: {e}",
        ) from e


@public_router.get(
    "/artifacts/{artifact_id:path}",
)
async def get_artifact_for_company(
    s3_client: S3ClientDep,
    user: CompanyViewerDep,
    artifact_id: str = Path(...),
    company_id: int = Path(...),
) -> Response:
    """Get artifact file for company (frontend access).

    Args:
        artifact_id: S3 key (artifact ID)
        company_id: Company ID from path
        s3_client: S3 client dependency

    Returns:
        File content with appropriate headers

    Raises:
        HTTPException: If artifact not found or access denied
    """
    ArtifactService.validate_belongs_to_company(artifact_id, company_id)

    try:
        file_bytes = await s3_client.download_file(artifact_id)

        content_type, _ = mimetypes.guess_type(artifact_id)
        content_type = content_type or "application/octet-stream"

        return Response(
            content=file_bytes,
            media_type=content_type,
            headers={"Content-Disposition": f'inline; filename="{artifact_id.split("/")[-1]}"'},
        )

    except S3FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found",
        ) from None
    except S3StorageError as e:
        log.error("artifact.download_failed", artifact_id=artifact_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download artifact: {e}",
        ) from e


@public_direct_router.get(
    "/{company_id}/{artifact_id:path}",
)
async def get_artifact_direct(
    s3_client: S3ClientDep,
    user: CompanyViewerDep,
    artifact_id: str = Path(...),
    company_id: int = Path(..., ge=1),
) -> Response:
    """Get artifact file (direct path, avoids route conflicts)."""
    ArtifactService.validate_belongs_to_company(artifact_id, company_id)

    try:
        file_bytes = await s3_client.download_file(artifact_id)

        content_type, _ = mimetypes.guess_type(artifact_id)
        content_type = content_type or "application/octet-stream"

        return Response(
            content=file_bytes,
            media_type=content_type,
            headers={"Content-Disposition": f'inline; filename="{artifact_id.split("/")[-1]}"'},
        )

    except S3FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found",
        ) from None
    except S3StorageError as e:
        log.error("artifact.download_failed", artifact_id=artifact_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download artifact: {e}",
        ) from e


@internal_router.get(
    "/{artifact_id:path}/presigned-url",
    response_model=ArtifactPresignedUrlResponse,
    dependencies=[Depends(require_service_api_key)],
)
async def get_artifact_presigned_url(
    s3_client: S3ClientDep,
    artifact_id: str = Path(...),
) -> ArtifactPresignedUrlResponse:
    """Generate a presigned S3 GET URL for an artifact (transport modules)."""
    try:
        url = await s3_client.get_presigned_url(artifact_id)
        return ArtifactPresignedUrlResponse(url=url, expires_in=PRESIGNED_URL_EXPIRES_SECONDS)
    except S3FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found") from None
    except S3StorageError as e:
        log.error("artifact.presigned_url_failed", artifact_id=artifact_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate presigned URL: {e}",
        ) from e


@internal_router.get(
    "/{artifact_id:path}",
    dependencies=[Depends(require_service_api_key)],
)
async def get_artifact_internal(
    s3_client: S3ClientDep,
    artifact_id: str = Path(...),
) -> Response:
    """Get artifact file for internal services (Sales-Agent).

    Args:
        artifact_id: S3 key (artifact ID)
        s3_client: S3 client dependency

    Returns:
        File content with appropriate headers

    Raises:
        HTTPException: If artifact not found
    """
    try:
        file_bytes = await s3_client.download_file(artifact_id)

        content_type, _ = mimetypes.guess_type(artifact_id)
        content_type = content_type or "application/octet-stream"

        return Response(
            content=file_bytes,
            media_type=content_type,
        )

    except S3FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Artifact not found",
        ) from None
    except S3StorageError as e:
        log.error("artifact.download_failed", artifact_id=artifact_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download artifact: {e}",
        ) from e
