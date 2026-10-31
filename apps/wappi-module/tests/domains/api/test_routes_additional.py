"""Additional edge case tests for API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from pydantic import SecretStr

from wappi_module.connectors.models import WappiConnectorConfig


class TestWappiWebhookEdgeCases:
    def test_webhook_messages_not_list(self, client: TestClient) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        payload = {"messages": "not a list"}

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
        forward_mock.assert_called_once()

    def test_webhook_message_not_dict(self, client: TestClient) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        payload = {"messages": ["not a dict", 123, None]}

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
        forward_mock.assert_called_once()

    def test_webhook_is_me_true_without_wh_type(self, client: TestClient) -> None:
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
                    "is_me": True,
                    "from_where": "web",
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

    def test_webhook_wh_type_case_insensitive(self, client: TestClient) -> None:
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
                    "wh_type": "OUTGOING_MESSAGE",
                    "from_where": "web",
                    "is_me": False,
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

    def test_webhook_from_where_case_insensitive(self, client: TestClient) -> None:
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
                    "from_where": "API",
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


class TestWappiSyncEdgeCases:
    def test_sync_empty_dialogs(self, client: TestClient) -> None:
        connector = WappiConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wappi_token=SecretStr("token"),
            wappi_profile_id="profile123",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        chats_data = {
            "status": "done",
            "dialogs": [],
            "total_count": 0,
        }

        with patch(
            "wappi_module.services.wappi_api.WappiApiClient.get_chats_list",
            new_callable=AsyncMock,
            return_value=chats_data,
        ):
            response = client.post("/wappi/sync/test-connector")

        assert response.status_code == 202
        data = response.json()
        assert data["chats_processed"] == 0
        assert data["messages_sent"] == 0

    def test_sync_messages_fetch_failed_continues(self, client: TestClient) -> None:
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
                side_effect=[
                    Exception("Failed to fetch messages for chat1"),
                    messages_data,
                ],
            ):
                with patch(
                    "wappi_module.services.sales_agent.BackendInboundClient.forward_update",
                    new_callable=AsyncMock,
                ):
                    response = client.post("/wappi/sync/test-connector")

        assert response.status_code == 202
        data = response.json()
        assert data["chats_processed"] == 2
        assert data["messages_sent"] == 1

    def test_sync_empty_messages_continues(self, client: TestClient) -> None:
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

        empty_messages = {"status": "done", "messages": [], "total_count": 0}
        messages_with_data = {
            "status": "done",
            "messages": [
                {
                    "id": "msg1",
                    "fromMe": False,
                    "body": "Message 1",
                    "chatId": "chat2",
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
                side_effect=[empty_messages, messages_with_data],
            ):
                with patch(
                    "wappi_module.services.sales_agent.BackendInboundClient.forward_update",
                    new_callable=AsyncMock,
                ):
                    response = client.post("/wappi/sync/test-connector")

        assert response.status_code == 202
        data = response.json()
        assert data["chats_processed"] == 2
        assert data["messages_sent"] == 1

    def test_sync_forward_failed_continues(self, client: TestClient) -> None:
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
                    side_effect=[
                        Exception("Forward failed for chat1"),
                        None,
                    ],
                ):
                    response = client.post("/wappi/sync/test-connector")

        assert response.status_code == 202
        data = response.json()
        assert data["chats_processed"] == 2
        assert data["messages_sent"] == 2


class TestTransportDeliveryEdgeCases:
    def test_transport_delivery_empty_body_decode(self, client: TestClient) -> None:
        headers = {
            "X-Service-Key": "test-api-key",
            "X-Connector-Id": "test-connector",
        }

        response = client.post(
            "/transport/delivery",
            content=b"",
            headers=headers,
        )

        assert response.status_code == 422

    def test_transport_delivery_empty_json_object(self, client: TestClient) -> None:
        headers = {
            "X-Service-Key": "test-api-key",
            "X-Connector-Id": "test-connector",
        }

        response = client.post(
            "/transport/delivery",
            json={},
            headers=headers,
        )

        assert response.status_code == 422
