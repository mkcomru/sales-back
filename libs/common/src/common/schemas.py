"""Common schemas and enums."""

from enum import StrEnum


class FileType(StrEnum):
    """Supported file types for S3 storage."""

    VOICE = "voice"
    AUDIO = "audio"
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
