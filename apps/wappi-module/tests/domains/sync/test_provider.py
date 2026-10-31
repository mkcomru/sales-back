"""Tests for WappiSyncProvider."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr

from common.contracts.sync import SyncMessage
from common.models.inbound import MessageRole
from wappi_module.connectors.models import WappiConnectorConfig
from wappi_module.services.wappi_api import WappiApiClient, WappiApiError
from wappi_module.sync.provider import WappiSyncProvider


@pytest.fixture
def connector_config() -> WappiConnectorConfig:
    """Create test connector config."""
    return WappiConnectorConfig(
        connector_id="test-connector",
        company_id="123",
        wappi_token=SecretStr("test-token"),
        wappi_profile_id="profile-123",
        channel_type="telegram",
        metadata={},
    )


@pytest.fixture
def mock_wappi_client() -> WappiApiClient:
    """Create mock Wappi API client."""
    return MagicMock(spec=WappiApiClient)


@pytest.fixture
def provider(connector_config: WappiConnectorConfig, mock_wappi_client: WappiApiClient) -> WappiSyncProvider:
    """Create WappiSyncProvider instance."""
    return WappiSyncProvider(
        connector_config=connector_config,
        wappi_client=mock_wappi_client,
    )


@pytest.mark.asyncio
async def test_fetch_dialogs_success(provider: WappiSyncProvider, mock_wappi_client: WappiApiClient):
    """Test successful dialog fetching."""
    mock_wappi_client.get_chats_list = AsyncMock(
        return_value={
            "dialogs": [
                {"id": "chat1", "name": "Chat 1", "type": "user"},
                {"id": "chat2", "name": "Chat 2", "type": "channel"},
            ],
            "total_count": 2,
        }
    )

    dialogs = []
    async for dialog in provider.fetch_dialogs():
        dialogs.append(dialog)

    assert len(dialogs) == 2
    assert dialogs[0].id == "chat1"
    assert dialogs[0].name == "Chat 1"
    assert dialogs[1].id == "chat2"
    assert dialogs[1].name == "Chat 2"

    mock_wappi_client.get_chats_list.assert_called_once()
    call_kwargs = mock_wappi_client.get_chats_list.call_args[1]
    assert call_kwargs["wappi_token"] == "test-token"
    assert call_kwargs["profile_id"] == "profile-123"
    assert call_kwargs["limit"] == 200


@pytest.mark.asyncio
async def test_fetch_dialogs_with_cursor(provider: WappiSyncProvider, mock_wappi_client: WappiApiClient):
    """Test dialog fetching with cursor (pagination)."""
    mock_wappi_client.get_chats_list = AsyncMock(
        side_effect=[
            {
                "dialogs": [{"id": "chat1", "name": "Chat 1"}],
                "total_count": 3,
            },
            {
                "dialogs": [{"id": "chat2", "name": "Chat 2"}],
                "total_count": 3,
            },
            {
                "dialogs": [{"id": "chat3", "name": "Chat 3"}],
                "total_count": 3,
            },
        ]
    )

    dialogs = []
    async for dialog in provider.fetch_dialogs(cursor="0"):
        dialogs.append(dialog)
        if len(dialogs) >= 3:
            break

    assert len(dialogs) >= 1
    assert mock_wappi_client.get_chats_list.call_count >= 1


@pytest.mark.asyncio
async def test_fetch_dialogs_empty(provider: WappiSyncProvider, mock_wappi_client: WappiApiClient):
    """Test dialog fetching with empty result."""
    mock_wappi_client.get_chats_list = AsyncMock(
        return_value={
            "dialogs": [],
            "total_count": 0,
        }
    )

    dialogs = []
    async for dialog in provider.fetch_dialogs():
        dialogs.append(dialog)

    assert len(dialogs) == 0


@pytest.mark.asyncio
async def test_fetch_messages_success(provider: WappiSyncProvider, mock_wappi_client: WappiApiClient):
    """Test successful message fetching."""
    mock_wappi_client.get_chat_messages = AsyncMock(
        return_value={
            "messages": [
                {
                    "id": "msg1",
                    "body": "Hello",
                    "fromMe": False,
                    "time": 1709456814,
                    "chatId": "chat123",
                    "from": "user1",
                    "senderName": "User 1",
                },
                {
                    "id": "msg2",
                    "body": "World",
                    "fromMe": True,
                    "time": 1709456820,
                    "chatId": "chat123",
                    "from": "profile-123",
                },
            ],
            "total_count": 2,
        }
    )

    messages = []
    async for msg in provider.fetch_messages("chat123"):
        messages.append(msg)

    assert len(messages) == 2
    assert messages[0]["id"] == "msg1"
    assert messages[1]["id"] == "msg2"

    mock_wappi_client.get_chat_messages.assert_called_once()
    call_kwargs = mock_wappi_client.get_chat_messages.call_args[1]
    assert call_kwargs["wappi_token"] == "test-token"
    assert call_kwargs["profile_id"] == "profile-123"
    assert call_kwargs["chat_id"] == "chat123"
    assert call_kwargs["limit"] == 100


@pytest.mark.asyncio
async def test_fetch_messages_with_since(provider: WappiSyncProvider, mock_wappi_client: WappiApiClient):
    """Test message fetching with since date (catchup)."""
    mock_wappi_client.get_chat_messages = AsyncMock(
        return_value={
            "messages": [
                {
                    "id": "msg1",
                    "body": "Hello",
                    "fromMe": False,
                    "time": 1709456814,
                    "chatId": "chat123",
                    "from": "user1",
                },
            ],
            "total_count": 1,
        }
    )

    since = "2024-03-01T12:00:00"
    messages = []
    async for msg in provider.fetch_messages("chat123", since=since):
        messages.append(msg)

    assert len(messages) == 1
    call_kwargs = mock_wappi_client.get_chat_messages.call_args[1]
    assert call_kwargs["order"] == "asc"


@pytest.mark.asyncio
async def test_fetch_messages_pagination(provider: WappiSyncProvider, mock_wappi_client: WappiApiClient):
    """Test message fetching with pagination."""
    mock_wappi_client.get_chat_messages = AsyncMock(
        side_effect=[
            {
                "messages": [
                    {
                        "id": f"msg{i}",
                        "body": f"Message {i}",
                        "fromMe": False,
                        "time": 1709456814 + i,
                        "chatId": "chat123",
                        "from": "user1",
                    }
                    for i in range(100)
                ],
                "total_count": 150,
            },
            {
                "messages": [
                    {
                        "id": f"msg{i}",
                        "body": f"Message {i}",
                        "fromMe": False,
                        "time": 1709456814 + i,
                        "chatId": "chat123",
                        "from": "user1",
                    }
                    for i in range(100, 150)
                ],
                "total_count": 150,
            },
        ]
    )

    messages = []
    async for msg in provider.fetch_messages("chat123"):
        messages.append(msg)

    assert len(messages) == 150
    assert mock_wappi_client.get_chat_messages.call_count == 2


@pytest.mark.asyncio
async def test_transform_message_user(provider: WappiSyncProvider):
    """Test message transformation for user message."""
    raw = {
        "id": "msg1",
        "body": "Hello",
        "fromMe": False,
        "time": 1709456814,
        "chatId": "chat123",
        "from": "user1",
        "senderName": "User 1",
    }

    sync_msg = await provider.transform_message(raw)

    assert isinstance(sync_msg, SyncMessage)
    assert sync_msg.conversation_id == "chat123"
    assert sync_msg.user_id == "user1"
    assert sync_msg.text == "Hello"
    assert sync_msg.role == MessageRole.USER
    assert sync_msg.provider_message_id == "msg1"
    assert sync_msg.sender_name == "User 1"


@pytest.mark.asyncio
async def test_transform_message_assistant(provider: WappiSyncProvider):
    """Test message transformation for manager message (fromMe=True)."""
    raw = {
        "id": "msg2",
        "body": "Hi there",
        "fromMe": True,
        "time": 1709456820,
        "chatId": "chat123",
        "from": "profile-123",
    }

    sync_msg = await provider.transform_message(raw)

    assert isinstance(sync_msg, SyncMessage)
    assert sync_msg.role == MessageRole.MANAGER
    assert sync_msg.user_id == "profile-123"


@pytest.mark.asyncio
async def test_get_rate_limit(provider: WappiSyncProvider):
    """Test rate limit getter."""
    rate = provider.get_rate_limit()
    assert rate == 2.0


@pytest.mark.asyncio
async def test_fetch_dialogs_handles_errors(provider: WappiSyncProvider, mock_wappi_client: WappiApiClient):
    """Test that errors in fetch_dialogs are properly raised."""
    mock_wappi_client.get_chats_list = AsyncMock(side_effect=WappiApiError("API error"))

    with pytest.raises(WappiApiError):
        async for _ in provider.fetch_dialogs():
            pass


@pytest.mark.asyncio
async def test_fetch_messages_handles_errors(provider: WappiSyncProvider, mock_wappi_client: WappiApiClient):
    """Test that errors in fetch_messages are properly raised."""
    mock_wappi_client.get_chat_messages = AsyncMock(side_effect=WappiApiError("API error"))

    with pytest.raises(WappiApiError):
        async for _ in provider.fetch_messages("chat123"):
            pass
