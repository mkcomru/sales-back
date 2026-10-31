from fastapi import status
from fastapi.requests import Request
from fastapi.responses import JSONResponse


class S3StorageError(Exception):
    """Raised when S3 operations fail"""


class S3FileNotFoundError(S3StorageError):
    """Raised when requested file not found in S3"""


class PresignedUploadPolicyError(Exception):
    """filename/content_type/file_type combination is not allowed for presigned upload."""


async def s3_storage_error_handler(request: Request, exc: S3StorageError):
    """Handler for S3 storage errors"""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"message": "S3 storage error", "detail": str(exc)},
    )


async def s3_file_not_found_handler(request: Request, exc: S3FileNotFoundError):
    """Handler for S3 file not found errors"""
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"message": "File not found in S3", "detail": str(exc)},
    )
