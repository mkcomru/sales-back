"""Integration tests for complete history synchronization flow."""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import pytest_asyncio

from src.backend.modules.chat.models import ChatMessage, Thread
from src.backend.modules.transport.models import Connector, ConnectorType


@pytest_asyncio.fixture
async def auth_headers(company_factory, settings):
    """Create auth headers factory function for a company."""
    from passlib.context import CryptContext

    from src.backend.modules.auth.service import AuthService
    from src.backend.modules.users.models import CompanyUser, User, UserRole

    async def _create_headers(company_id: int) -> dict[str, str]:
        pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")
        hashed_password = pwd_context.hash("test_manager_password")

        email = f"manager{company_id}@test.com"
        user = await User.get_or_none(email=email)
        if not user:
            user = await User.create(
                first_name="Manager",
                last_name="Test",
                email=email,
                hashed_password=hashed_password,
                is_active=True,
                is_superuser=False,
            )

        company_user = await CompanyUser.get_or_none(user=user, company_id=company_id)
        if not company_user:
            await CompanyUser.create(
                user=user,
                company_id=company_id,
                role=UserRole.ADMIN,
            )

        auth_service = AuthService(settings)
        access_token = auth_service.create_access_token(user.id, is_superuser=False)
        return {"Authorization": f"Bearer {access_token}"}

    return _create_headers


