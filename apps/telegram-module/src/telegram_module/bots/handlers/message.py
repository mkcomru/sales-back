from __future__ import annotations

import structlog
from aiogram import Router
from aiogram.types import Document, Message, PhotoSize
from aiogram.utils.serialization import deserialize_telegram_object_to_python

from common import AudioConversionService, FileType
from telegram_module.bots.models import BotConfig
from telegram_module.services.backend import TransportBackendClient, TransportBackendClientError
from telegram_module.services.file_downloader import (
    TelegramFileDownloader,
    TelegramFileDownloadError,
)
from telegram_module.services.sales_agent import BackendInboundClient, BackendInboundClientError

log = structlog.get_logger(__name__)


def _largest_photo_file_id(photo: tuple[PhotoSize, ...]) -> str:
    best = max(
        photo,
        key=lambda p: ((p.file_size or 0), (p.width or 0) * (p.height or 0)),
    )
    return best.file_id


async def _process_photo_message(
    photo: tuple[PhotoSize, ...],
    config: BotConfig,
    file_downloader: TelegramFileDownloader,
    backend_client: TransportBackendClient,
    company_id: int,
) -> str | None:
    try:
        bot_token = config.bot_token.get_secret_value()
        file_id = _largest_photo_file_id(photo)

        log.debug(
            "telegram.photo.download_started",
            connector_id=config.connector_id,
            file_id=file_id,
        )

        image_bytes = await file_downloader.download_bot_file(bot_token, file_id)

        log.debug(
            "telegram.photo.uploading",
            connector_id=config.connector_id,
            file_id=file_id,
            size_bytes=len(image_bytes),
        )

        artifact_id = await backend_client.upload_artifact(
            file_bytes=image_bytes,
            file_type=FileType.IMAGE,
            company_id=company_id,
            connector_id=config.connector_id,
        )

        log.info(
            "telegram.photo.processed",
            connector_id=config.connector_id,
            file_id=file_id,
            artifact_id=artifact_id,
            size_bytes=len(image_bytes),
        )

        return artifact_id
    except (TelegramFileDownloadError, TransportBackendClientError) as e:
        log.warning(
            "telegram.photo.processing_failed",
            connector_id=config.connector_id,
            file_id=photo[0].file_id if photo else None,
            error=str(e),
        )
        return None
    except Exception as e:
        log.exception(
            "telegram.photo.unexpected_error",
            connector_id=config.connector_id,
            file_id=photo[0].file_id if photo else None,
            error=str(e),
        )
        return None


async def _process_image_document_message(
    document: Document,
    config: BotConfig,
    file_downloader: TelegramFileDownloader,
    backend_client: TransportBackendClient,
    company_id: int,
) -> str | None:
    file_id = document.file_id
    if not file_id:
        log.warning(
            "telegram.image_document.missing_file_id",
            connector_id=config.connector_id,
        )
        return None

    try:
        bot_token = config.bot_token.get_secret_value()

        log.debug(
            "telegram.image_document.download_started",
            connector_id=config.connector_id,
            file_id=file_id,
            mime_type=document.mime_type,
        )

        image_bytes = await file_downloader.download_bot_file(bot_token, file_id)

        log.debug(
            "telegram.image_document.uploading",
            connector_id=config.connector_id,
            file_id=file_id,
            size_bytes=len(image_bytes),
        )

        artifact_id = await backend_client.upload_artifact(
            file_bytes=image_bytes,
            file_type=FileType.IMAGE,
            company_id=company_id,
            connector_id=config.connector_id,
        )

        log.info(
            "telegram.image_document.processed",
            connector_id=config.connector_id,
            file_id=file_id,
            artifact_id=artifact_id,
            size_bytes=len(image_bytes),
        )

        return artifact_id
    except (TelegramFileDownloadError, TransportBackendClientError) as e:
        log.warning(
            "telegram.image_document.processing_failed",
            connector_id=config.connector_id,
            file_id=file_id,
            error=str(e),
        )
        return None
    except Exception as e:
        log.exception(
            "telegram.image_document.unexpected_error",
            connector_id=config.connector_id,
            file_id=file_id,
            error=str(e),
        )
        return None


