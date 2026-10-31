"""Wappi sync provider implementation."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import structlog

from common import AudioConversionService, FileType
from common.contracts.sync import SyncMessage
from common.models.inbound import MessageRole
from common.sync.base import BaseSyncProvider, Dialog, RawMessage
from wappi_module.connectors.models import WappiConnectorConfig
from wappi_module.services.backend import WappiBackendClient, WappiBackendClientError
from wappi_module.services.wappi_api import WappiApiClient, WappiApiError

log = structlog.get_logger(__name__)

WAPPI_RATE_LIMIT = 2.0


class WappiSyncProvider(BaseSyncProvider):
    """Wappi-specific sync provider implementation."""

    def __init__(
        self,
        connector_config: WappiConnectorConfig,
        wappi_client: WappiApiClient,
        backend_client: WappiBackendClient | None = None,
        audio_converter: AudioConversionService | None = None,
        initial_sync_messages_limit: int = 50,
        initial_sync_dialogs_limit: int = 20,
    ):
        """Initialize Wappi sync provider.

        Args:
            connector_config: Wappi connector configuration
            wappi_client: Wappi API client
            backend_client: Backend client for uploading media to S3
            audio_converter: Audio converter service for voice messages
            initial_sync_messages_limit: Maximum messages to sync per dialog during initial sync
            initial_sync_dialogs_limit: Maximum dialogs to sync during initial sync
        """
        self._config = connector_config
        self._client = wappi_client
        self._backend_client = backend_client
        self._audio_converter = audio_converter or AudioConversionService()
        self._initial_sync_messages_limit = initial_sync_messages_limit
        self._initial_sync_dialogs_limit = initial_sync_dialogs_limit
        self._wappi_token = connector_config.wappi_token.get_secret_value()
        self._profile_id = connector_config.wappi_profile_id
        self._company_id = int(connector_config.company_id)

    async def fetch_dialogs(self, cursor: str | None = None, max_dialogs: int | None = None) -> AsyncIterator[Dialog]:
        """Fetch list of dialogs from Wappi API.

        Args:
            cursor: Optional cursor for pagination (offset as string)
            max_dialogs: Optional maximum number of dialogs to fetch (for initial sync)

        Yields:
            Dialog objects from Wappi API
        """
        offset = int(cursor) if cursor and cursor.isdigit() else 0
        limit = 200
        fetched_count = 0

        while True:
            try:
                response = await self._client.get_chats_list(
                    wappi_token=self._wappi_token,
                    profile_id=self._profile_id,
                    channel_type=self._config.channel_type,
                    limit=limit,
                    offset=offset,
                    show_all=False,
                )

                dialogs_data = response.get("dialogs", [])
                if not dialogs_data:
                    break

                for dialog_data in dialogs_data:
                    # Check max_dialogs limit
                    if max_dialogs is not None and fetched_count >= max_dialogs:
                        log.debug(
                            "wappi.sync.fetch_dialogs.limit_reached",
                            connector_id=self._config.connector_id,
                            max_dialogs=max_dialogs,
                        )
                        return

                    dialog_id = str(dialog_data.get("id", ""))
                    if not dialog_id:
                        continue

                    # AICODE-NOTE: WhatsApp and Telegram have different response formats
                    # Telegram: {"id": "...", "name": "...", "type": "...", "unread_count": ...}
                    # WhatsApp: {"id": "...", "name": "...", "contact": {...}, "chat": {...}, "isGroup": ...}
                    name = dialog_data.get("name")

                    # Extract dialog type - Telegram has "type", WhatsApp has "isGroup"
                    dialog_type = dialog_data.get("type")
                    if dialog_type is None:
                        # WhatsApp format
                        is_group = dialog_data.get("isGroup", False)
                        dialog_type = "group" if is_group else "user"

                    # Extract unread_count - Telegram has it directly, WhatsApp doesn't provide it
                    unread_count = dialog_data.get("unread_count", 0)

                    yield Dialog(
                        id=dialog_id,
                        name=name,
                        metadata={
                            "type": dialog_type,
                            "unread_count": unread_count,
                        },
                    )
                    fetched_count += 1

                total_count = response.get("total_count", 0)
                if offset + len(dialogs_data) >= total_count:
                    break

                offset += len(dialogs_data)

            except Exception as exc:
                log.exception(
                    "wappi.sync.fetch_dialogs.failed",
                    connector_id=self._config.connector_id,
                    offset=offset,
                    error=str(exc),
                )
                raise

    async def fetch_messages(
        self,
        dialog_id: str,
        cursor: str | None = None,
        since: str | None = None,
        max_messages: int | None = None,
    ) -> AsyncIterator[RawMessage]:
        """Fetch messages from a dialog.

        Args:
            dialog_id: Dialog identifier
            cursor: Optional cursor for pagination (offset as string)
            since: Optional date string for catchup sync (format: YYYY-mm-ddTHH:MM:ss)
            max_messages: Optional maximum number of messages to fetch (for initial sync)

        Yields:
            Raw message dictionaries from Wappi API
        """
        offset = int(cursor) if cursor and cursor.isdigit() else 0
        limit = 100
        fetched_count = 0

        # For catchup sync, we need to fetch messages in ascending order (oldest first)
        # and filter by date. However, Wappi API doesn't support date filtering directly,
        # so we'll fetch all messages and filter client-side if since is provided.
        order = "asc" if since else "desc"
        since_dt: datetime | None = None
        if since:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=UTC)

        while True:
            try:
                response = await self._client.get_chat_messages(
                    wappi_token=self._wappi_token,
                    profile_id=self._profile_id,
                    chat_id=dialog_id,
                    channel_type=self._config.channel_type,
                    limit=limit,
                    offset=offset,
                    order=order,
                )

                messages = response.get("messages", [])
                if not messages:
                    break

                for message in messages:
                    # Check max_messages limit
                    if max_messages is not None and fetched_count >= max_messages:
                        log.debug(
                            "wappi.sync.fetch_messages.limit_reached",
                            connector_id=self._config.connector_id,
                            dialog_id=dialog_id,
                            max_messages=max_messages,
                        )
                        return

                    # Filter by date if since is provided
                    if since_dt is not None:
                        message_time = message.get("time")
                        if message_time:
                            message_dt = datetime.fromtimestamp(float(message_time), tz=UTC)
                            # For ascending order, stop when we reach messages older than since
                            if order == "asc" and message_dt < since_dt:
                                # Messages are in ascending order, so we can stop here
                                return
                            # For descending order, skip messages older than since
                            if order == "desc" and message_dt < since_dt:
                                continue

                    yield message
                    fetched_count += 1

                total_count = response.get("total_count", 0)
                if offset + len(messages) >= total_count:
                    break

                offset += len(messages)

            except Exception as exc:
                log.exception(
                    "wappi.sync.fetch_messages.failed",
                    connector_id=self._config.connector_id,
                    dialog_id=dialog_id,
                    offset=offset,
                    error=str(exc),
                )
                raise

    async def _process_media_sync(self, raw: RawMessage) -> list[str]:
        """Process media files from message and upload to S3.

        Args:
            raw: Raw message dictionary from Wappi API

        Returns:
            List of artifact IDs (S3 keys) for uploaded media
        """
        artifact_ids: list[str] = []
        msg_type = raw.get("type")
        message_id = str(raw.get("id", ""))

        # Check if message has media
        if msg_type not in ("ptt", "image", "video", "document", "audio"):
            return artifact_ids

        # Skip if no backend client available
        if not self._backend_client:
            log.warning(
                "sync.media.no_backend_client",
                message_id=message_id,
                type=msg_type,
            )
            return artifact_ids

        try:
            # Try to get artifact_ids from raw message (already processed)
            if "_artifact_ids" in raw:
                return raw["_artifact_ids"]

            # Get file bytes
            file_bytes: bytes | None = None
            mime_type = "application/octet-stream"
            media_data: dict = {}

            # VK sync API returns URL in s3Info.url (not attachments)
            if self._config.channel_type == "vk":
                direct_url = (raw.get("s3Info") or {}).get("url")
                if direct_url:
                    mime_type = "audio/mp3"
                    try:
                        async with httpx.AsyncClient(timeout=30.0) as client:
                            response = await client.get(direct_url)
                            response.raise_for_status()
                            file_bytes = response.content
                            log.debug(
                                "sync.media.downloaded_from_link",
                                message_id=message_id,
                                size_bytes=len(file_bytes),
                            )
                    except Exception as e:
                        log.warning(
                            "sync.media.download_link_failed",
                            message_id=message_id,
                            url=direct_url,
                            error=str(e),
                        )
            else:
                # Download media from Wappi API (Telegram, WhatsApp)
                media_data = await self._client.download_media(
                    wappi_token=self._wappi_token,
                    profile_id=self._profile_id,
                    message_id=message_id,
                    channel_type=self._config.channel_type,
                )

                if media_data.get("status") != "done":
                    log.warning(
                        "sync.media.download_not_ready",
                        message_id=message_id,
                        status=media_data.get("status"),
                    )
                    return artifact_ids

                mime_type = media_data.get("mime_type", "application/octet-stream")

                # Try file_link first (Telegram and newer WhatsApp)
                file_link = media_data.get("file_link")
                if file_link:
                    try:
                        async with httpx.AsyncClient(timeout=30.0) as client:
                            response = await client.get(file_link)
                            response.raise_for_status()
                            file_bytes = response.content
                            log.debug(
                                "sync.media.downloaded_from_link",
                                message_id=message_id,
                                size_bytes=len(file_bytes),
                            )
                    except Exception as e:
                        log.warning(
                            "sync.media.download_link_failed",
                            message_id=message_id,
                            url=file_link,
                            error=str(e),
                        )

                # Fallback to base64 (older WhatsApp)
                if not file_bytes and "file_b64" in media_data:
                    try:
                        file_bytes = base64.b64decode(media_data["file_b64"])
                        log.debug(
                            "sync.media.decoded_base64",
                            message_id=message_id,
                            size_bytes=len(file_bytes),
                        )
                    except Exception as e:
                        log.warning(
                            "sync.media.base64_decode_failed",
                            message_id=message_id,
                            error=str(e),
                        )

            if not file_bytes:
                log.warning("sync.media.no_file_data", message_id=message_id)
                return artifact_ids

            # Determine file type
            media_type = media_data.get("media_type", msg_type)

            log.debug(
                "sync.media.type_detection",
                message_id=message_id,
                msg_type=msg_type,
                media_type=media_type,
                mime_type=mime_type,
                file_name=media_data.get("file_name"),
            )

            # Check for voice messages (ptt)
            # Some providers return type="document" for voice, so also check MIME type
            is_voice = (
                media_type == "ptt"
                or msg_type in ("ptt", "audio")
                or "ogg" in mime_type.lower()
                or (msg_type == "document" and "audio" in mime_type.lower())
            )

            if is_voice:
                file_type = FileType.VOICE
                # Mark in raw message for text generation in transform_message
                raw["_detected_as_voice"] = True
                # Convert voice to MP3 (skip if already MP3)
                if "mp3" not in mime_type.lower():
                    input_format = "ogg" if "ogg" in mime_type.lower() else "mpeg"
                    file_bytes = await self._audio_converter.convert_to_mp3(
                        audio_bytes=file_bytes,
                        input_format=input_format,
                        timeout_s=60.0,
                    )
            elif media_type == "image":
                file_type = FileType.IMAGE
            elif media_type == "video":
                file_type = FileType.VIDEO
            elif media_type == "audio":
                file_type = FileType.AUDIO
            else:
                file_type = FileType.DOCUMENT

            # Upload to S3
            artifact_id = await self._backend_client.upload_artifact(
                file_bytes=file_bytes,
                file_type=file_type,
                company_id=self._company_id,
                connector_id=self._config.connector_id,
            )
            artifact_ids.append(artifact_id)

            log.info(
                "sync.media.uploaded",
                message_id=message_id,
                artifact_id=artifact_id,
                file_type=file_type.value,
                size_bytes=len(file_bytes),
            )

        except WappiBackendClientError as e:
            log.warning(
                "sync.media.upload_failed",
                message_id=message_id,
                error=str(e),
            )
        except WappiApiError as e:
            log.warning(
                "sync.media.download_unavailable",
                message_id=message_id,
                msg_type=msg_type,
                error=str(e),
            )
        except Exception as e:
            log.exception(
                "sync.media.processing_failed",
                message_id=message_id,
                error=str(e),
            )

        return artifact_ids

    async def transform_message(self, raw: RawMessage) -> SyncMessage:
        """Transform Wappi message format to SyncMessage.

        Args:
            raw: Raw message dictionary from Wappi API

        Returns:
            Normalized SyncMessage with artifact_ids for media
        """
        message_id = str(raw.get("id", ""))
        chat_id = str(raw.get("chatId", ""))
        from_me = raw.get("fromMe", False)
        msg_type = raw.get("type", "text")
        timestamp = raw.get("time", 0)
        sender_name = raw.get("senderName") or raw.get("from") or ""

        # Determine role based on fromMe flag
        role = MessageRole.MANAGER if from_me else MessageRole.USER

        # Extract user_id from message
        if from_me:
            user_id = self._profile_id
        else:
            user_id = str(raw.get("from", chat_id))

        # Process media files
        artifact_ids = await self._process_media_sync(raw)

        # Determine text content based on message type
        # For media messages, check if it was detected as voice in _process_media_sync
        detected_as_voice = raw.get("_detected_as_voice", False)

        if detected_as_voice or msg_type == "ptt" or msg_type == "audio":
            text = ""
        elif msg_type == "image":
            text = ""
        elif msg_type == "video":
            text = "[Видео]"
        elif msg_type == "document":
            text = "[Документ]"
        else:
            text = raw.get("body") or ""

        # Convert timestamp to datetime
        message_dt = datetime.fromtimestamp(timestamp, tz=UTC)

        return SyncMessage(
            conversation_id=chat_id,
            user_id=user_id,
            text=text,
            role=role,
            timestamp=message_dt,
            provider_message_id=message_id,
            sender_name=sender_name if sender_name else None,
            sender_username=None,
            sender_phone=None,
            artifact_ids=artifact_ids,
        )

    def get_rate_limit(self) -> float:
        """Get rate limit for Wappi API.

        Returns:
            Rate limit as float (2.0 for 2 req/sec)
        """
        return WAPPI_RATE_LIMIT

    def get_initial_sync_limit(self) -> int | None:
        """Get message limit for initial sync per dialog.

        Returns:
            Maximum number of messages to sync per dialog during initial sync
        """
        return self._initial_sync_messages_limit

    def get_initial_dialogs_limit(self) -> int | None:
        """Get dialog limit for initial sync.

        Returns:
            Maximum number of dialogs to sync during initial sync
        """
        return self._initial_sync_dialogs_limit