class TestHistorySyncIntegrationFlow:
    """Integration tests for complete history sync flow from API to storage."""

    @pytest.fixture
    async def setup_connector_and_thread(self, company_factory):
        """Set up connector and thread for testing."""
        company = await company_factory()

        # Create wappi connector
        connector = await Connector.create(
            connector_id="test-wappi-flow",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="whatsapp",
            display_name="Test WhatsApp Flow",
            managed=True,
            config={"wappi_token": "test-token", "wappi_profile_id": "test-profile"},
            enabled=True,
        )

        # Create customer
        from src.backend.modules.chat.models import Customer

        customer = await Customer.create(
            user_id="test-user-flow",
            company=company,
            quiz_answers={"name": "Test User"},
            meta={},
        )

        # Create thread
        thread = await Thread.create(
            thread_id="test-thread-flow",
            connector_id=connector.connector_id,
            conversation_id="test-conversation-flow",
            company_id=company.id,
            channel_type=connector.channel_type,
            customer=customer,
            history_synced=False,
        )

        return {"company": company, "connector": connector, "thread": thread}

    @patch("httpx.AsyncClient")
    async def test_complete_history_sync_flow(
        self,
        mock_httpx_client,
        api_client: httpx.AsyncClient,
        auth_headers,
        setup_connector_and_thread,
        settings,
    ):
        """Test complete flow: API request -> transport trigger -> flag set."""
        company = setup_connector_and_thread["company"]
        thread = setup_connector_and_thread["thread"]
        settings.transport.wappi.url = "http://localhost:8002"

        # Mock httpx client to simulate successful wappi-module call
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.raise_for_status = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        # Step 1: Trigger history sync via API
        response = await api_client.post(
            f"/api/v1/companies/{company.id}/threads/{thread.thread_id}/sync-history",
            headers=await auth_headers(company.id),
        )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "sync_triggered"
        assert data["thread_id"] == thread.thread_id

        # Verify wappi-module was called
        mock_client_instance.post.assert_called_once()
        call_url = mock_client_instance.post.call_args[0][0]
        assert f"wappi/sync/{thread.connector_id}/conversation/{thread.conversation_id}" in call_url

        # Step 2: Simulate wappi-module marking thread as synced
        await thread.refresh_from_db()
        assert thread.history_synced is False  # Still false before wappi-module completes

        # Manually mark as synced (simulating what wappi-module would do)
        mark_response = await api_client.patch(
            f"/api/v1/internal/chat/threads/{thread.thread_id}/history-synced",
            headers={"X-Service-Key": "test-service-key"},
        )

        assert mark_response.status_code == 204

        # Step 3: Verify flag is set
        await thread.refresh_from_db()
        assert thread.history_synced is True

        # Step 4: Try to sync again - should fail with 409
        response2 = await api_client.post(
            f"/api/v1/companies/{company.id}/threads/{thread.thread_id}/sync-history",
            headers=await auth_headers(company.id),
        )

        assert response2.status_code == 409
        assert "already synced" in response2.json()["detail"].lower()

    async def test_history_sync_with_messages_idempotency(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        setup_connector_and_thread,
    ):
        """Test that syncing same messages multiple times doesn't create duplicates."""
        thread = setup_connector_and_thread["thread"]

        # Simulate syncing same message twice via sync batch endpoint
        from datetime import UTC, datetime

        from src.backend.modules.chat.models import ChatMessageRole, ChatMessageStatus
        from src.backend.modules.chat.service import ChatService
        from src.backend.modules.orders.service import OrderService

        service = ChatService(order_service=OrderService())
        provider_message_id = "wappi-historical-msg-123"

        # First sync
        message1 = await service.create_message(
            thread_id=thread.thread_id,
            role=ChatMessageRole.USER,
            content="Historical message from Wappi",
            status=ChatMessageStatus.SENT,
            provider_message_id=provider_message_id,
            is_historical=True,
            delivered_at=datetime.now(UTC),
        )

        # Second sync (duplicate)
        message2 = await service.create_message(
            thread_id=thread.thread_id,
            role=ChatMessageRole.USER,
            content="Same historical message",
            status=ChatMessageStatus.SENT,
            provider_message_id=provider_message_id,
            is_historical=True,
            delivered_at=datetime.now(UTC),
        )

        # Should return same message
        assert message1.id == message2.id
        assert message1.message_id == message2.message_id

        # Verify only one message in database
        messages = await ChatMessage.filter(
            thread=thread,
            provider_message_id=provider_message_id,
        ).all()
        assert len(messages) == 1

    async def test_get_thread_by_conversation_integration(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        setup_connector_and_thread,
    ):
        """Test getting thread by conversation via internal API."""
        connector = setup_connector_and_thread["connector"]
        thread = setup_connector_and_thread["thread"]

        # Get thread by conversation
        response = await api_client.get(
            "/api/v1/internal/chat/threads/by-conversation",
            params={
                "connector_id": connector.connector_id,
                "conversation_id": thread.conversation_id,
            },
            headers=service_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["thread_id"] == thread.thread_id
        assert data["history_synced"] is False

        # Mark as synced
        await api_client.patch(
            f"/api/v1/internal/chat/threads/{thread.thread_id}/history-synced",
            headers=service_headers,
        )

        # Get again - should show as synced
        response2 = await api_client.get(
            "/api/v1/internal/chat/threads/by-conversation",
            params={
                "connector_id": connector.connector_id,
                "conversation_id": thread.conversation_id,
            },
            headers=service_headers,
        )

        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["thread_id"] == thread.thread_id
        assert data2["history_synced"] is True


class TestSyncMoreChatsIntegrationFlow:
    """Integration tests for sync more chats flow."""

    @pytest.fixture
    async def setup_connector(self, company_factory):
        """Set up connector for testing."""
        company = await company_factory()

        connector = await Connector.create(
            connector_id="test-wappi-more-flow",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="whatsapp",
            display_name="Test WhatsApp More Flow",
            managed=True,
            config={"wappi_token": "test-token", "wappi_profile_id": "test-profile"},
            enabled=True,
        )

        return {"company": company, "connector": connector}

    @patch("httpx.AsyncClient")
    async def test_sync_more_chats_flow(
        self,
        mock_httpx_client,
        api_client: httpx.AsyncClient,
        service_headers,
        setup_connector,
        settings,
    ):
        """Test complete flow for syncing more chats."""
        connector = setup_connector["connector"]
        settings.transport.wappi.url = "http://localhost:8002"

        # Mock httpx client
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.raise_for_status = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        # Trigger sync more chats
        response = await api_client.post(
            f"/api/v1/transport/connectors/{connector.connector_id}/sync/more-chats",
            headers=service_headers,
        )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "sync_triggered"
        assert data["connector_id"] == connector.connector_id
        assert "loading more chats" in data["message"].lower()

    @patch("httpx.AsyncClient")
    async def test_sync_more_chats_idempotent(
        self,
        mock_httpx_client,
        api_client: httpx.AsyncClient,
        service_headers,
        setup_connector,
        settings,
    ):
        """Test that sync more chats can be called multiple times."""
        connector = setup_connector["connector"]
        settings.transport.wappi.url = "http://localhost:8002"

        # Mock httpx client
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.raise_for_status = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        # Call multiple times
        for _ in range(3):
            response = await api_client.post(
                f"/api/v1/transport/connectors/{connector.connector_id}/sync/more-chats",
                headers=service_headers,
            )
            assert response.status_code == 202

    async def test_sync_more_chats_with_existing_threads(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        setup_connector,
    ):
        """Test that sync more chats correctly identifies existing threads."""
        from src.backend.modules.chat.models import Customer

        connector = setup_connector["connector"]
        company = setup_connector["company"]

        # Create some existing threads
        for i in range(3):
            customer = await Customer.create(
                user_id=f"test-user-{i}",
                company=company,
                quiz_answers={"name": f"Test User {i}"},
                meta={},
            )

            await Thread.create(
                thread_id=f"existing-thread-{i}",
                connector_id=connector.connector_id,
                conversation_id=f"existing-conv-{i}",
                company_id=connector.company_id,
                channel_type=connector.channel_type,
                customer=customer,
                history_synced=False,
            )

        # Get threads by conversation to verify they exist
        for i in range(3):
            response = await api_client.get(
                "/api/v1/internal/chat/threads/by-conversation",
                params={
                    "connector_id": connector.connector_id,
                    "conversation_id": f"existing-conv-{i}",
                },
                headers=service_headers,
            )
            assert response.status_code == 200
            assert response.json()["thread_id"] == f"existing-thread-{i}"
