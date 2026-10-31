from __future__ import annotations

import httpx
import structlog

log = structlog.get_logger(__name__)

API_BASE_URL = "https://api.wazzup24.com/v3"


class WazzupApiError(RuntimeError):
    """Raised when Wazzup API request fails."""


class WazzupApiClient:
    """HTTP client for Wazzup24 API endpoints."""

    def __init__(self, api_base_url: str = API_BASE_URL) -> None:
        self._base_url = api_base_url.rstrip("/")

    async def send_message(
        self,
        *,
        api_key: str,
        channel_id: str,
        chat_id: str,
        chat_type: str,
        text: str,
        crm_message_id: str | None = None,
    ) -> dict:
        url = f"{self._base_url}/message"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "channelId": channel_id,
            "chatId": chat_id,
            "chatType": chat_type,
            "text": text,
        }
        if crm_message_id:
            payload["crmMessageId"] = crm_message_id

        log.debug(
            "wazzup.api.send_message",
            channel_id=channel_id,
            chat_id=chat_id,
            chat_type=chat_type,
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code >= 400:
                    raise WazzupApiError(f"Wazzup API error {response.status_code}: {response.text}")
                return response.json() if response.content else {}
        except httpx.HTTPError as exc:
            raise WazzupApiError(f"Wazzup API request failed: {exc}") from exc

    async def register_webhook(self, *, api_key: str, webhook_uri: str) -> None:
        url = f"{self._base_url}/webhooks"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "webhooksUri": webhook_uri,
            "subscriptions": {"messagesAndStatuses": True},
        }

        log.debug("wazzup.api.register_webhook", webhook_uri=webhook_uri)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.patch(url, headers=headers, json=payload)
                if response.status_code >= 400:
                    raise WazzupApiError(f"Webhook registration failed {response.status_code}: {response.text}")
        except httpx.HTTPError as exc:
            raise WazzupApiError(f"Wazzup webhook registration request failed: {exc}") from exc
