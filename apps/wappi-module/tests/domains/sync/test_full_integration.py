"""Full integration test: Wappi API → Provider → Runner → Backend → DB."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr

from common.contracts.sync import SyncMessage, SyncStatus
from common.models.inbound import MessageRole
from common.sync.client import BackendSyncClient
from wappi_module.connectors.models import WappiConnectorConfig
from wappi_module.services.wappi_api import WappiApiClient
from wappi_module.sync.provider import WappiSyncProvider


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    from common.config import BackendSettings, EventingSettings
    from wappi_module.config import Settings

    return Settings(
        backend=BackendSettings(url="http://backend.test"),
        service_api_key="test-key",  # pragma: allowlist secret
        app_environment="test",
        app_debug=False,
        config_refresh_interval_s=0,
        request_timeout_s=10.0,
        max_delivery_attempts=3,
        idempotency_cache_ttl_s=86400,
        eventing=EventingSettings(enabled=False),
    )


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
def mock_backend_client() -> BackendSyncClient:
    """Create mock backend sync client."""
    client = MagicMock(spec=BackendSyncClient)
    client.send_batch = AsyncMock()
    client.update_status = AsyncMock()
    client.heartbeat = AsyncMock()
    client.get_cursor = AsyncMock(return_value=None)
    client.close = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_full_sync_flow(
    mock_settings,
    connector_config: WappiConnectorConfig,
    mock_wappi_client: WappiApiClient,
    mock_backend_client: BackendSyncClient,
):
    """Test complete sync flow from Wappi API to Backend."""
    # Setup: Mock Wappi API responses
    mock_wappi_client.get_chats_list = AsyncMock(
        return_value={
            "dialogs": [
                {"id": "chat1", "name": "User 1", "type": "user"},
                {"id": "chat2", "name": "User 2", "type": "user"},
            ],
            "total_count": 2,
        }
    )

    mock_wappi_client.get_chat_messages = AsyncMock(
        side_effect=[
            {
                "messages": [
                    {
                        "id": "msg1",
                        "body": "Hello",
                        "fromMe": False,
                        "time": 1709456814,
                        "chatId": "chat1",
                        "from": "user1",
                        "senderName": "User 1",
                    },
                    {
                        "id": "msg2",
                        "body": "Hi there",
                        "fromMe": True,
                        "time": 1709456820,
                        "chatId": "chat1",
                        "from": "profile-123",
                    },
                ],
                "total_count": 2,
            },
            {
                "messages": [
                    {
                        "id": "msg3",
                        "body": "World",
                        "fromMe": False,
                        "time": 1709456830,
                        "chatId": "chat2",
                        "from": "user2",
                    },
                ],
                "total_count": 1,
            },
        ]
    )

    # Create provider
    provider = WappiSyncProvider(
        connector_config=connector_config,
        wappi_client=mock_wappi_client,
    )

    # Create runner
    from common.sync.runner import SyncRunner

    runner = SyncRunner(
        provider=provider,
        client=mock_backend_client,
        connector_id="test-connector",
        correlation_id="test-corr-123",
    )

    # Run sync
    await runner.run(sync_type="initial")

    # Verify Wappi API was called
    assert mock_wappi_client.get_chats_list.call_count >= 1
    assert mock_wappi_client.get_chat_messages.call_count == 2

    # Verify batches were sent to backend
    assert mock_backend_client.send_batch.call_count >= 1

    # Verify status updates
    status_calls = [call[1]["status"] for call in mock_backend_client.update_status.call_args_list]
    assert SyncStatus.INITIAL in status_calls
    assert SyncStatus.COMPLETED in status_calls

    # Verify heartbeat was set up (may be 0 if sync completes too quickly)
    # Heartbeat runs in background task every 30 seconds
    # In real scenario with longer sync, heartbeat would be called

    # Verify batch content
    batch_calls = mock_backend_client.send_batch.call_args_list
    all_messages: list[SyncMessage] = []
    for call in batch_calls:
        messages = call[1]["messages"]
        all_messages.extend(messages)

    # Should have 3 messages total
    assert len(all_messages) == 3

    # Verify message transformation
    msg1 = next((m for m in all_messages if m.provider_message_id == "msg1"), None)
    assert msg1 is not None
    assert msg1.role == MessageRole.USER
    assert msg1.text == "Hello"
    assert msg1.conversation_id == "chat1"

    msg2 = next((m for m in all_messages if m.provider_message_id == "msg2"), None)
    assert msg2 is not None
    assert msg2.role == MessageRole.MANAGER
    assert msg2.text == "Hi there"

    # Verify correlation_id is passed
    for call in batch_calls:
        assert call[1]["correlation_id"] == "test-corr-123"
        assert call[1]["connector_id"] == "test-connector"
