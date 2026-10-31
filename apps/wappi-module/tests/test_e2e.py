"""E2E tests for Wappi module under new architecture (Backend Router)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from wappi_module.connectors.models import WappiConnectorConfig

# =============================================================================
# Inbound Flow Tests: Wappi → wappi-module → Backend → Sales Agent
# =============================================================================


def test_e2e_inbound_message_basic(
    client: TestClient,
    sample_connector_config: WappiConnectorConfig,
) -> None:
    """Test basic inbound message normalization and forwarding."""
    client.app.state.connector_manager._connectors["test-connector"] = sample_connector_config

    webhook_payload = {
        "messages": [
            {
                "id": "msg123",
                "type": "text",
                "body": "Hello from user",
                "chatId": "351311665",
                "from": "user123",
                "time": 1234567890,
                "fromMe": False,
                "is_me": False,
            }
        ]
    }

    with patch(
        "wappi_module.services.sales_agent.httpx.AsyncClient.post",
        new_callable=AsyncMock,
    ) as mock_post:
        mock_response = AsyncMock()
        mock_response.status_code = 202
        mock_post.return_value = mock_response

        response = client.post(
            "/wappi/test-connector/webhook",
            json=webhook_payload,
        )

    assert response.status_code == 202
    assert response.json() == {"status": "forwarded"}

    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[0][0] == "http://backend.test/api/v1/messages/inbound"

    sent_envelope = call_args[1]["json"]
    assert sent_envelope["conversation_id"] == "351311665"
    assert sent_envelope["user_id"] == "351311665"
    assert sent_envelope["text"] == "Hello from user"
    assert sent_envelope["ts"] == 1234567890
    assert sent_envelope.get("audio") is None
    assert isinstance(sent_envelope.get("extra"), dict)


def test_e2e_inbound_manager_outgoing_flag(
    client: TestClient,
    sample_connector_config: WappiConnectorConfig,
) -> None:
    """Test that _manager_outgoing flag is preserved for manager messages."""
    client.app.state.connector_manager._connectors["test-connector"] = sample_connector_config

    webhook_payload = {
        "messages": [
            {
                "id": "msg456",
                "type": "text",
                "body": "Manager reply",
                "chatId": "351311665",
                "from": "user123",
                "time": 1234567900,
                "wh_type": "outgoing_message",
                "from_where": "web",
                "fromMe": True,
                "is_me": True,
            }
        ]
    }

    with patch(
        "wappi_module.services.sales_agent.httpx.AsyncClient.post",
        new_callable=AsyncMock,
    ) as mock_post:
        mock_response = AsyncMock()
        mock_response.status_code = 202
        mock_post.return_value = mock_response

        response = client.post(
            "/wappi/test-connector/webhook",
            json=webhook_payload,
        )

    assert response.status_code == 202

    mock_post.assert_called_once()
    sent_envelope = mock_post.call_args[1]["json"]
    assert sent_envelope["extra"].get("_manager_outgoing") is True
    assert sent_envelope["extra"].get("fromMe") is True


def test_e2e_inbound_sync_mode_flag(
    client: TestClient,
    sample_connector_config: WappiConnectorConfig,
) -> None:
    """Test that _sync_mode flag is preserved for historical sync."""
    client.app.state.connector_manager._connectors["test-connector"] = sample_connector_config

    webhook_payload = {
        "messages": [
            {
                "id": "msg789",
                "type": "text",
                "body": "Historical message",
                "chatId": "351311665",
                "from": "user123",
                "time": 1234560000,
                "fromMe": False,
                "_sync_mode": True,
            }
        ]
    }

    with patch(
        "wappi_module.services.sales_agent.httpx.AsyncClient.post",
        new_callable=AsyncMock,
    ) as mock_post:
        mock_response = AsyncMock()
        mock_response.status_code = 202
        mock_post.return_value = mock_response

        response = client.post(
            "/wappi/test-connector/webhook",
            json=webhook_payload,
        )

    assert response.status_code == 202

    mock_post.assert_called_once()
    sent_envelope = mock_post.call_args[1]["json"]
    assert sent_envelope["extra"].get("_sync_mode") is True


def test_e2e_inbound_audio_message(
    client: TestClient,
    sample_connector_config: WappiConnectorConfig,
    mock_backend_client,
) -> None:
    """Test voice message (ptt) normalization."""
    client.app.state.connector_manager._connectors["test-connector"] = sample_connector_config

    sales_agent_client = client.app.state.sales_agent_client
    sales_agent_client._backend_client = mock_backend_client

    webhook_payload = {
        "messages": [
            {
                "id": "msg_audio",
                "type": "ptt",
                "body": "base64encodedaudiodata==",
                "mimetype": "audio/ogg; codecs=opus",
                "chatId": "351311665",
                "from": "user123",
                "time": 1234567890,
                "fromMe": False,
            }
        ]
    }

    with (
        patch(
            "wappi_module.services.sales_agent.httpx.AsyncClient.post",
            new_callable=AsyncMock,
        ) as mock_post,
        patch(
            "wappi_module.services.sales_agent.AudioConversionService.convert_to_mp3",
            new_callable=AsyncMock,
        ) as mock_convert,
    ):
        mock_response = AsyncMock()
        mock_response.status_code = 202
        mock_post.return_value = mock_response

        mock_convert.return_value = b"fake_mp3_data"
        mock_backend_client.upload_artifact = AsyncMock(return_value="artifact_123")

        response = client.post(
            "/wappi/test-connector/webhook",
            json=webhook_payload,
        )

    assert response.status_code == 202

    mock_post.assert_called_once()
    sent_envelope = mock_post.call_args[1]["json"]
    assert sent_envelope.get("text") is None
    assert len(sent_envelope.get("artifact_ids", [])) == 1
    assert sent_envelope["artifact_ids"][0] == "artifact_123"


# =============================================================================
# Outbound Flow Tests: Sales Agent → Backend → wappi-module → Wappi API
# =============================================================================


def test_e2e_outbound_delivery_success(
    client: TestClient,
    sample_connector_config: WappiConnectorConfig,
    sample_transport_payload: dict[str, Any],
) -> None:
    """Test successful outbound message delivery."""
    client.app.state.connector_manager._connectors["test-connector"] = sample_connector_config

    headers = {
        "X-Service-Key": "test-api-key",
        "X-Connector-Id": "test-connector",
    }

    with patch(
        "wappi_module.transport.service.WappiApiClient.send_message",
        new_callable=AsyncMock,
    ) as mock_send:
        response = client.post(
            "/transport/delivery",
            json=sample_transport_payload,
            headers=headers,
        )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["connector_id"] == "test-connector"
    assert data["correlation_id"] == "corr123"

    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args[1]
    assert call_kwargs["recipient"] == "351311665"
    assert call_kwargs["body"] == "Test message"


def test_e2e_outbound_idempotency(
    client: TestClient,
    sample_connector_config: WappiConnectorConfig,
    sample_transport_payload: dict[str, Any],
) -> None:
    """Test idempotency for duplicate correlation_id."""
    client.app.state.connector_manager._connectors["test-connector"] = sample_connector_config

    headers = {
        "X-Service-Key": "test-api-key",
        "X-Connector-Id": "test-connector",
    }

    with patch(
        "wappi_module.transport.service.WappiApiClient.send_message",
        new_callable=AsyncMock,
    ):
        response1 = client.post(
            "/transport/delivery",
            json=sample_transport_payload,
            headers=headers,
        )
        response2 = client.post(
            "/transport/delivery",
            json=sample_transport_payload,
            headers=headers,
        )

    assert response1.status_code == 202
    assert response1.json()["status"] == "accepted"

    assert response2.status_code == 409
    assert response2.json()["status"] == "duplicate"


# =============================================================================
# Connector Reload Tests: Event-driven configuration updates
# =============================================================================


@pytest.mark.asyncio
async def test_e2e_connector_reload_via_admin(
    client: TestClient,
    sample_connector_config: WappiConnectorConfig,
) -> None:
    """Test manual connector reload via admin endpoint."""
    with patch(
        "wappi_module.services.backend.WappiBackendClient.fetch_connectors",
        new_callable=AsyncMock,
        return_value=[sample_connector_config],
    ):
        response = client.post("/admin/reload")

    assert response.status_code == 202
    assert response.json() == {"status": "reloaded"}

    assert "test-connector" in client.app.state.connector_manager._connectors
