"""Tests for thread history synchronization endpoints."""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src.backend.modules.chat.models import Thread
from src.backend.modules.transport.models import Connector, ConnectorType


@pytest.fixture
async def connector(company_factory):
    """Create a wappi connector for testing."""
    company = await company_factory()
    connector = await Connector.create(
        connector_id="test-wappi-connector",
        company=company,
        type=ConnectorType.WAPPI,
        channel_type="whatsapp",
        display_name="Test WhatsApp",
        managed=True,
        config={"wappi_token": "test-token", "wappi_profile_id": "test-profile"},
        enabled=True,
    )
    return connector


@pytest.fixture
async def thread(connector):
    """Create a thread for testing."""
    from src.backend.modules.chat.models import Customer

    await connector.fetch_related("company")
    company = connector.company

    customer = await Customer.create(
        user_id="test_user_thread",
        company=company,
        customer_fields={"name": "Test User"},
        meta={},
    )

    thread = await Thread.create(
        thread_id="test-thread-123",
        connector_id=connector.connector_id,
        conversation_id="test-conversation-456",
        company=company,
        channel_type=connector.channel_type,
        customer=customer,
        history_synced=False,
    )
    # Ensure thread is saved and fields are accessible
    await thread.save()
    return thread


@pytest.fixture
async def manager_headers_for_connector(connector, settings):
    """Create manager headers for connector's company."""
    from passlib.context import CryptContext

    from src.backend.modules.auth.service import AuthService
    from src.backend.modules.users.models import CompanyUser, User, UserRole

    pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")
    hashed_password = pwd_context.hash("test_manager_password")

    user = await User.create(
        first_name="Manager",
        last_name="Test",
        email=f"manager{connector.company_id}@test.com",
        hashed_password=hashed_password,
        is_active=True,
        is_superuser=False,
    )

    await CompanyUser.create(
        user=user,
        company_id=connector.company_id,
        role=UserRole.ADMIN,
    )

    auth_service = AuthService(settings)
    access_token = auth_service.create_access_token(user.id, is_superuser=False)
    return {"Authorization": f"Bearer {access_token}"}


async def create_manager_headers_for_company(company_id: int, settings) -> dict[str, str]:
    """Create manager headers for a specific company."""
    from passlib.context import CryptContext

    from src.backend.modules.auth.service import AuthService
    from src.backend.modules.users.models import CompanyUser, User, UserRole

    pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")
    hashed_password = pwd_context.hash("test_manager_password")

    user = await User.create(
        first_name="Manager",
        last_name="Test",
        email=f"manager{company_id}@test.com",
        hashed_password=hashed_password,
        is_active=True,
        is_superuser=False,
    )

    await CompanyUser.create(
        user=user,
        company_id=company_id,
        role=UserRole.ADMIN,
    )

    auth_service = AuthService(settings)
    access_token = auth_service.create_access_token(user.id, is_superuser=False)
    return {"Authorization": f"Bearer {access_token}"}


