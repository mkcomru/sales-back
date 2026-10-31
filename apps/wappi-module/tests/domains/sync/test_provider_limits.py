"""Tests for WappiSyncProvider message and dialog limits."""

from unittest.mock import AsyncMock

import pytest

from wappi_module.connectors.models import WappiConnectorConfig
from wappi_module.sync.provider import WappiSyncProvider


class TestFetchMessagesWithLimit:
    """Tests for WappiSyncProvider.fetch_messages with max_messages parameter."""

    @pytest.fixture
    def connector_config(self):
        """Create test connector config."""
        from pydantic import SecretStr

        return WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("test-token"),
            wappi_profile_id="test-profile",
            channel_type="whatsapp",
            metadata={},
        )

    @pytest.fixture
    def mock_wappi_client(self):
        """Mock WappiApiClient."""
        from unittest.mock import MagicMock

        client = MagicMock()

        # Mock get_chat_messages to return paginated responses
        # Each call returns the next page based on offset
        async def mock_get_chat_messages(*args, **kwargs):
            offset = kwargs.get("offset", 0)
            # First page: 10 messages (offset 0)
            if offset == 0:
                return {
                    "messages": [{"id": f"msg-{i}", "type": "text", "body": f"Message {i}"} for i in range(10)],
                    "total_count": 25,
                }
            # Second page: 10 more messages (offset 10)
            elif offset == 10:
                return {
                    "messages": [{"id": f"msg-{i}", "type": "text", "body": f"Message {i}"} for i in range(10, 20)],
                    "total_count": 25,
                }
            # Third page: 5 messages (offset 20)
            else:
                return {
                    "messages": [{"id": f"msg-{i}", "type": "text", "body": f"Message {i}"} for i in range(20, 25)],
                    "total_count": 25,
                }

        client.get_chat_messages = AsyncMock(side_effect=mock_get_chat_messages)
        return client

    @pytest.fixture
    def mock_backend_client(self):
        """Mock WappiBackendClient."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_fetch_messages_without_limit(
        self,
        connector_config,
        mock_wappi_client,
        mock_backend_client,
    ):
        """Test fetching all messages without limit."""
        provider = WappiSyncProvider(
            connector_config=connector_config,
            wappi_client=mock_wappi_client,
            backend_client=mock_backend_client,
        )

        messages = []
        async for msg in provider.fetch_messages(dialog_id="dialog-1", max_messages=None):
            messages.append(msg)

        # Should fetch all 25 messages
        assert len(messages) == 25

    @pytest.mark.asyncio
    async def test_fetch_messages_with_limit_10(
        self,
        connector_config,
        mock_wappi_client,
        mock_backend_client,
    ):
        """Test fetching messages with limit of 10."""
        provider = WappiSyncProvider(
            connector_config=connector_config,
            wappi_client=mock_wappi_client,
            backend_client=mock_backend_client,
        )

        messages = []
        async for msg in provider.fetch_messages(dialog_id="dialog-1", max_messages=10):
            messages.append(msg)

        # Should fetch exactly 10 messages
        assert len(messages) == 10

    @pytest.mark.asyncio
    async def test_fetch_messages_with_limit_15(
        self,
        connector_config,
        mock_wappi_client,
        mock_backend_client,
    ):
        """Test fetching messages with limit of 15 (crosses page boundary)."""
        provider = WappiSyncProvider(
            connector_config=connector_config,
            wappi_client=mock_wappi_client,
            backend_client=mock_backend_client,
        )

        messages = []
        async for msg in provider.fetch_messages(dialog_id="dialog-1", max_messages=15):
            messages.append(msg)

        # Should fetch exactly 15 messages (10 from first page + 5 from second)
        assert len(messages) == 15

    @pytest.mark.asyncio
    async def test_fetch_messages_with_limit_greater_than_total(
        self,
        connector_config,
        mock_wappi_client,
        mock_backend_client,
    ):
        """Test fetching messages with limit greater than total available."""
        provider = WappiSyncProvider(
            connector_config=connector_config,
            wappi_client=mock_wappi_client,
            backend_client=mock_backend_client,
        )

        messages = []
        async for msg in provider.fetch_messages(dialog_id="dialog-1", max_messages=100):
            messages.append(msg)

        # Should fetch all 25 messages (stops when no more available)
        assert len(messages) == 25


class TestFetchDialogsWithLimit:
    """Tests for WappiSyncProvider.fetch_dialogs with max_dialogs parameter."""

    @pytest.fixture
    def connector_config(self):
        """Create test connector config."""
        from pydantic import SecretStr

        return WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("test-token"),
            wappi_profile_id="test-profile",
            channel_type="whatsapp",
            metadata={},
        )

    @pytest.fixture
    def mock_wappi_client(self):
        """Mock WappiApiClient."""
        from unittest.mock import MagicMock

        client = MagicMock()

        # Mock get_chats_list to return paginated responses
        # Each call returns the next page based on offset
        async def mock_get_chats_list(*args, **kwargs):
            offset = kwargs.get("offset", 0)
            # First page: 10 dialogs (offset 0)
            if offset == 0:
                return {
                    "dialogs": [
                        {
                            "id": f"dialog-{i}",
                            "name": f"Dialog {i}",
                            "last_message_time": 1234567890 + i,
                        }
                        for i in range(10)
                    ],
                    "total_count": 25,
                }
            # Second page: 10 more dialogs (offset 10)
            elif offset == 10:
                return {
                    "dialogs": [
                        {
                            "id": f"dialog-{i}",
                            "name": f"Dialog {i}",
                            "last_message_time": 1234567890 + i,
                        }
                        for i in range(10, 20)
                    ],
                    "total_count": 25,
                }
            # Third page: 5 dialogs (offset 20)
            else:
                return {
                    "dialogs": [
                        {
                            "id": f"dialog-{i}",
                            "name": f"Dialog {i}",
                            "last_message_time": 1234567890 + i,
                        }
                        for i in range(20, 25)
                    ],
                    "total_count": 25,
                }

        client.get_chats_list = AsyncMock(side_effect=mock_get_chats_list)
        return client

    @pytest.fixture
    def mock_backend_client(self):
        """Mock WappiBackendClient."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_fetch_dialogs_without_limit(
        self,
        connector_config,
        mock_wappi_client,
        mock_backend_client,
    ):
        """Test fetching all dialogs without limit."""
        provider = WappiSyncProvider(
            connector_config=connector_config,
            wappi_client=mock_wappi_client,
            backend_client=mock_backend_client,
        )

        dialogs = []
        async for dialog in provider.fetch_dialogs(max_dialogs=None):
            dialogs.append(dialog)

        # Should fetch all 25 dialogs
        assert len(dialogs) == 25

    @pytest.mark.asyncio
    async def test_fetch_dialogs_with_limit_10(
        self,
        connector_config,
        mock_wappi_client,
        mock_backend_client,
    ):
        """Test fetching dialogs with limit of 10."""
        provider = WappiSyncProvider(
            connector_config=connector_config,
            wappi_client=mock_wappi_client,
            backend_client=mock_backend_client,
        )

        dialogs = []
        async for dialog in provider.fetch_dialogs(max_dialogs=10):
            dialogs.append(dialog)

        # Should fetch exactly 10 dialogs
        assert len(dialogs) == 10

    @pytest.mark.asyncio
    async def test_fetch_dialogs_with_limit_15(
        self,
        connector_config,
        mock_wappi_client,
        mock_backend_client,
    ):
        """Test fetching dialogs with limit of 15 (crosses page boundary)."""
        provider = WappiSyncProvider(
            connector_config=connector_config,
            wappi_client=mock_wappi_client,
            backend_client=mock_backend_client,
        )

        dialogs = []
        async for dialog in provider.fetch_dialogs(max_dialogs=15):
            dialogs.append(dialog)

        # Should fetch exactly 15 dialogs (10 from first page + 5 from second)
        assert len(dialogs) == 15

    @pytest.mark.asyncio
    async def test_fetch_dialogs_with_limit_50(
        self,
        connector_config,
        mock_wappi_client,
        mock_backend_client,
    ):
        """Test fetching dialogs with limit of 50 (default for initial sync)."""
        provider = WappiSyncProvider(
            connector_config=connector_config,
            wappi_client=mock_wappi_client,
            backend_client=mock_backend_client,
        )

        dialogs = []
        async for dialog in provider.fetch_dialogs(max_dialogs=50):
            dialogs.append(dialog)

        # Should fetch all 25 dialogs (limit not reached)
        assert len(dialogs) == 25


