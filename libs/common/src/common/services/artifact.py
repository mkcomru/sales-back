"""Service for artifact ID generation, parsing, and validation."""

from __future__ import annotations

import hashlib
from pathlib import Path

import structlog
from fastapi import HTTPException, status

from common import FileType

log = structlog.get_logger()


class ArtifactService:
    """Service for working with artifact IDs (S3 keys)."""

    @staticmethod
    def generate_file_id(file_bytes: bytes, filename: str | None = None) -> str:
        """Generate unique file ID based on content hash.

        Args:
            file_bytes: File content
            filename: Optional filename for additional uniqueness

        Returns:
            Hex string file ID (16 characters)
        """
        hasher = hashlib.sha256()
        hasher.update(file_bytes)
        if filename:
            hasher.update(filename.encode("utf-8"))
        return hasher.hexdigest()[:16]

    @staticmethod
    def build_artifact_id(
        company_id: int | str,
        file_type: FileType | str,
        file_id: str,
        filename: str | None = None,
    ) -> str:
        """Build S3 key (artifact_id) from components.

        Args:
            company_id: Company identifier
            file_type: File type (voice, audio, image, video, document)
            file_id: Unique file identifier
            filename: Optional filename for extension extraction

        Returns:
            S3 key string: company_{company_id}/{file_type}/{file_id}.{ext}
        """
        file_type_value = file_type.value if isinstance(file_type, FileType) else file_type

        ext = ""
        if filename:
            path = Path(filename)
            if path.suffix:
                ext = path.suffix.lower()
        else:
            match file_type:
                case FileType.AUDIO | FileType.VOICE:
                    ext = ".mp3"
                case FileType.IMAGE:
                    ext = ".jpg"
                case FileType.VIDEO:
                    ext = ".mp4"
                case FileType.DOCUMENT:
                    ext = ".pdf"

        return f"company_{company_id}/{file_type_value}/{file_id}{ext}"

    @staticmethod
    def parse_artifact_id(artifact_id: str) -> dict[str, str | int]:
        """Parse artifact_id (S3 key) into components.

        Args:
            artifact_id: S3 key in format: company_{id}/{file_type}/{file_id}.{ext}

        Returns:
            Dictionary with keys: company_id, file_type, file_id, extension

        Raises:
            ValueError: If artifact_id format is invalid
        """
        parts = artifact_id.split("/")
        if len(parts) < 3:
            raise ValueError(f"Invalid artifact_id format: {artifact_id}")

        company_part = parts[0]
        if not company_part.startswith("company_"):
            raise ValueError(f"Invalid company prefix in artifact_id: {artifact_id}")

        try:
            company_id = int(company_part.replace("company_", ""))
        except ValueError as e:
            raise ValueError(f"Invalid company_id in artifact_id: {artifact_id}") from e

        file_type = parts[1]
        file_id_with_ext = parts[2]

        path = Path(file_id_with_ext)
        file_id = path.stem
        extension = path.suffix.lower() if path.suffix else ""

        return {
            "company_id": company_id,
            "file_type": file_type,
            "file_id": file_id,
            "extension": extension,
        }

    @staticmethod
    def validate_belongs_to_company(artifact_id: str, company_id: int) -> None:
        """Validate that artifact belongs to the specified company.

        Args:
            artifact_id: S3 key (artifact ID) in format: company_{id}/...
            company_id: Company identifier

        Raises:
            HTTPException: If artifact does not belong to the company
        """
        expected_prefix = f"company_{company_id}/"
        if not artifact_id.startswith(expected_prefix):
            log.warning(
                "artifact.ownership_check_failed",
                artifact_id=artifact_id,
                company_id=company_id,
                expected_prefix=expected_prefix,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Artifact does not belong to this company "
                    f"(got: {artifact_id!r}, expected prefix: {expected_prefix!r})"
                ),
            )