async def _process_voice_message(
    voice,
    config: BotConfig,
    file_downloader: TelegramFileDownloader,
    audio_converter: AudioConversionService,
    backend_client: TransportBackendClient,
    company_id: int,
) -> str | None:
    """Process voice message: download, convert to MP3, upload to Backend.

    Returns:
        artifact_id if successful, None otherwise
    """
    try:
        bot_token = config.bot_token.get_secret_value()
        file_id = voice.file_id

        log.debug(
            "telegram.voice.download_started",
            connector_id=config.connector_id,
            file_id=file_id,
        )

        audio_bytes, _ = await file_downloader.download_voice_file(bot_token, file_id)

        log.debug(
            "telegram.voice.converting",
            connector_id=config.connector_id,
            file_id=file_id,
            size_bytes=len(audio_bytes),
        )

        mp3_bytes = await audio_converter.convert_to_mp3(
            audio_bytes=audio_bytes,
            input_format="ogg",
            timeout_s=60.0,
        )

        log.debug(
            "telegram.voice.uploading",
            connector_id=config.connector_id,
            file_id=file_id,
            size_bytes=len(mp3_bytes),
        )

        artifact_id = await backend_client.upload_artifact(
            file_bytes=mp3_bytes,
            file_type=FileType.VOICE,
            company_id=company_id,
            connector_id=config.connector_id,
        )

        log.info(
            "telegram.voice.processed",
            connector_id=config.connector_id,
            file_id=file_id,
            artifact_id=artifact_id,
            original_size_bytes=len(audio_bytes),
            mp3_size_bytes=len(mp3_bytes),
        )

        return artifact_id
    except (TelegramFileDownloadError, TransportBackendClientError) as e:
        log.warning(
            "telegram.voice.processing_failed",
            connector_id=config.connector_id,
            file_id=voice.file_id if voice else None,
            error=str(e),
        )
        return None
    except Exception as e:
        log.exception(
            "telegram.voice.unexpected_error",
            connector_id=config.connector_id,
            file_id=voice.file_id if voice else None,
            error=str(e),
        )
        return None


async def _process_audio_message(
    audio,
    config: BotConfig,
    file_downloader: TelegramFileDownloader,
    audio_converter: AudioConversionService,
    backend_client: TransportBackendClient,
    company_id: int,
) -> str | None:
    """Process audio message: download, convert to MP3, upload to Backend.

    Returns:
        artifact_id if successful, None otherwise
    """
    try:
        bot_token = config.bot_token.get_secret_value()
        file_id = audio.file_id

        log.debug(
            "telegram.audio.download_started",
            connector_id=config.connector_id,
            file_id=file_id,
        )

        audio_bytes, _ = await file_downloader.download_voice_file(bot_token, file_id)

        log.debug(
            "telegram.audio.converting",
            connector_id=config.connector_id,
            file_id=file_id,
            size_bytes=len(audio_bytes),
        )

        mp3_bytes = await audio_converter.convert_to_mp3(
            audio_bytes=audio_bytes,
            input_format=None,
            timeout_s=60.0,
        )

        log.debug(
            "telegram.audio.uploading",
            connector_id=config.connector_id,
            file_id=file_id,
            size_bytes=len(mp3_bytes),
        )

        artifact_id = await backend_client.upload_artifact(
            file_bytes=mp3_bytes,
            file_type=FileType.AUDIO,
            company_id=company_id,
            connector_id=config.connector_id,
        )

        log.info(
            "telegram.audio.processed",
            connector_id=config.connector_id,
            file_id=file_id,
            artifact_id=artifact_id,
            original_size_bytes=len(audio_bytes),
            mp3_size_bytes=len(mp3_bytes),
        )

        return artifact_id
    except (TelegramFileDownloadError, TransportBackendClientError) as e:
        log.warning(
            "telegram.audio.processing_failed",
            connector_id=config.connector_id,
            file_id=audio.file_id if audio else None,
            error=str(e),
        )
        return None
    except Exception as e:
        log.exception(
            "telegram.audio.unexpected_error",
            connector_id=config.connector_id,
            file_id=audio.file_id if audio else None,
            error=str(e),
        )
        return None


def create_message_handler_router(
    config: BotConfig,
    sales_agent: BackendInboundClient,
    backend_client: TransportBackendClient,
    audio_converter: AudioConversionService,
) -> Router:
    router = Router(name=f"bot_{config.connector_id}")
    file_downloader = TelegramFileDownloader()
    company_id = int(config.company_id)

    @router.message()
    async def message_handler(message: Message) -> None:
        update_dict = {"message": deserialize_telegram_object_to_python(message)}
        message_dict = update_dict["message"]
        artifact_ids: list[str] = []

        if message.photo:
            artifact_id = await _process_photo_message(
                tuple(message.photo),
                config,
                file_downloader,
                backend_client,
                company_id,
            )
            if artifact_id:
                artifact_ids.append(artifact_id)
        elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
            artifact_id = await _process_image_document_message(
                message.document,
                config,
                file_downloader,
                backend_client,
                company_id,
            )
            if artifact_id:
                artifact_ids.append(artifact_id)
        elif message.voice:
            artifact_id = await _process_voice_message(
                message.voice,
                config,
                file_downloader,
                audio_converter,
                backend_client,
                company_id,
            )
            if artifact_id:
                artifact_ids.append(artifact_id)
        elif message.audio:
            artifact_id = await _process_audio_message(
                message.audio,
                config,
                file_downloader,
                audio_converter,
                backend_client,
                company_id,
            )
            if artifact_id:
                artifact_ids.append(artifact_id)

        if artifact_ids:
            message_dict["artifact_ids"] = artifact_ids

        try:
            await sales_agent.forward_update(config.connector_id, config, update_dict)
        except BackendInboundClientError as exc:
            log.error(
                "sales_agent.forward.failed",
                connector_id=config.connector_id,
                company_id=config.company_id,
                error=str(exc),
            )
            raise
        log.debug(
            "telegram.message.handled",
            connector_id=config.connector_id,
            company_id=config.company_id,
            message="Message forwarded to backend (routing decision made by backend)",
        )

    return router
