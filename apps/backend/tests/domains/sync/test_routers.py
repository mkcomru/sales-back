"""Tests for sync API endpoints."""

from datetime import UTC, datetime

from common.contracts.sync import SyncBatchRequest, SyncHeartbeatRequest, SyncMessage, SyncStatus, SyncStatusUpdate
from common.models.inbound import MessageRole

from src.backend.modules.transport.models import Connector, ConnectorType


class TestSyncRouters:
    """Tests for sync API endpoints."""

    async def test_ingest_batch_success(self, api_client, service_headers, company_factory):
        """Test successful batch ingestion."""
        company = await company_factory()

        await Connector.create(
            connector_id="test-connector",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="telegram",
            display_name="Test Connector",
            managed=True,
            config={},
            enabled=True,
        )

        messages = [
            SyncMessage(
                conversation_id="chat123",
                user_id="user1",
                text="Hello",
                role=MessageRole.USER,
                timestamp=datetime.now(UTC),
                provider_message_id="msg1",
            ),
        ]

        request = SyncBatchRequest(
            connector_id="test-connector",
            batch_id="batch1",
            correlation_id="corr1",
            messages=messages,
        )

        response = await api_client.post(
            "/api/v1/internal/sync/batch",
            json=request.model_dump(mode="json"),
            headers=service_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processed"
        assert data["message_count"] == 1

    async def test_ingest_batch_duplicate(self, api_client, service_headers, company_factory):
        """Test duplicate batch returns 409."""
        company = await company_factory()

        await Connector.create(
            connector_id="test-connector",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="telegram",
            display_name="Test Connector",
            managed=True,
            config={},
            enabled=True,
            sync_progress={"processed_batches": ["batch1"]},
        )

        request = SyncBatchRequest(
            connector_id="test-connector",
            batch_id="batch1",
            correlation_id="corr1",
            messages=[],
        )

        response = await api_client.post(
            "/api/v1/internal/sync/batch",
            json=request.model_dump(mode="json"),
            headers=service_headers,
        )

        assert response.status_code == 409

    async def test_ingest_batch_unauthorized(self, api_client, company_factory):
        """Test batch ingestion without service key."""
        company = await company_factory()

        await Connector.create(
            connector_id="test-connector",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="telegram",
            display_name="Test Connector",
            managed=True,
            config={},
            enabled=True,
        )

        request = SyncBatchRequest(
            connector_id="test-connector",
            batch_id="batch1",
            correlation_id="corr1",
            messages=[],
        )

        response = await api_client.post(
            "/api/v1/internal/sync/batch",
            json=request.model_dump(mode="json"),
        )

        assert response.status_code == 401

    async def test_update_status_success(self, api_client, service_headers, company_factory):
        """Test successful status update."""
        company = await company_factory()

        connector = await Connector.create(
            connector_id="test-connector",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="telegram",
            display_name="Test Connector",
            managed=True,
            config={},
            enabled=True,
        )

        request = SyncStatusUpdate(
            connector_id="test-connector",
            correlation_id="corr1",
            status=SyncStatus.INITIAL,
        )

        response = await api_client.post(
            "/api/v1/internal/sync/status",
            json=request.model_dump(mode="json"),
            headers=service_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"

        await connector.refresh_from_db()
        assert connector.sync_status.value == "initial"

    async def test_send_heartbeat_success(self, api_client, service_headers, company_factory):
        """Test successful heartbeat."""
        company = await company_factory()

        connector = await Connector.create(
            connector_id="test-connector",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="telegram",
            display_name="Test Connector",
            managed=True,
            config={},
            enabled=True,
        )

        request = SyncHeartbeatRequest(
            connector_id="test-connector",
            correlation_id="corr1",
        )

        response = await api_client.post(
            "/api/v1/internal/sync/heartbeat",
            json=request.model_dump(mode="json"),
            headers=service_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "received"

        await connector.refresh_from_db()
        assert "last_heartbeat_at" in connector.sync_progress

    async def test_get_cursor_success(self, api_client, service_headers, company_factory):
        """Test getting cursor."""
        company = await company_factory()

        await Connector.create(
            connector_id="test-connector",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="telegram",
            display_name="Test Connector",
            managed=True,
            config={},
            enabled=True,
            sync_progress={"cursor": "offset_100"},
        )

        response = await api_client.get(
            "/api/v1/internal/sync/cursor/test-connector",
            headers=service_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["cursor"] == "offset_100"

    async def test_get_cursor_not_found(self, api_client, service_headers, company_factory):
        """Test getting cursor when not set."""
        company = await company_factory()

        await Connector.create(
            connector_id="test-connector",
            company=company,
            type=ConnectorType.WAPPI,
            channel_type="telegram",
            display_name="Test Connector",
            managed=True,
            config={},
            enabled=True,
        )

        response = await api_client.get(
            "/api/v1/internal/sync/cursor/test-connector",
            headers=service_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["cursor"] is None
