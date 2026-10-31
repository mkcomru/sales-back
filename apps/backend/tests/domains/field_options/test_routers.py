"""Router tests for field options."""

import httpx


async def test_list_field_options_empty(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    field_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/fields",
        json={"name": "Enum Field", "question": "Q?", "type": "enum"},
        headers=auth["headers"],
    )
    field_id = field_resp.json()["id"]

    response = await api_client.get(
        f"/api/v1/companies/{company_id}/fields/{field_id}/options",
        headers=auth["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_create_field_option_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    field_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/fields",
        json={"name": "Enum Field", "question": "Q?", "type": "enum"},
        headers=auth["headers"],
    )
    field_id = field_resp.json()["id"]

    payload = {"value": "Option 1", "order": 0}
    response = await api_client.post(
        f"/api/v1/companies/{company_id}/fields/{field_id}/options",
        json=payload,
        headers=auth["headers"],
    )
    assert response.status_code == 201
    data = response.json()
    assert data["value"] == "Option 1"
    assert data["order"] == 0
    assert isinstance(data["id"], int)


async def test_create_field_option_validation_error(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    field_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/fields",
        json={"name": "Enum Field", "question": "Q?", "type": "enum"},
        headers=auth["headers"],
    )
    field_id = field_resp.json()["id"]

    response = await api_client.post(
        f"/api/v1/companies/{company_id}/fields/{field_id}/options",
        json={},
        headers=auth["headers"],
    )
    assert response.status_code == 422


async def test_update_field_option_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    field_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/fields",
        json={"name": "Enum Field", "question": "Q?", "type": "enum"},
        headers=auth["headers"],
    )
    field_id = field_resp.json()["id"]

    option_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/fields/{field_id}/options",
        json={"value": "Original", "order": 0},
        headers=auth["headers"],
    )
    option_id = option_resp.json()["id"]

    update_payload = {"value": "Updated", "order": 1}
    response = await api_client.patch(
        f"/api/v1/companies/{company_id}/fields/{field_id}/options/{option_id}",
        json=update_payload,
        headers=auth["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["value"] == "Updated"
    assert data["order"] == 1


async def test_delete_field_option_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    field_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/fields",
        json={"name": "Enum Field", "question": "Q?", "type": "enum"},
        headers=auth["headers"],
    )
    field_id = field_resp.json()["id"]

    option_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/fields/{field_id}/options",
        json={"value": "Option", "order": 0},
        headers=auth["headers"],
    )
    option_id = option_resp.json()["id"]

    response = await api_client.delete(
        f"/api/v1/companies/{company_id}/fields/{field_id}/options/{option_id}",
        headers=auth["headers"],
    )
    assert response.status_code == 204

    list_response = await api_client.get(
        f"/api/v1/companies/{company_id}/fields/{field_id}/options",
        headers=auth["headers"],
    )
    data = list_response.json()
    assert data["items"] == []
    assert data["total"] == 0
