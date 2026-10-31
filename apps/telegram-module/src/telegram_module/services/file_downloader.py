from __future__ import annotations

import base64
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)

# AICODE-NOTE: Telegram Bot API limits
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB
DOWNLOAD_TIMEOUT_S = 30.0  # 30 seconds for file download
GET_FILE_TIMEOUT_S = 5.0  # 5 seconds for getFile API call
MAX_RETRIES = 3


class TelegramFileDownloadError(RuntimeError):
    """Raised when file download from Telegram fails."""


class TelegramFileDownloader:
    """Downloads files from Telegram Bot API."""

    def __init__(self) -> None:
        self._base_url = "https://api.telegram.org"

    async def download_voice_file(self, bot_token: str, file_id: str) -> tuple[bytes, dict[str, Any]]:
        """Download voice file from Telegram and return bytes with metadata.

        Args:
            bot_token: Telegram bot token
            file_id: Telegram file_id from voice message

        Returns:
            Tuple of (audio_bytes, metadata_dict) where metadata contains:
            - mime_type: str (usually "audio/ogg")
            - duration: int | None
            - file_size: int | None

        Raises:
            TelegramFileDownloadError: If download fails after retries
        """
        # Get file path first
        file_path = await self._get_file_path_with_retry(bot_token, file_id)

        # Download file with retries
        audio_bytes = await self._download_file_with_retry(bot_token, file_path)

        # Get metadata from voice object (we'll need to pass it separately)
        # For now, return default metadata
        metadata: dict[str, Any] = {
            "mime_type": "audio/ogg",  # Telegram voice is usually OGG
            "duration": None,
            "file_size": len(audio_bytes),
        }

        return audio_bytes, metadata

    async def download_bot_file(self, bot_token: str, file_id: str) -> bytes:
        """Download arbitrary Telegram-hosted file bytes (photo, document, etc.)."""
        file_path = await self._get_file_path_with_retry(bot_token, file_id)
        return await self._download_file_with_retry(bot_token, file_path)

    async def _get_file_path_with_retry(self, bot_token: str, file_id: str) -> str:
        """Get file path from Telegram API with retries.

        Args:
            bot_token: Telegram bot token
            file_id: Telegram file_id

        Returns:
            File path for downloading

        Raises:
            TelegramFileDownloadError: If all retries fail
        """
        url = f"{self._base_url}/bot{bot_token}/getFile"
        params = {"file_id": file_id}

        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=GET_FILE_TIMEOUT_S) as client:
                    response = await client.get(url, params=params)
                    response.raise_for_status()

                    data = response.json()
                    if not data.get("ok"):
                        error_description = data.get("description", "Unknown error")
                        raise TelegramFileDownloadError(f"Telegram API error: {error_description}")

                    result = data.get("result", {})
                    file_path = result.get("file_path")
                    if not file_path:
                        raise TelegramFileDownloadError("Telegram API returned no file_path")

                    # Check file size if available
                    file_size = result.get("file_size")
                    if file_size and file_size > MAX_FILE_SIZE_BYTES:
                        raise TelegramFileDownloadError(f"File size {file_size} exceeds limit {MAX_FILE_SIZE_BYTES}")

                    log.debug(
                        "telegram.file.path_retrieved",
                        file_id=file_id,
                        file_path=file_path,
                        file_size=file_size,
                        attempt=attempt,
                    )

                    return file_path

            except httpx.HTTPError as e:
                last_error = e
                log.warning(
                    "telegram.file.get_path_failed",
                    file_id=file_id,
                    attempt=attempt,
                    max_retries=MAX_RETRIES,
                    error=str(e),
                )
                if attempt < MAX_RETRIES:
                    continue
            except TelegramFileDownloadError:
                # Don't retry on business logic errors
                raise
            except Exception as e:
                last_error = e
                log.warning(
                    "telegram.file.get_path_unexpected_error",
                    file_id=file_id,
                    attempt=attempt,
                    error=str(e),
                )
                if attempt < MAX_RETRIES:
                    continue

        raise TelegramFileDownloadError(
            f"Failed to get file path after {MAX_RETRIES} attempts: {last_error}"
        ) from last_error

    async def _download_file_with_retry(self, bot_token: str, file_path: str) -> bytes:
        """Download file from Telegram with retries.

        Args:
            bot_token: Telegram bot token
            file_path: File path from getFile API

        Returns:
            File bytes

        Raises:
            TelegramFileDownloadError: If download fails after retries
        """
        url = f"{self._base_url}/file/bot{bot_token}/{file_path}"

        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT_S) as client:
                    response = await client.get(url)
                    response.raise_for_status()

                    audio_bytes = response.content

                    # Check size after download
                    if len(audio_bytes) > MAX_FILE_SIZE_BYTES:
                        raise TelegramFileDownloadError(
                            f"Downloaded file size {len(audio_bytes)} exceeds limit {MAX_FILE_SIZE_BYTES}"
                        )

                    log.debug(
                        "telegram.file.downloaded",
                        file_path=file_path,
                        size_bytes=len(audio_bytes),
                        attempt=attempt,
                    )

                    return audio_bytes

            except httpx.HTTPError as e:
                last_error = e
                log.warning(
                    "telegram.file.download_failed",
                    file_path=file_path,
                    attempt=attempt,
                    max_retries=MAX_RETRIES,
                    error=str(e),
                )
                if attempt < MAX_RETRIES:
                    continue
            except TelegramFileDownloadError:
                # Don't retry on business logic errors
                raise
            except Exception as e:
                last_error = e
                log.warning(
                    "telegram.file.download_unexpected_error",
                    file_path=file_path,
                    attempt=attempt,
                    error=str(e),
                )
                if attempt < MAX_RETRIES:
                    continue

        raise TelegramFileDownloadError(
            f"Failed to download file after {MAX_RETRIES} attempts: {last_error}"
        ) from last_error

    @staticmethod
    def encode_to_base64(data: bytes) -> str:
        """Encode bytes to base64 string.

        Args:
            data: Bytes to encode

        Returns:
            Base64 encoded string
        """
        return base64.b64encode(data).decode("utf-8")
