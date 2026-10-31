"""S3-compatible storage client using aioboto3."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import aioboto3
import structlog
from botocore.exceptions import ClientError

from common import ArtifactService, FileType
from common.config import S3Settings

from src.backend.modules.s3_storage.exceptions import S3FileNotFoundError, S3StorageError

logger = structlog.get_logger(__name__)


class S3Client:
    """Async S3-compatible storage client.

    Handles file uploads, downloads, and deletions with company-based organization.
    Files are stored under: company_{company_id}/{file_type}/{file_id}.{ext}
    """

    def __init__(self, settings: S3Settings) -> None:
        self._endpoint_url = settings.endpoint_url
        self._access_key_id = settings.access_key_id.get_secret_value()
        self._secret_access_key = settings.secret_access_key.get_secret_value()
        self._bucket_name = settings.bucket_name
        self._region_name = settings.region_name or "us-east-1"
        self._use_ssl = settings.use_ssl
        self._session = aioboto3.Session()

    @asynccontextmanager
    async def _client(self):
        async with self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key_id,
            aws_secret_access_key=self._secret_access_key,
            region_name=self._region_name,
            use_ssl=self._use_ssl,
        ) as s3:
            yield s3

    async def upload_file(
        self,
        company_id: int | str,
        file_type: FileType | str,
        file_bytes: bytes,
        filename: str | None = None,
        mime_type: str | None = None,
        file_id: str | None = None,
    ) -> str:
        if not file_id:
            file_id = ArtifactService.generate_file_id(file_bytes, filename)

        s3_key = ArtifactService.build_artifact_id(company_id, file_type, file_id, filename)

        extra_args: dict[str, Any] = {}
        if mime_type:
            extra_args["ContentType"] = mime_type

        try:
            async with self._client() as s3:
                await s3.put_object(
                    Bucket=self._bucket_name,
                    Key=s3_key,
                    Body=file_bytes,
                    **extra_args,
                )

            logger.info(
                "s3.file.uploaded",
                s3_key=s3_key,
                company_id=company_id,
                file_type=file_type,
                size_bytes=len(file_bytes),
            )
            return s3_key

        except Exception as e:
            logger.exception(
                "s3.file.upload_failed",
                s3_key=s3_key,
                company_id=company_id,
                error=str(e),
            )
            raise S3StorageError(f"Failed to upload file to S3: {e}") from e

    async def download_file(self, s3_key: str) -> bytes:
        try:
            async with self._client() as s3:
                response = await s3.get_object(Bucket=self._bucket_name, Key=s3_key)
                file_bytes = await response["Body"].read()

            logger.debug(
                "s3.file.downloaded",
                s3_key=s3_key,
                size_bytes=len(file_bytes),
            )
            return file_bytes

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "NoSuchKey":
                logger.warning("s3.file.not_found", s3_key=s3_key)
                raise S3FileNotFoundError(f"File not found in S3: {s3_key}") from e
            raise
        except Exception as e:
            logger.exception("s3.file.download_failed", s3_key=s3_key, error=str(e))
            raise S3StorageError(f"Failed to download file from S3: {e}") from e

    async def delete_file(self, s3_key: str) -> None:
        try:
            async with self._client() as s3:
                await s3.delete_object(Bucket=self._bucket_name, Key=s3_key)

            logger.info("s3.file.deleted", s3_key=s3_key)

        except Exception as e:
            logger.exception("s3.file.delete_failed", s3_key=s3_key, error=str(e))
            raise S3StorageError(f"Failed to delete file from S3: {e}") from e

    async def get_presigned_url(self, s3_key: str, expiration: int = 3600) -> str:
        try:
            async with self._client() as s3:
                url = await s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self._bucket_name, "Key": s3_key},
                    ExpiresIn=expiration,
                )

            logger.debug("s3.presigned_url.generated", s3_key=s3_key, expiration=expiration)
            return url

        except Exception as e:
            logger.exception("s3.presigned_url.failed", s3_key=s3_key, error=str(e))
            raise S3StorageError(f"Failed to generate presigned URL: {e}") from e

    async def get_presigned_put_url(
        self,
        s3_key: str,
        content_type: str,
        expiration: int = 3600,
    ) -> str:
        try:
            async with self._client() as s3:
                url = await s3.generate_presigned_url(
                    "put_object",
                    Params={
                        "Bucket": self._bucket_name,
                        "Key": s3_key,
                        "ContentType": content_type,
                    },
                    ExpiresIn=expiration,
                )

            logger.debug(
                "s3.presigned_put_url.generated",
                s3_key=s3_key,
                expiration=expiration,
                content_type=content_type,
            )
            return url

        except Exception as e:
            logger.exception("s3.presigned_put_url.failed", s3_key=s3_key, error=str(e))
            raise S3StorageError(f"Failed to generate presigned PUT URL: {e}") from e