class TestSyncProviderLimitMethods:
    """Tests for get_initial_sync_limit and get_initial_dialogs_limit methods."""

    @pytest.fixture
    def connector_config(self):
        """Create test connector config."""
        from pydantic import SecretStr

        return WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("test-token"),
            wappi_profile_id="test-profile",
            channel_type="whatsapp",
            metadata={},
        )

    @pytest.fixture
    def mock_wappi_client(self):
        """Mock WappiApiClient."""
        return AsyncMock()

    @pytest.fixture
    def mock_backend_client(self):
        """Mock WappiBackendClient."""
        return AsyncMock()

    def test_get_initial_sync_limit_default(
        self,
        connector_config,
        mock_wappi_client,
        mock_backend_client,
    ):
        """Test get_initial_sync_limit returns configured value."""
        # Create provider with default settings
        provider = WappiSyncProvider(
            connector_config=connector_config,
            wappi_client=mock_wappi_client,
            backend_client=mock_backend_client,
            initial_sync_messages_limit=50,
        )

        assert provider.get_initial_sync_limit() == 50

    def test_get_initial_dialogs_limit_default(
        self,
        connector_config,
        mock_wappi_client,
        mock_backend_client,
    ):
        """Test get_initial_dialogs_limit returns configured value."""
        # Create provider with default settings
        provider = WappiSyncProvider(
            connector_config=connector_config,
            wappi_client=mock_wappi_client,
            backend_client=mock_backend_client,
            initial_sync_dialogs_limit=50,
        )

        assert provider.get_initial_dialogs_limit() == 50

    def test_get_initial_sync_limit_custom(
        self,
        connector_config,
        mock_wappi_client,
        mock_backend_client,
    ):
        """Test get_initial_sync_limit with custom value."""
        # Create provider with custom limit
        provider = WappiSyncProvider(
            connector_config=connector_config,
            wappi_client=mock_wappi_client,
            backend_client=mock_backend_client,
            initial_sync_messages_limit=100,
        )

        assert provider.get_initial_sync_limit() == 100

    def test_get_initial_dialogs_limit_custom(
        self,
        connector_config,
        mock_wappi_client,
        mock_backend_client,
    ):
        """Test get_initial_dialogs_limit with custom value."""
        # Create provider with custom limit
        provider = WappiSyncProvider(
            connector_config=connector_config,
            wappi_client=mock_wappi_client,
            backend_client=mock_backend_client,
            initial_sync_dialogs_limit=20,
        )

        assert provider.get_initial_dialogs_limit() == 20