class TestSyncThreadHistory:
    """Tests for POST /companies/{company_id}/threads/{thread_id}/sync-history endpoint."""

    async def test_sync_history_without_auth(self, api_client: httpx.AsyncClient, thread: Thread):
        """Test that sync history requires authentication."""
        response = await api_client.post(
            f"/api/v1/companies/{thread.company_id}/threads/{thread.thread_id}/sync-history"
        )
        assert response.status_code == 401

    async def test_sync_history_thread_not_found(
        self,
        api_client: httpx.AsyncClient,
        company_factory,
        settings,
    ):
        """Test sync history with non-existent thread."""
        company = await company_factory()
        headers = await create_manager_headers_for_company(company.id, settings)
        response = await api_client.post(
            f"/api/v1/companies/{company.id}/threads/non-existent-thread/sync-history",
            headers=headers,
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @patch("httpx.AsyncClient")
    async def test_sync_history_wrong_company(
        self,
        mock_httpx_client,
        api_client: httpx.AsyncClient,
        manager_headers_for_connector,
        thread: Thread,
        company_factory,
    ):
        """Test that user cannot sync history for thread from another company."""
        other_company = await company_factory()

        # Mock httpx to prevent actual transport module call
        mock_client_instance = AsyncMock()
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        response = await api_client.post(
            f"/api/v1/companies/{other_company.id}/threads/{thread.thread_id}/sync-history",
            headers=manager_headers_for_connector,
        )
        assert response.status_code == 403
        detail = response.json()["detail"].lower()
        assert "does not belong" in detail or "no access" in detail

    async def test_sync_history_already_synced(
        self,
        api_client: httpx.AsyncClient,
        manager_headers_for_connector,
        thread: Thread,
    ):
        """Test that sync history fails if already synced."""
        # Mark thread as already synced
        thread.history_synced = True
        await thread.save()

        response = await api_client.post(
            f"/api/v1/companies/{thread.company_id}/threads/{thread.thread_id}/sync-history",
            headers=manager_headers_for_connector,
        )
        assert response.status_code == 409
        assert "already synced" in response.json()["detail"].lower()

    async def test_sync_history_missing_connector_id(
        self,
        api_client: httpx.AsyncClient,
        manager_headers_for_connector,
        connector,
    ):
        """Test sync history fails if thread has no connector_id."""
        from src.backend.modules.chat.models import Customer

        await connector.fetch_related("company")
        company = connector.company

        customer = await Customer.create(
            user_id="test_user_no_connector",
            company=company,
            customer_fields={"name": "Test User"},
            meta={},
        )

        thread = await Thread.create(
            thread_id="thread-no-connector",
            connector_id=None,
            conversation_id="conversation-123",
            company=company,
            channel_type=connector.channel_type,
            customer=customer,
            history_synced=False,
        )

        response = await api_client.post(
            f"/api/v1/companies/{thread.company_id}/threads/{thread.thread_id}/sync-history",
            headers=manager_headers_for_connector,
        )
        assert response.status_code == 400
        assert "missing" in response.json()["detail"].lower()

    async def test_sync_history_missing_conversation_id(
        self,
        api_client: httpx.AsyncClient,
        manager_headers_for_connector,
        connector,
    ):
        """Test sync history fails if thread has no conversation_id."""
        from src.backend.modules.chat.models import Customer

        await connector.fetch_related("company")
        company = connector.company

        customer = await Customer.create(
            user_id="test_user_no_conversation",
            company=company,
            customer_fields={"name": "Test User"},
            meta={},
        )

        thread = await Thread.create(
            thread_id="thread-no-conversation",
            connector_id=connector.connector_id,
            conversation_id=None,
            company=company,
            channel_type=connector.channel_type,
            customer=customer,
            history_synced=False,
        )

        response = await api_client.post(
            f"/api/v1/companies/{thread.company_id}/threads/{thread.thread_id}/sync-history",
            headers=manager_headers_for_connector,
        )
        assert response.status_code == 400
        assert "missing" in response.json()["detail"].lower()

    @patch("httpx.AsyncClient")
    async def test_sync_history_success(
        self,
        mock_httpx_client,
        api_client: httpx.AsyncClient,
        manager_headers_for_connector,
        thread: Thread,
        settings,
    ):
        """Test successful history sync triggers transport module."""
        settings.transport.wappi.url = "http://localhost:8002"
        # Mock httpx client
        mock_client_instance = AsyncMock()
        mock_response = Mock()
        mock_response.status_code = 202
        mock_response.raise_for_status = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        response = await api_client.post(
            f"/api/v1/companies/{thread.company_id}/threads/{thread.thread_id}/sync-history",
            headers=manager_headers_for_connector,
        )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "sync_triggered"
        assert data["thread_id"] == thread.thread_id
        assert "sync started" in data["message"].lower()

        # Verify httpx was called to trigger wappi-module
        mock_client_instance.post.assert_called_once()
        call_args = mock_client_instance.post.call_args
        assert f"wappi/sync/{thread.connector_id}/conversation/{thread.conversation_id}" in call_args[0][0]

    @patch("httpx.AsyncClient")
    async def test_sync_history_transport_module_unavailable(
        self,
        mock_httpx_client,
        api_client: httpx.AsyncClient,
        manager_headers_for_connector,
        thread: Thread,
        settings,
    ):
        """Test sync history when transport module is unavailable."""
        settings.transport.wappi.url = "http://localhost:8002"
        # Mock httpx client to raise error
        mock_client_instance = AsyncMock()
        mock_client_instance.post.side_effect = httpx.ConnectError("Connection refused")
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        response = await api_client.post(
            f"/api/v1/companies/{thread.company_id}/threads/{thread.thread_id}/sync-history",
            headers=manager_headers_for_connector,
        )

        assert response.status_code == 502
        assert "failed to trigger sync" in response.json()["detail"].lower()

    async def test_sync_history_unsupported_connector_type(
        self,
        api_client: httpx.AsyncClient,
        company_factory,
        settings,
    ):
        """Test sync history with unsupported connector type."""
        company = await company_factory()

        # Create telegram connector (not supported for history sync)
        connector = await Connector.create(
            connector_id="test-telegram-connector",
            company=company,
            type=ConnectorType.TELEGRAM,
            channel_type="telegram",
            display_name="Test Telegram",
            managed=True,
            config={},
            enabled=True,
        )

        from src.backend.modules.chat.models import Customer

        customer = await Customer.create(
            user_id="test_user_telegram",
            company=company,
            customer_fields={"name": "Test User"},
            meta={},
        )

        thread = await Thread.create(
            thread_id="thread-telegram",
            connector_id=connector.connector_id,
            conversation_id="conversation-123",
            company=company,
            channel_type=connector.channel_type,
            customer=customer,
            history_synced=False,
        )

        headers = await create_manager_headers_for_company(thread.company_id, settings)
        response = await api_client.post(
            f"/api/v1/companies/{thread.company_id}/threads/{thread.thread_id}/sync-history",
            headers=headers,
        )
        assert response.status_code == 400
        assert "not supported" in response.json()["detail"].lower()


@pytest.fixture
async def thread_with_history(connector):
    """Create a thread with history_synced=True."""
    from src.backend.modules.chat.models import Customer

    await connector.fetch_related("company")
    company = connector.company

    customer = await Customer.create(
        user_id="test_user_synced",
        company=company,
        customer_fields={"name": "Test User Synced"},
        meta={},
    )

    thread = await Thread.create(
        thread_id="test-thread-synced",
        connector_id=connector.connector_id,
        conversation_id="test-conversation-synced",
        company=company,
        channel_type=connector.channel_type,
        customer=customer,
        history_synced=True,
    )
    # Ensure thread is saved
    await thread.save()
    return thread


class TestThreadByConversation:
    """Tests for GET /internal/chat/threads/by-conversation endpoint."""

    async def test_get_thread_by_conversation_not_found(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
    ):
        """Test getting non-existent thread by conversation."""
        response = await api_client.get(
            "/api/v1/internal/chat/threads/by-conversation",
            params={
                "connector_id": "non-existent-connector",
                "conversation_id": "non-existent-conversation",
            },
            headers=service_headers,
        )
        assert response.status_code == 404

    async def test_get_thread_by_conversation_success(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        thread_with_history,
    ):
        """Test successfully getting thread by conversation."""
        response = await api_client.get(
            "/api/v1/internal/chat/threads/by-conversation",
            params={
                "connector_id": thread_with_history.connector_id,
                "conversation_id": thread_with_history.conversation_id,
            },
            headers=service_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["thread_id"] == thread_with_history.thread_id
        assert data["history_synced"] is True

    async def test_get_thread_by_conversation_not_synced(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        thread,
    ):
        """Test getting thread that hasn't been synced yet."""
        # Refresh thread to ensure all fields are loaded
        await thread.refresh_from_db()

        # Verify thread can be found using filter (same as endpoint)
        found_thread = await Thread.filter(
            connector_id=thread.connector_id,
            conversation_id=thread.conversation_id,
        ).first()
        assert found_thread is not None, (
            f"Thread should be found by connector_id={thread.connector_id}, conversation_id={thread.conversation_id}"
        )

        response = await api_client.get(
            "/api/v1/internal/chat/threads/by-conversation",
            params={
                "connector_id": thread.connector_id,
                "conversation_id": thread.conversation_id,
            },
            headers=service_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["thread_id"] == thread.thread_id
        assert data["history_synced"] is False


class TestMarkThreadHistorySynced:
    """Tests for PATCH /internal/chat/threads/{thread_id}/history-synced endpoint."""

    async def test_mark_history_synced_not_found(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
    ):
        """Test marking non-existent thread as synced."""
        response = await api_client.patch(
            "/api/v1/internal/chat/threads/non-existent-thread/history-synced",
            headers=service_headers,
        )
        assert response.status_code == 404

    async def test_mark_history_synced_success(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        thread: Thread,
    ):
        """Test successfully marking thread as synced."""
        assert thread.history_synced is False

        response = await api_client.patch(
            f"/api/v1/internal/chat/threads/{thread.thread_id}/history-synced",
            headers=service_headers,
        )
        assert response.status_code == 204

        # Verify in database
        await thread.refresh_from_db()
        assert thread.history_synced is True

    async def test_mark_history_synced_idempotent(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        thread: Thread,
    ):
        """Test marking thread as synced multiple times is idempotent."""
        # Mark first time
        response1 = await api_client.patch(
            f"/api/v1/internal/chat/threads/{thread.thread_id}/history-synced",
            headers=service_headers,
        )
        assert response1.status_code == 204

        # Mark second time
        response2 = await api_client.patch(
            f"/api/v1/internal/chat/threads/{thread.thread_id}/history-synced",
            headers=service_headers,
        )
        assert response2.status_code == 204

        # Verify still marked
        await thread.refresh_from_db()
        assert thread.history_synced is True
