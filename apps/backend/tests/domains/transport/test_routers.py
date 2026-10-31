"""Router tests for unified connector endpoints."""

import httpx

from src.backend.modules.transport.models import Connector, ConnectorType


def _connector_create_payload(company_id: int, **overrides: dict) -> dict:
    base = {
        "connector_id": "test-connector-1",
        "company_id": company_id,
        "type": "telegram",
        "channel_type": "telegram",
        "display_name": "Test Telegram Bot",
        "managed": True,
        "config": {"bot_token": "123:ABC", "mode": "auto"},
        "enabled": True,
    }
    base.update(overrides)
    return base


class TestConnectorsCRUD:
    """Tests for /transport/connectors endpoints."""

    async def test_list_connectors_without_auth(self, api_client: httpx.AsyncClient):
        response = await api_client.get("/api/v1/transport/connectors")
        assert response.status_code == 401

    async def test_list_connectors_empty(self, api_client: httpx.AsyncClient, service_headers):
        response = await api_client.get("/api/v1/transport/connectors", headers=service_headers)
        assert response.status_code == 200
        data = response.json()
        assert "connectors" in data
        assert data["connectors"] == []

    async def test_list_connectors_with_data(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        authenticated_user_with_company,
    ):
        auth = authenticated_user_with_company
        company = auth["company"]
        payload = _connector_create_payload(company.id)
        await api_client.post(
            f"/api/v1/companies/{company.id}/connectors",
            json=payload,
            headers=auth["headers"],
        )

        response = await api_client.get("/api/v1/transport/connectors", headers=service_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["connectors"]) == 1
        assert data["connectors"][0]["connector_id"] == "test-connector-1"

    async def test_create_telegram_connector(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
    ):
        auth = authenticated_user_with_company
        company = auth["company"]
        payload = _connector_create_payload(
            company.id,
            connector_id="tg-bot-create",
            display_name="Created Bot",
            config={"bot_token": "token123", "mode": "webhook"},
        )
        response = await api_client.post(
            f"/api/v1/companies/{company.id}/connectors",
            json=payload,
            headers=auth["headers"],
        )
        assert response.status_code == 201
        data = response.json()
        assert data["connector_id"] == "tg-bot-create"
        assert data["type"] == "telegram"
        assert "bot_token" not in data["config"]
        assert "id" in data

    async def test_create_wappi_connector(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
    ):
        auth = authenticated_user_with_company
        company = auth["company"]
        payload = _connector_create_payload(
            company.id,
            connector_id="wappi-create",
            type="wappi",
            channel_type="whatsapp",
            display_name="WhatsApp Bot",
            config={
                "wappi_token": "wappi-tok",
                "wappi_profile_id": "profile-1",
                "transport_endpoint": "https://wappi.example.com",
            },
        )
        response = await api_client.post(
            f"/api/v1/companies/{company.id}/connectors",
            json=payload,
            headers=auth["headers"],
        )
        assert response.status_code == 201
        data = response.json()
        assert data["connector_id"] == "wappi-create"
        assert data["type"] == "wappi"
        assert data["channel_type"] == "whatsapp"

    async def test_create_custom_connector(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
    ):
        auth = authenticated_user_with_company
        company = auth["company"]
        payload = _connector_create_payload(
            company.id,
            connector_id="custom-create",
            type="custom",
            channel_type="custom-channel",
            display_name="Customer Custom Bot",
            managed=False,
            config={},
        )
        response = await api_client.post(
            f"/api/v1/companies/{company.id}/connectors",
            json=payload,
            headers=auth["headers"],
        )
        assert response.status_code == 201
        data = response.json()
        assert data["connector_id"] == "custom-create"
        assert data["type"] == "custom"
        assert data["managed"] is False

    async def test_create_connector_without_auth(
        self,
        api_client: httpx.AsyncClient,
        company_factory,
    ):
        company = await company_factory()
        payload = _connector_create_payload(
            company.id,
            connector_id="no-auth",
            display_name="No Auth",
            config={"bot_token": "tok"},
        )
        response = await api_client.post(f"/api/v1/companies/{company.id}/connectors", json=payload)
        assert response.status_code == 401

    async def test_create_connector_validation_error(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
    ):
        auth = authenticated_user_with_company
        response = await api_client.post(
            f"/api/v1/companies/{auth['company'].id}/connectors",
            json={},
            headers=auth["headers"],
        )
        assert response.status_code == 422

    async def test_get_connector(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        authenticated_user_with_company,
    ):
        auth = authenticated_user_with_company
        company = auth["company"]
        create_payload = _connector_create_payload(
            company.id,
            connector_id="get-test",
            display_name="Get Test",
            config={"bot_token": "tok"},
        )
        create_resp = await api_client.post(
            f"/api/v1/companies/{company.id}/connectors",
            json=create_payload,
            headers=auth["headers"],
        )
        connector_id = create_resp.json()["id"]

        response = await api_client.get(f"/api/v1/transport/connectors/{connector_id}", headers=service_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["connector_id"] == "get-test"

    async def test_get_connector_not_found(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
    ):
        response = await api_client.get("/api/v1/transport/connectors/99999", headers=service_headers)
        assert response.status_code == 404

    async def test_update_connector(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
    ):
        auth = authenticated_user_with_company
        company = auth["company"]
        create_payload = _connector_create_payload(
            company.id,
            connector_id="update-test",
            display_name="Original",
            config={"bot_token": "original"},
        )
        create_resp = await api_client.post(
            f"/api/v1/companies/{company.id}/connectors",
            json=create_payload,
            headers=auth["headers"],
        )
        connector_id = create_resp.json()["id"]

        update_payload = {"display_name": "Updated", "enabled": False}
        response = await api_client.patch(
            f"/api/v1/transport/connectors/{connector_id}",
            json=update_payload,
            headers=auth["headers"],
        )
        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "Updated"
        assert data["enabled"] is False

    async def test_update_connector_not_found(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
    ):
        response = await api_client.patch(
            "/api/v1/transport/connectors/99999",
            json={"display_name": "X"},
            headers=authenticated_user_with_company["headers"],
        )
        assert response.status_code == 404

    async def test_delete_connector(
        self,
        api_client: httpx.AsyncClient,
        service_headers,
        authenticated_user_with_company,
    ):
        auth = authenticated_user_with_company
        company = auth["company"]
        create_payload = _connector_create_payload(
            company.id,
            connector_id="delete-test",
            display_name="Delete Me",
            config={"bot_token": "tok"},
        )
        create_resp = await api_client.post(
            f"/api/v1/companies/{company.id}/connectors",
            json=create_payload,
            headers=auth["headers"],
        )
        connector_id = create_resp.json()["id"]

        response = await api_client.delete(
            f"/api/v1/transport/connectors/{connector_id}",
            headers=auth["headers"],
        )
        assert response.status_code == 204

        get_resp = await api_client.get(f"/api/v1/transport/connectors/{connector_id}", headers=service_headers)
        assert get_resp.status_code == 404

    async def test_delete_connector_not_found(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
    ):
        response = await api_client.delete(
            "/api/v1/transport/connectors/99999",
            headers=authenticated_user_with_company["headers"],
        )
        assert response.status_code == 404


class TestApiKeyEndpoints:
    """Tests for API key management endpoints."""

    async def test_create_api_key(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
    ):
        auth = authenticated_user_with_company
        company = auth["company"]
        connector = await Connector.create(
            connector_id="api-key-endpoint",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="API Key Test",
            managed=False,
            config={},
        )
        response = await api_client.post(
            f"/api/v1/transport/connectors/{connector.id}/api-keys",
            headers=auth["headers"],
        )
        assert response.status_code == 201
        data = response.json()
        assert data["raw_key"].startswith("sk_")
        assert data["connector_id"] == "api-key-endpoint"

    async def test_list_api_keys(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
    ):
        auth = authenticated_user_with_company
        company = auth["company"]
        connector = await Connector.create(
            connector_id="list-keys-endpoint",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="List Keys Test",
            managed=False,
            config={},
        )
        await api_client.post(
            f"/api/v1/transport/connectors/{connector.id}/api-keys",
            headers=auth["headers"],
        )
        await api_client.post(
            f"/api/v1/transport/connectors/{connector.id}/api-keys",
            headers=auth["headers"],
        )

        response = await api_client.get(
            f"/api/v1/transport/connectors/{connector.id}/api-keys",
            headers=auth["headers"],
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    async def test_delete_api_key(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
    ):
        auth = authenticated_user_with_company
        company = auth["company"]
        connector = await Connector.create(
            connector_id="delete-key-endpoint",
            company=company,
            type=ConnectorType.CUSTOM,
            channel_type="custom",
            display_name="Delete Key Test",
            managed=False,
            config={},
        )
        create_resp = await api_client.post(
            f"/api/v1/transport/connectors/{connector.id}/api-keys",
            headers=auth["headers"],
        )
        key_id = create_resp.json()["id"]

        response = await api_client.delete(
            f"/api/v1/transport/connectors/{connector.id}/api-keys/{key_id}",
            headers=auth["headers"],
        )
        assert response.status_code == 204


class TestConfigValidation:
    """Tests for connector config validation."""

    async def test_telegram_config_validation_missing_bot_token(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
    ):
        auth = authenticated_user_with_company
        payload = _connector_create_payload(
            auth["company"].id,
            connector_id="tg-invalid",
            display_name="Invalid Config",
            config={},  # Missing bot_token
        )
        response = await api_client.post(
            f"/api/v1/companies/{auth['company'].id}/connectors",
            json=payload,
            headers=auth["headers"],
        )
        assert response.status_code == 422

    async def test_wappi_config_validation_missing_fields(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
    ):
        auth = authenticated_user_with_company
        payload = _connector_create_payload(
            auth["company"].id,
            connector_id="wappi-invalid",
            type="wappi",
            channel_type="whatsapp",
            display_name="Invalid Config",
            config={"wappi_token": "tok"},  # Missing wappi_profile_id
        )
        response = await api_client.post(
            f"/api/v1/companies/{auth['company'].id}/connectors",
            json=payload,
            headers=auth["headers"],
        )
        assert response.status_code == 422

    async def test_custom_connector_empty_config_allowed(
        self,
        api_client: httpx.AsyncClient,
        authenticated_user_with_company,
    ):
        auth = authenticated_user_with_company
        payload = _connector_create_payload(
            auth["company"].id,
            connector_id="custom-valid",
            type="custom",
            channel_type="any",
            display_name="Valid Custom",
            managed=False,
            config={},
        )
        response = await api_client.post(
            f"/api/v1/companies/{auth['company'].id}/connectors",
            json=payload,
            headers=auth["headers"],
        )
        assert response.status_code == 201
