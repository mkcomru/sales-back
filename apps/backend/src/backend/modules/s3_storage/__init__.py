"""Storage module for S3-compatible object storage."""

from common import FileType

from src.backend.modules.s3_storage.exceptions import S3FileNotFoundError, S3StorageError
from src.backend.modules.s3_storage.routers import (
    internal_router as artifacts_internal_router,
)
from src.backend.modules.s3_storage.routers import (
    public_router as artifacts_public_router,
)
from src.backend.modules.s3_storage.s3_client import S3Client

__all__ = [
    "S3Client",
    "S3StorageError",
    "S3FileNotFoundError",
    "FileType",
    "artifacts_internal_router",
    "artifacts_public_router",
]
