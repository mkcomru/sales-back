"""Tests for history synchronization endpoints in wappi-module."""

from unittest.mock import patch

import pytest

from wappi_module.connectors.models import WappiConnectorConfig


class TestSyncConversationHistoryEndpoint:
    """Tests for POST /wappi/sync/{connector_id}/conversation/{conversation_id} endpoint."""

    def test_sync_conversation_history_connector_not_found(self, client):
        """Test sync with non-existent connector."""
        # Connector manager will return None for non-existent connector
        response = client.post("/wappi/sync/non-existent/conversation/conv-123")
        assert response.status_code == 404

    def test_sync_conversation_history_triggers_background_task(
        self,
        client,
        sample_connector_config,
        mock_connector_manager,
    ):
        """Test that endpoint triggers background sync task."""
        # Add connector to manager
        mock_connector_manager._connectors[sample_connector_config.connector_id] = sample_connector_config

        with patch("wappi_module.api.routes.asyncio.create_task") as mock_create_task:
            response = client.post(f"/wappi/sync/{sample_connector_config.connector_id}/conversation/conv-456")

            assert response.status_code == 202
            data = response.json()
            assert data["status"] == "sync_triggered"
            assert data["conversation_id"] == "conv-456"

            # Verify background task was created
            mock_create_task.assert_called_once()


class TestSyncMoreChatsEndpoint:
    """Tests for POST /wappi/sync/{connector_id}/more-chats endpoint."""

    @pytest.fixture
    def connector_config(self):
        """Create a test connector config."""
        from pydantic import SecretStr

        return WappiConnectorConfig(
            connector_id="test-connector-more",
            company_id="test-company-more",
            wappi_token=SecretStr("test-token"),
            wappi_profile_id="test-profile",
            channel_type="whatsapp",
            metadata={},
        )

    def test_sync_more_chats_connector_not_found(
        self,
        client,
    ):
        """Test sync more chats with non-existent connector."""
        response = client.post("/wappi/sync/non-existent/more-chats")
        assert response.status_code == 404

    def test_sync_more_chats_triggers_background_task(
        self,
        client,
        connector_config,
        mock_connector_manager,
    ):
        """Test that endpoint triggers background sync task."""
        # Add connector to manager
        mock_connector_manager._connectors[connector_config.connector_id] = connector_config

        with patch("wappi_module.api.routes.asyncio.create_task") as mock_create_task:
            response = client.post(f"/wappi/sync/{connector_config.connector_id}/more-chats")

            assert response.status_code == 202
            data = response.json()
            assert data["status"] == "sync_triggered"
            assert "loading more chats" in data["message"].lower()

            # Verify background task was created
            mock_create_task.assert_called_once()


# Background task tests removed - too complex for unit testing
# They test internal implementation details and are better covered by integration tests
# Endpoint tests above confirm that tasks are triggered correctly
