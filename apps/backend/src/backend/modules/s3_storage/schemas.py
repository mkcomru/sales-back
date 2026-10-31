from typing import Literal

from pydantic import BaseModel, Field, field_validator

from common import FileType

ManagerArtifactFileType = Literal["image", "audio", "video", "document"]


class ArtifactUploadResponse(BaseModel):
    """Response schema for artifact upload endpoint."""

    artifact_id: str = Field(..., description="S3 key (artifact ID) for the uploaded file")


class ArtifactPresignedUrlResponse(BaseModel):
    """Response schema for presigned URL endpoint."""

    url: str = Field(..., description="Presigned S3 GET URL")
    expires_in: int = Field(..., description="TTL of the presigned URL in seconds")


class ArtifactPresignedUploadRequest(BaseModel):
    """Request body for starting a direct-to-S3 upload via presigned PUT."""

    file_type: ManagerArtifactFileType = Field(..., description="Logical artifact type")
    filename: str = Field(..., min_length=1, max_length=512)
    content_type: str = Field(..., min_length=1, max_length=256)
    byte_size: int = Field(..., ge=1)

    @field_validator("filename")
    @classmethod
    def filename_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("filename must not be empty")
        return stripped


class ArtifactPresignedUploadResponse(BaseModel):
    """Presigned PUT target and final artifact_id (S3 key)."""

    artifact_id: str = Field(..., description="S3 key to reference in messages after upload completes")
    upload_url: str = Field(..., description="Presigned URL for HTTP PUT of the object bytes")
    expires_in: int = Field(..., description="TTL of the presigned PUT URL in seconds")
    required_headers: dict[str, str] = Field(
        default_factory=dict,
        description="Headers the client must send with PUT (e.g. Content-Type)",
    )


__all__ = [
    "ArtifactPresignedUploadRequest",
    "ArtifactPresignedUploadResponse",
    "ArtifactPresignedUrlResponse",
    "ArtifactUploadResponse",
    "FileType",
    "ManagerArtifactFileType",
]
