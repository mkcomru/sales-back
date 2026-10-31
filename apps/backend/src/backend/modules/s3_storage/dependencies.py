"""Dependencies for storage module."""

from typing import Annotated

from fastapi import Depends

from common import AudioConversionService

from src.backend.modules.core.dependencies import SettingsDep
from src.backend.modules.s3_storage.s3_client import S3Client


def get_s3_client(settings: SettingsDep) -> S3Client:
    """Get S3 client instance."""
    return S3Client(settings.s3)


_audio_converter: AudioConversionService | None = None


def get_audio_converter() -> AudioConversionService:
    global _audio_converter  # noqa: PLW0603
    if _audio_converter is None:
        _audio_converter = AudioConversionService()
    return _audio_converter


S3ClientDep = Annotated[S3Client, Depends(get_s3_client)]
AudioConverterDep = Annotated[AudioConversionService, Depends(get_audio_converter)]
