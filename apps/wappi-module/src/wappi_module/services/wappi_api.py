from __future__ import annotations

import base64

import httpx
import structlog

log = structlog.get_logger(__name__)

# Maps channel_type → Wappi API URL prefix
# Telegram: /tapi/..., WhatsApp: /api/..., VK: /vkapi/...
_CHANNEL_API_PREFIX: dict[str, str] = {
    "telegram": "tapi",
    "whatsapp": "api",
    "vk": "vkapi",
}

# Maps channel_type → HTTP method for chats list endpoint
# Telegram uses GET; WhatsApp and VK use POST
_CHANNEL_CHATS_METHOD: dict[str, str] = {
    "telegram": "GET",
    "whatsapp": "POST",
    "vk": "POST",
}


class WappiApiError(RuntimeError):
    """Raised when Wappi API request fails."""


class WappiApiClient:
    """Client for sending messages via Wappi API."""

    def __init__(self, api_base_url: str = "https://wappi.pro") -> None:
        self._base_url = api_base_url.rstrip("/")
        self._timeout = httpx.Timeout(30.0, connect=15.0)

    def _api_prefix(self, channel_type: str) -> str:
        prefix = _CHANNEL_API_PREFIX.get(channel_type.lower())
        if prefix is None:
            raise WappiApiError(f"Unsupported channel_type: '{channel_type}'")
        return prefix

    def _chats_method(self, channel_type: str) -> str:
        method = _CHANNEL_CHATS_METHOD.get(channel_type.lower())
        if method is None:
            raise WappiApiError(f"Unsupported channel_type: '{channel_type}'")
        return method

    async def send_message(
        self, *, wappi_token: str, profile_id: str, recipient: str, body: str, channel_type: str
    ) -> dict:
        prefix = self._api_prefix(channel_type)
        url = f"{self._base_url}/{prefix}/async/message/send"
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": wappi_token,
        }
        params = {"profile_id": profile_id}
        payload = {"body": body, "recipient": recipient}

        log.info(
            "wappi.api.sending_request",
            url=url,
            profile_id=profile_id,
            recipient=recipient,
            body_length=len(body),
            full_url=f"{url}?profile_id={profile_id}",
            headers_keys=list(headers.keys()),
            payload=payload,
        )

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload, headers=headers, params=params)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.error(
                "wappi.api.http_error",
                status_code=exc.response.status_code,
                response_text=exc.response.text[:500],
                profile_id=profile_id,
                recipient=recipient,
            )
            raise WappiApiError(f"Wappi API returned {exc.response.status_code}: {exc.response.text[:200]}") from exc
        except httpx.HTTPError as exc:
            log.error(
                "wappi.api.request_failed",
                error=str(exc),
                profile_id=profile_id,
                recipient=recipient,
            )
            raise WappiApiError(f"Failed to send message via Wappi: {exc}") from exc

        result = response.json()
        log.debug("wappi.api.message_sent", profile_id=profile_id, recipient=recipient, response=result)
        return result

    async def _send_media(
        self,
        *,
        wappi_token: str,
        profile_id: str,
        recipient: str,
        file_bytes: bytes,
        channel_type: str,
        media_path: str,
        caption: str | None,
        filename: str | None,
    ) -> dict:
        if "telegram" in channel_type.lower():
            url = f"{self._base_url}/tapi/sync/message/{media_path}/send"
        else:
            url = f"{self._base_url}/api/sync/message/{media_path}/send"

        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": wappi_token,
        }
        params = {"profile_id": profile_id}
        payload: dict = {
            "recipient": recipient,
            "b64_file": base64.b64encode(file_bytes).decode(),
        }
        if caption is not None:
            payload["caption"] = caption
        if filename is not None:
            payload["file_name"] = filename

        log.debug(
            "wappi.api.sending_media",
            url=url,
            profile_id=profile_id,
            recipient=recipient,
            media_path=media_path,
            file_size=len(file_bytes),
        )

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload, headers=headers, params=params)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.error(
                "wappi.api.media_http_error",
                status_code=exc.response.status_code,
                response_text=exc.response.text[:500],
                profile_id=profile_id,
                recipient=recipient,
                media_path=media_path,
            )
            raise WappiApiError(f"Wappi API returned {exc.response.status_code}: {exc.response.text[:200]}") from exc
        except httpx.HTTPError as exc:
            log.error(
                "wappi.api.media_request_failed",
                error=str(exc),
                profile_id=profile_id,
                recipient=recipient,
                media_path=media_path,
            )
            raise WappiApiError(f"Failed to send media via Wappi: {exc}") from exc

        result = response.json()
        log.debug("wappi.api.media_sent", profile_id=profile_id, recipient=recipient, media_path=media_path)
        return result

    async def send_image(
        self,
        *,
        wappi_token: str,
        profile_id: str,
        recipient: str,
        file_bytes: bytes,
        channel_type: str,
        caption: str | None = None,
    ) -> dict:
        return await self._send_media(
            wappi_token=wappi_token,
            profile_id=profile_id,
            recipient=recipient,
            file_bytes=file_bytes,
            channel_type=channel_type,
            media_path="img",
            caption=caption,
            filename=None,
        )

    async def send_audio(
        self,
        *,
        wappi_token: str,
        profile_id: str,
        recipient: str,
        file_bytes: bytes,
        channel_type: str,
        caption: str | None = None,
    ) -> dict:
        return await self._send_media(
            wappi_token=wappi_token,
            profile_id=profile_id,
            recipient=recipient,
            file_bytes=file_bytes,
            channel_type=channel_type,
            media_path="audio",
            caption=caption,
            filename=None,
        )

    async def send_video(
        self,
        *,
        wappi_token: str,
        profile_id: str,
        recipient: str,
        file_bytes: bytes,
        channel_type: str,
        filename: str,
        caption: str | None = None,
    ) -> dict:
        return await self._send_media(
            wappi_token=wappi_token,
            profile_id=profile_id,
            recipient=recipient,
            file_bytes=file_bytes,
            channel_type=channel_type,
            media_path="video",
            caption=caption,
            filename=filename,
        )

    async def send_document(
        self,
        *,
        wappi_token: str,
        profile_id: str,
        recipient: str,
        file_bytes: bytes,
        channel_type: str,
        filename: str,
        caption: str | None = None,
    ) -> dict:
        return await self._send_media(
            wappi_token=wappi_token,
            profile_id=profile_id,
            recipient=recipient,
            file_bytes=file_bytes,
            channel_type=channel_type,
            media_path="document",
            caption=caption,
            filename=filename,
        )

    async def get_chats_list(
        self,
        wappi_token: str,
        profile_id: str,
        *,
        channel_type: str = "telegram",
        limit: int | None = None,
        offset: int | None = None,
        show_all: bool = False,
    ) -> dict:
        """
        Get list of chats from Wappi API.

        Returns:
            {
                "status": "done",
                "dialogs": [{"id": "1645157187", "name": "...", ...}],
                "total_count": 639
            }
        """
        prefix = self._api_prefix(channel_type)
        method = self._chats_method(channel_type)
        url = f"{self._base_url}/{prefix}/sync/chats/get"

        # AICODE-NOTE: Минимальный набор параметров - некоторые аккаунты
        # не поддерживают все параметры и возвращают 500
        params: dict[str, str | int] = {"profile_id": profile_id}
        if limit is not None:
            params["limit"] = limit
        if offset is not None and offset > 0:
            params["offset"] = offset
        if show_all:
            params["show_all"] = "true"

        headers = {"Authorization": wappi_token}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                log.debug(
                    "wappi.api.chats_list_request",
                    url=url,
                    method=method,
                    params=params,
                    channel_type=channel_type,
                )
                if method == "POST":
                    response = await client.post(url, params=params, headers=headers, json={})
                else:
                    response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            response_text = exc.response.text[:500] if exc.response.text else ""
            log.error(
                "wappi.api.chats_list_http_error",
                status_code=exc.response.status_code,
                error=str(exc),
                response_text=response_text,
                channel_type=channel_type,
            )
            if "wrong platform" in response_text.lower():
                other = "telegram" if "whatsapp" in channel_type.lower() else "whatsapp"
                raise WappiApiError(
                    f"Wrong platform: profile_id {profile_id} is a {other} profile, "
                    f"but connector uses channel_type={channel_type}. "
                    f"Fix connector config to match the Wappi profile."
                ) from exc
            raise WappiApiError(f"Failed to fetch chats: {exc}") from exc
        except httpx.HTTPError as exc:
            log.error("wappi.api.chats_list_failed", error=str(exc), channel_type=channel_type)
            raise WappiApiError(f"Failed to fetch chats: {exc}") from exc

        return response.json()

    async def get_chat_messages(
        self,
        wappi_token: str,
        profile_id: str,
        chat_id: str | int,
        *,
        channel_type: str = "telegram",
        limit: int = 100,
        offset: int = 0,
        order: str = "desc",
    ) -> dict:
        """
        Get messages from a chat.

        Returns:
            {
                "status": "done",
                "messages": [
                    {
                        "id": "2910",
                        "fromMe": true,
                        "body": "Текст",
                        "time": 1709456814,
                        "chatId": "89323786",
                        ...
                    }
                ],
                "total_count": 2
            }
        """
        prefix = self._api_prefix(channel_type)
        url = f"{self._base_url}/{prefix}/sync/messages/get"

        params = {
            "profile_id": profile_id,
            "chat_id": str(chat_id),
            "limit": min(limit, 100),
            "offset": offset,
            "order": order,
        }
        headers = {"Authorization": wappi_token}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                log.debug(
                    "wappi.api.messages_request",
                    url=url,
                    channel_type=channel_type,
                    chat_id=chat_id,
                )
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            log.error("wappi.api.messages_failed", chat_id=chat_id, error=str(exc), channel_type=channel_type)
            raise WappiApiError(f"Failed to fetch messages: {exc}") from exc

        return response.json()

    async def download_media(
        self,
        wappi_token: str,
        profile_id: str,
        message_id: str,
        channel_type: str,
    ) -> dict:
        """Download media file from message.

        Returns:
            {
                "status": "done",
                "file_link": "https://...",  # For Telegram and newer WhatsApp
                "file_b64": "base64...",  # For older WhatsApp messages
                "media_type": "image|video|voice|document",
                "mime_type": "image/jpeg",
                "file_name": "file.jpg",
                ...
            }

        Raises:
            WappiApiError: If download fails
        """
        prefix = self._api_prefix(channel_type)
        url = f"{self._base_url}/{prefix}/sync/message/media/download"

        params = {"profile_id": profile_id, "message_id": message_id}
        headers = {"Authorization": wappi_token}

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
                log.debug(
                    "wappi.api.media_download_request",
                    url=url,
                    channel_type=channel_type,
                    message_id=message_id,
                )
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            log.error(
                "wappi.api.media_download_failed",
                message_id=message_id,
                error=str(exc),
                channel_type=channel_type,
            )
            raise WappiApiError(f"Failed to download media: {exc}") from exc

        return response.json()
