"""Allowed (extension, content-type) pairs for manager presigned uploads."""

from __future__ import annotations

import pathlib

from common import FileType

from src.backend.modules.s3_storage.exceptions import PresignedUploadPolicyError

_ALLOWED_BY_TYPE: dict[FileType, list[tuple[str, str]]] = {
    FileType.IMAGE: [
        (".jpg", "image/jpeg"),
        (".jpeg", "image/jpeg"),
        (".png", "image/png"),
        (".webp", "image/webp"),
        (".gif", "image/gif"),
    ],
    FileType.AUDIO: [
        (".mp3", "audio/mpeg"),
    ],
    FileType.VIDEO: [
        (".mp4", "video/mp4"),
        (".webm", "video/webm"),
    ],
    FileType.DOCUMENT: [
        (".pdf", "application/pdf"),
        (".txt", "text/plain"),
        (".doc", "application/msword"),
        (".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ],
}


def validate_presigned_upload_policy(file_type: FileType, filename: str, content_type: str) -> None:
    suffix = pathlib.Path(filename).suffix.lower()
    allowed = _ALLOWED_BY_TYPE.get(file_type)
    if not allowed:
        raise PresignedUploadPolicyError(f"Unsupported file_type for presigned upload: {file_type.value}")
    ct = content_type.strip().lower()
    for ext, mime in allowed:
        if suffix == ext and ct == mime.lower():
            return
    raise PresignedUploadPolicyError(
        f"content_type and filename extension do not match allowed set for {file_type.value}: "
        f"{content_type!r} / {filename!r}"
    )
