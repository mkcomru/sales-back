"""Tests for API routes."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from wappi_module.connectors.models import WappiConnectorConfig


class TestHealthEndpoint:
    def test_healthz_returns_ok(self, client: TestClient) -> None:
        response = client.get("/healthz")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestAdminEndpoints:
    def test_admin_reload_success(self, client: TestClient) -> None:
        with patch(
            "wappi_module.connectors.manager.ConnectorManager.reload",
            new_callable=AsyncMock,
        ):
            response = client.post("/admin/reload")

        assert response.status_code == 202
        assert response.json() == {"status": "reloaded"}

    def test_admin_reload_error(self, client: TestClient) -> None:
        with patch(
            "wappi_module.connectors.manager.ConnectorManager.reload",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Backend error"),
        ):
            with pytest.raises(RuntimeError):
                client.post("/admin/reload")


class TestTransportDeliveryEndpoint:
    def test_transport_delivery_success(self, client: TestClient, sample_transport_payload: dict[str, Any]) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        headers = {
            "X-Service-Key": "test-api-key",
            "X-Connector-Id": "test-connector",
        }

        with patch(
            "wappi_module.transport.service.WappiApiClient.send_message",
            new_callable=AsyncMock,
        ):
            response = client.post(
                "/transport/delivery",
                json=sample_transport_payload,
                headers=headers,
            )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert data["connector_id"] == "test-connector"

    def test_transport_delivery_invalid_json(self, client: TestClient) -> None:
        headers = {
            "X-Service-Key": "test-api-key",
            "X-Connector-Id": "test-connector",
        }

        response = client.post(
            "/transport/delivery",
            content="invalid json",
            headers=headers,
        )

        assert response.status_code == 400
        assert "Invalid JSON body" in response.json()["detail"]

    def test_transport_delivery_validation_error(self, client: TestClient) -> None:
        headers = {
            "X-Service-Key": "test-api-key",
            "X-Connector-Id": "test-connector",
        }

        invalid_payload = {
            "connector_id": "test",
        }

        response = client.post(
            "/transport/delivery",
            json=invalid_payload,
            headers=headers,
        )

        assert response.status_code == 422

    def test_transport_delivery_missing_service_key(
        self, client: TestClient, sample_transport_payload: dict[str, Any]
    ) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        headers = {"X-Connector-Id": "test-connector"}

        response = client.post(
            "/transport/delivery",
            json=sample_transport_payload,
            headers=headers,
        )

        assert response.status_code == 401
        assert "Missing service credentials" in response.json()["detail"]

    def test_transport_delivery_connector_not_found(
        self, client: TestClient, sample_transport_payload: dict[str, Any]
    ) -> None:
        headers = {
            "X-Service-Key": "test-api-key",
            "X-Connector-Id": "test-connector",
        }

        response = client.post(
            "/transport/delivery",
            json=sample_transport_payload,
            headers=headers,
        )

        assert response.status_code == 404
        assert "Unknown connector_id" in response.json()["detail"]

    def test_transport_delivery_duplicate(self, client: TestClient, sample_transport_payload: dict[str, Any]) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        headers = {
            "X-Service-Key": "test-api-key",
            "X-Connector-Id": "test-connector",
        }

        with patch(
            "wappi_module.transport.service.WappiApiClient.send_message",
            new_callable=AsyncMock,
        ):
            first_response = client.post(
                "/transport/delivery",
                json=sample_transport_payload,
                headers=headers,
            )
            second_response = client.post(
                "/transport/delivery",
                json=sample_transport_payload,
                headers=headers,
            )

        assert first_response.status_code == 202
        assert second_response.status_code == 409
        assert second_response.json()["status"] == "duplicate"


class TestWappiWebhookEndpoint:
    def test_webhook_success(self, client: TestClient, sample_webhook_payload: dict[str, Any]) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        with patch(
            "wappi_module.services.sales_agent.BackendInboundClient.forward_update",
            new_callable=AsyncMock,
        ):
            response = client.post(
                "/wappi/test-connector/webhook",
                json=sample_webhook_payload,
            )

        assert response.status_code == 202
        assert response.json() == {"status": "forwarded"}

    def test_webhook_connector_not_found(self, client: TestClient, sample_webhook_payload: dict[str, Any]) -> None:
        response = client.post(
            "/wappi/non-existent/webhook",
            json=sample_webhook_payload,
        )

        assert response.status_code == 404
        assert "Unknown connector" in response.json()["detail"]

    def test_webhook_invalid_json(self, client: TestClient) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        response = client.post(
            "/wappi/test-connector/webhook",
            content="invalid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 400
        assert "Invalid JSON payload" in response.json()["detail"]

    def test_webhook_forward_failed(self, client: TestClient, sample_webhook_payload: dict[str, Any]) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        with patch(
            "wappi_module.services.sales_agent.BackendInboundClient.forward_update",
            new_callable=AsyncMock,
            side_effect=Exception("Sales Agent error"),
        ):
            response = client.post(
                "/wappi/test-connector/webhook",
                json=sample_webhook_payload,
            )

        assert response.status_code == 502
        assert "Failed to forward to sales agent" in response.json()["detail"]

    def test_webhook_manager_outgoing_detection(self, client: TestClient) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        payload = {
            "messages": [
                {
                    "id": "msg1",
                    "wh_type": "outgoing_message",
                    "from_where": "web",
                    "is_me": True,
                    "body": "Manager message",
                }
            ]
        }

        forward_mock = AsyncMock()
        with patch(
            "wappi_module.services.sales_agent.BackendInboundClient.forward_update",
            forward_mock,
        ):
            response = client.post(
                "/wappi/test-connector/webhook",
                json=payload,
            )

        assert response.status_code == 202
        call_args = forward_mock.call_args
        forwarded_payload = call_args[0][2]
        assert forwarded_payload["messages"][0]["_manager_outgoing"] is True

    def test_webhook_manager_outgoing_from_where_empty(self, client: TestClient) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        payload = {
            "messages": [
                {
                    "id": "msg1",
                    "wh_type": "outgoing_message",
                    "from_where": "",
                    "is_me": True,
                    "body": "Manager message",
                }
            ]
        }

        forward_mock = AsyncMock()
        with patch(
            "wappi_module.services.sales_agent.BackendInboundClient.forward_update",
            forward_mock,
        ):
            response = client.post(
                "/wappi/test-connector/webhook",
                json=payload,
            )

        assert response.status_code == 202
        call_args = forward_mock.call_args
        forwarded_payload = call_args[0][2]
        assert forwarded_payload["messages"][0]["_manager_outgoing"] is True

    def test_webhook_api_outgoing_not_marked(self, client: TestClient) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        payload = {
            "messages": [
                {
                    "id": "msg1",
                    "wh_type": "outgoing_message",
                    "from_where": "api",
                    "is_me": True,
                    "body": "Assistant message",
                }
            ]
        }

        forward_mock = AsyncMock()
        with patch(
            "wappi_module.services.sales_agent.BackendInboundClient.forward_update",
            forward_mock,
        ):
            response = client.post(
                "/wappi/test-connector/webhook",
                json=payload,
            )

        assert response.status_code == 202
        call_args = forward_mock.call_args
        forwarded_payload = call_args[0][2]
        assert "_manager_outgoing" not in forwarded_payload["messages"][0]

    def test_webhook_incoming_not_marked(self, client: TestClient) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        payload = {
            "messages": [
                {
                    "id": "msg1",
                    "wh_type": "incoming_message",
                    "from_where": "web",
                    "is_me": False,
                    "body": "User message",
                }
            ]
        }

        forward_mock = AsyncMock()
        with patch(
            "wappi_module.services.sales_agent.BackendInboundClient.forward_update",
            forward_mock,
        ):
            response = client.post(
                "/wappi/test-connector/webhook",
                json=payload,
            )

        assert response.status_code == 202
        call_args = forward_mock.call_args
        forwarded_payload = call_args[0][2]
        assert "_manager_outgoing" not in forwarded_payload["messages"][0]


class TestWappiSyncEndpoint:
    def test_sync_connector_history_success(self, client: TestClient) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        chats_data = {
            "status": "done",
            "dialogs": [
                {"id": "chat1", "name": "Chat 1"},
                {"id": "chat2", "name": "Chat 2"},
            ],
            "total_count": 2,
        }

        messages_data = {
            "status": "done",
            "messages": [
                {
                    "id": "msg1",
                    "fromMe": False,
                    "body": "Message 1",
                    "chatId": "chat1",
                }
            ],
            "total_count": 1,
        }

        with patch(
            "wappi_module.services.wappi_api.WappiApiClient.get_chats_list",
            new_callable=AsyncMock,
            return_value=chats_data,
        ):
            with patch(
                "wappi_module.services.wappi_api.WappiApiClient.get_chat_messages",
                new_callable=AsyncMock,
                return_value=messages_data,
            ):
                with patch(
                    "wappi_module.services.sales_agent.BackendInboundClient.forward_update",
                    new_callable=AsyncMock,
                ):
                    response = client.post("/wappi/sync/test-connector")

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "completed"
        assert data["chats_processed"] == 2
        assert data["messages_sent"] == 2

    def test_sync_connector_not_found(self, client: TestClient) -> None:
        response = client.post("/wappi/sync/non-existent")

        assert response.status_code == 404
        assert "Connector 'non-existent' not found" in response.json()["detail"]

    def test_sync_missing_wappi_credentials(self, client: TestClient) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        connector.wappi_token = SecretStr("")
        connector.wappi_profile_id = ""

        response = client.post("/wappi/sync/test-connector")

        assert response.status_code == 400
        assert "missing Wappi credentials" in response.json()["detail"]

    def test_sync_chats_fetch_failed(self, client: TestClient) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        with patch(
            "wappi_module.services.wappi_api.WappiApiClient.get_chats_list",
            new_callable=AsyncMock,
            side_effect=Exception("Wappi API error"),
        ):
            response = client.post("/wappi/sync/test-connector")

        assert response.status_code == 502
        assert "Failed to fetch chats from Wappi API" in response.json()["detail"]

    def test_sync_skips_chat_without_id(self, client: TestClient) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        chats_data = {
            "status": "done",
            "dialogs": [
                {"id": "chat1", "name": "Chat 1"},
                {"name": "Chat without ID"},
            ],
            "total_count": 2,
        }

        messages_data = {
            "status": "done",
            "messages": [],
            "total_count": 0,
        }

        with patch(
            "wappi_module.services.wappi_api.WappiApiClient.get_chats_list",
            new_callable=AsyncMock,
            return_value=chats_data,
        ):
            with patch(
                "wappi_module.services.wappi_api.WappiApiClient.get_chat_messages",
                new_callable=AsyncMock,
                return_value=messages_data,
            ):
                with patch(
                    "wappi_module.services.sales_agent.BackendInboundClient.forward_update",
                    new_callable=AsyncMock,
                ):
                    response = client.post("/wappi/sync/test-connector")

        assert response.status_code == 202
        data = response.json()
        assert data["chats_processed"] == 2

    def test_sync_adds_sync_mode_flag(self, client: TestClient) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        chats_data = {
            "status": "done",
            "dialogs": [{"id": "chat1", "name": "Chat 1"}],
            "total_count": 1,
        }

        messages_data = {
            "status": "done",
            "messages": [
                {
                    "id": "msg1",
                    "fromMe": False,
                    "body": "Message 1",
                    "chatId": "chat1",
                }
            ],
            "total_count": 1,
        }

        forward_mock = AsyncMock()
        with patch(
            "wappi_module.services.wappi_api.WappiApiClient.get_chats_list",
            new_callable=AsyncMock,
            return_value=chats_data,
        ):
            with patch(
                "wappi_module.services.wappi_api.WappiApiClient.get_chat_messages",
                new_callable=AsyncMock,
                return_value=messages_data,
            ):
                with patch(
                    "wappi_module.services.sales_agent.BackendInboundClient.forward_update",
                    forward_mock,
                ):
                    response = client.post("/wappi/sync/test-connector")

        assert response.status_code == 202
        call_args = forward_mock.call_args
        forwarded_payload = call_args[0][2]
        assert forwarded_payload["messages"][0]["_sync_mode"] is True


class TestWappiChatHistoryEndpoint:
    def test_get_chat_history_success(self, client: TestClient) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        messages_data = {
            "status": "done",
            "messages": [
                {
                    "id": "msg1",
                    "fromMe": False,
                    "body": "Message 1",
                    "chatId": "chat1",
                }
            ],
            "total_count": 1,
        }

        with patch(
            "wappi_module.services.wappi_api.WappiApiClient.get_chat_messages",
            new_callable=AsyncMock,
            return_value=messages_data,
        ):
            with patch(
                "wappi_module.services.sales_agent.BackendInboundClient.forward_update",
                new_callable=AsyncMock,
            ):
                response = client.get("/wappi/test-connector/chat/chat1/history?sync=true")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["total_count"] == 1
        assert data["synced"] is True

    def test_get_chat_history_without_sync(self, client: TestClient) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        messages_data = {
            "status": "done",
            "messages": [
                {
                    "id": "msg1",
                    "fromMe": False,
                    "body": "Message 1",
                    "chatId": "chat1",
                }
            ],
            "total_count": 1,
        }

        with patch(
            "wappi_module.services.wappi_api.WappiApiClient.get_chat_messages",
            new_callable=AsyncMock,
            return_value=messages_data,
        ):
            response = client.get("/wappi/test-connector/chat/chat1/history?sync=false")

        assert response.status_code == 200
        data = response.json()
        assert data["synced"] is False

    def test_get_chat_history_connector_not_found(self, client: TestClient) -> None:
        response = client.get("/wappi/non-existent/chat/chat1/history")

        assert response.status_code == 404
        assert "Connector 'non-existent' not found" in response.json()["detail"]

    def test_get_chat_history_missing_credentials(self, client: TestClient) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        connector.wappi_token = SecretStr("")
        connector.wappi_profile_id = ""

        response = client.get("/wappi/test-connector/chat/chat1/history")

        assert response.status_code == 400
        assert "missing Wappi credentials" in response.json()["detail"]

    def test_get_chat_history_fetch_failed(self, client: TestClient) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        with patch(
            "wappi_module.services.wappi_api.WappiApiClient.get_chat_messages",
            new_callable=AsyncMock,
            side_effect=Exception("Wappi API error"),
        ):
            response = client.get("/wappi/test-connector/chat/chat1/history")

        assert response.status_code == 502
        assert "Failed to fetch chat history from Wappi" in response.json()["detail"]

    def test_get_chat_history_with_custom_params(self, client: TestClient) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        messages_data = {
            "status": "done",
            "messages": [],
            "total_count": 0,
        }

        get_messages_mock = AsyncMock(return_value=messages_data)
        with patch(
            "wappi_module.services.wappi_api.WappiApiClient.get_chat_messages",
            get_messages_mock,
        ):
            response = client.get("/wappi/test-connector/chat/chat1/history?limit=50&offset=10&order=asc")

        assert response.status_code == 200
        get_messages_mock.assert_called_once()
        call_args = get_messages_mock.call_args
        assert call_args[1]["limit"] == 50
        assert call_args[1]["offset"] == 10
        assert call_args[1]["order"] == "asc"

    def test_get_chat_history_sync_failed_continues(self, client: TestClient) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        messages_data = {
            "status": "done",
            "messages": [
                {
                    "id": "msg1",
                    "fromMe": False,
                    "body": "Message 1",
                    "chatId": "chat1",
                }
            ],
            "total_count": 1,
        }

        with patch(
            "wappi_module.services.wappi_api.WappiApiClient.get_chat_messages",
            new_callable=AsyncMock,
            return_value=messages_data,
        ):
            with patch(
                "wappi_module.services.sales_agent.BackendInboundClient.forward_update",
                new_callable=AsyncMock,
                side_effect=Exception("Sync failed"),
            ):
                response = client.get("/wappi/test-connector/chat/chat1/history?sync=true")

        assert response.status_code == 200
        data = response.json()
        assert data["synced"] is False
