from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from wazzup_module.connectors.models import WazzupConnectorConfig


class TestHealthEndpoint:
    def test_healthz_returns_ok(self, client: TestClient) -> None:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestAdminEndpoints:
    def test_admin_reload_success(self, client: TestClient) -> None:
        with patch(
            "wazzup_module.connectors.manager.ConnectorManager.reload",
            new_callable=AsyncMock,
        ):
            response = client.post("/admin/reload")
        assert response.status_code == 202
        assert response.json() == {"status": "reloaded"}

    def test_admin_reload_error(self, client: TestClient) -> None:
        with patch(
            "wazzup_module.connectors.manager.ConnectorManager.reload",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Backend error"),
        ):
            with pytest.raises(RuntimeError):
                client.post("/admin/reload")


class TestTransportDeliveryEndpoint:
    def test_transport_delivery_success(self, client: TestClient, sample_transport_payload: dict[str, Any]) -> None:
        connector = WazzupConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wazzup_api_key=SecretStr("api-key"),
            channel_id="chan-123",
            channel_type="instagram",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        headers = {
            "X-Service-Key": "test-api-key",
            "X-Connector-Id": "test-connector",
        }

        with patch(
            "wazzup_module.services.wazzup_api.WazzupApiClient.send_message",
            new_callable=AsyncMock,
        ):
            response = client.post("/transport/delivery", json=sample_transport_payload, headers=headers)

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert data["connector_id"] == "test-connector"

    def test_transport_delivery_invalid_json(self, client: TestClient) -> None:
        response = client.post(
            "/transport/delivery",
            content="invalid json",
            headers={"X-Service-Key": "test-api-key", "X-Connector-Id": "test-connector"},
        )
        assert response.status_code == 400

    def test_transport_delivery_connector_not_found(
        self, client: TestClient, sample_transport_payload: dict[str, Any]
    ) -> None:
        headers = {
            "X-Service-Key": "test-api-key",
            "X-Connector-Id": "test-connector",
        }
        response = client.post("/transport/delivery", json=sample_transport_payload, headers=headers)
        assert response.status_code == 404


class TestWazzupWebhook:
    def test_webhook_forwards_message(self, client: TestClient, sample_webhook_payload: dict[str, Any]) -> None:
        connector = WazzupConnectorConfig(
            connector_id="test-connector",
            company_id="123",
            wazzup_api_key=SecretStr("api-key"),
            channel_id="channel-uuid-123",
            channel_type="instagram",
        )
        client.app.state.connector_manager._connectors["test-connector"] = connector

        with patch.object(
            client.app.state.inbound_client,
            "forward_message",
            new_callable=AsyncMock,
        ) as mock_forward:
            response = client.post("/wazzup/webhook", json=sample_webhook_payload)

        assert response.status_code == 200
        assert response.json() == {"status": "forwarded"}
        mock_forward.assert_called_once()
        args = mock_forward.call_args
        assert args[0][0] == "test-connector"

    def test_webhook_unknown_channel_id(self, client: TestClient) -> None:
        payload = {
            "messages": [
                {
                    "messageId": "msg-1",
                    "channelId": "unknown-channel",
                    "chatId": "user-1",
                    "text": "Hello",
                    "isEcho": False,
                }
            ]
        }
        response = client.post("/wazzup/webhook", json=payload)
        assert response.status_code == 200
        assert response.json() == {"status": "forwarded"}

    def test_webhook_no_messages(self, client: TestClient) -> None:
        response = client.post("/wazzup/webhook", json={"messages": []})
        assert response.status_code == 200

    def test_webhook_no_channel_id(self, client: TestClient) -> None:
        payload = {"messages": [{"text": "Hello", "chatId": "user-1"}]}
        response = client.post("/wazzup/webhook", json=payload)
        assert response.status_code == 200

    def test_webhook_invalid_json(self, client: TestClient) -> None:
        response = client.post("/wazzup/webhook", content="not json")
        assert response.status_code == 400
