"""Router tests for prompt addons."""

import httpx

from src.backend.modules.prompt_addon.models import PromptAddon
from src.backend.modules.transport.models import Connector, ConnectorType


async def test_list_prompt_addons_empty(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    response = await api_client.get(
        f"/api/v1/companies/{auth['company'].id}/prompt-addons",
        headers=auth["headers"],
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_list_prompt_addons_with_data(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company = auth["company"]
    await PromptAddon.create(
        company=company,
        name="Addon 1",
        qualification_workflow="Workflow 1",
        qualification_examples="Examples 1",
    )
    await PromptAddon.create(
        company=company,
        name="Addon 2",
        qualification_workflow="Workflow 2",
        qualification_examples="Examples 2",
    )
    response = await api_client.get(
        f"/api/v1/companies/{company.id}/prompt-addons",
        headers=auth["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    names = {item["name"] for item in data}
    assert "Addon 1" in names
    assert "Addon 2" in names


async def test_create_prompt_addon_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company = auth["company"]
    payload = {
        "name": "New Addon",
        "qualification_workflow": "New workflow",
        "qualification_examples": "New examples",
    }
    response = await api_client.post(
        f"/api/v1/companies/{company.id}/prompt-addons",
        json=payload,
        headers=auth["headers"],
    )
    assert response.status_code == 201
    data = response.json()
    assert isinstance(data["id"], int)
    assert data["company_id"] == company.id
    assert data["name"] == payload["name"]
    assert data["qualification_workflow"] == payload["qualification_workflow"]
    assert data["qualification_examples"] == payload["qualification_examples"]


async def test_create_prompt_addon_validation_error(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company = auth["company"]
    payload = {"name": "Test"}
    response = await api_client.post(
        f"/api/v1/companies/{company.id}/prompt-addons",
        json=payload,
        headers=auth["headers"],
    )
    assert response.status_code == 422


async def test_get_prompt_addon_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company = auth["company"]
    addon = await PromptAddon.create(
        company=company,
        name="Get Test",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
    )
    response = await api_client.get(
        f"/api/v1/companies/{company.id}/prompt-addons/{addon.id}",
        headers=auth["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == addon.id
    assert data["name"] == "Get Test"
    assert data["qualification_workflow"] == "Workflow"
    assert data["qualification_examples"] == "Examples"


async def test_get_prompt_addon_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company = auth["company"]
    response = await api_client.get(
        f"/api/v1/companies/{company.id}/prompt-addons/99999",
        headers=auth["headers"],
    )
    assert response.status_code == 404


async def test_update_prompt_addon_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company = auth["company"]
    addon = await PromptAddon.create(
        company=company,
        name="Original",
        qualification_workflow="Original workflow",
        qualification_examples="Original examples",
    )
    payload = {"name": "Updated", "qualification_workflow": "Updated workflow"}
    response = await api_client.put(
        f"/api/v1/companies/{company.id}/prompt-addons/{addon.id}",
        json=payload,
        headers=auth["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated"
    assert data["qualification_workflow"] == "Updated workflow"
    assert data["qualification_examples"] == "Original examples"


async def test_update_prompt_addon_partial(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company = auth["company"]
    addon = await PromptAddon.create(
        company=company,
        name="Original",
        qualification_workflow="Original workflow",
        qualification_examples="Original examples",
    )
    payload = {"name": "Only Name Updated"}
    response = await api_client.put(
        f"/api/v1/companies/{company.id}/prompt-addons/{addon.id}",
        json=payload,
        headers=auth["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Only Name Updated"
    assert data["qualification_workflow"] == "Original workflow"
    assert data["qualification_examples"] == "Original examples"


async def test_update_prompt_addon_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company = auth["company"]
    payload = {"name": "Updated"}
    response = await api_client.put(
        f"/api/v1/companies/{company.id}/prompt-addons/99999",
        json=payload,
        headers=auth["headers"],
    )
    assert response.status_code == 404


async def test_delete_prompt_addon_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company = auth["company"]
    addon = await PromptAddon.create(
        company=company,
        name="Delete Me",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
    )
    response = await api_client.delete(
        f"/api/v1/companies/{company.id}/prompt-addons/{addon.id}",
        headers=auth["headers"],
    )
    assert response.status_code == 204

    get_response = await api_client.get(
        f"/api/v1/companies/{company.id}/prompt-addons/{addon.id}",
        headers=auth["headers"],
    )
    assert get_response.status_code == 404


async def test_delete_prompt_addon_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company = auth["company"]
    response = await api_client.delete(
        f"/api/v1/companies/{company.id}/prompt-addons/99999",
        headers=auth["headers"],
    )
    assert response.status_code == 404


async def test_update_connector_prompt_addon_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company = auth["company"]
    addon = await PromptAddon.create(
        company=company,
        name="Test Addon",
        qualification_workflow="Test workflow",
        qualification_examples="Test examples",
    )
    connector = await Connector.create(
        connector_id="test-connector",
        company=company,
        type=ConnectorType.TELEGRAM,
        channel_type="telegram",
        display_name="Test Bot",
        managed=True,
        config={"bot_token": "token"},
    )
    payload = {"prompt_addon_id": addon.id}
    response = await api_client.patch(
        f"/api/v1/companies/{company.id}/connectors/{connector.connector_id}",
        json=payload,
        headers=auth["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["prompt_addon_id"] == addon.id

    refreshed = await Connector.get(id=connector.id)
    assert refreshed.prompt_addon_id == addon.id


async def test_update_connector_prompt_addon_remove(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company = auth["company"]
    addon = await PromptAddon.create(
        company=company,
        name="Test Addon",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
    )
    connector = await Connector.create(
        connector_id="test-connector-2",
        company=company,
        type=ConnectorType.TELEGRAM,
        channel_type="telegram",
        display_name="Test Bot",
        managed=True,
        config={"bot_token": "token"},
        prompt_addon_id=addon.id,
    )
    payload = {"prompt_addon_id": None}
    response = await api_client.patch(
        f"/api/v1/companies/{company.id}/connectors/{connector.connector_id}",
        json=payload,
        headers=auth["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["prompt_addon_id"] is None

    refreshed = await Connector.get(id=connector.id)
    assert refreshed.prompt_addon_id is None


async def test_update_connector_prompt_addon_wrong_company(
    api_client: httpx.AsyncClient, authenticated_user_with_company, company_factory
):
    auth = authenticated_user_with_company
    company1 = auth["company"]
    company2 = await company_factory()
    addon = await PromptAddon.create(
        company=company2,
        name="Other Company Addon",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
    )
    connector = await Connector.create(
        connector_id="test-connector-3",
        company=company1,
        type=ConnectorType.TELEGRAM,
        channel_type="telegram",
        display_name="Test Bot",
        managed=True,
        config={"bot_token": "token"},
    )
    payload = {"prompt_addon_id": addon.id}
    response = await api_client.patch(
        f"/api/v1/companies/{company1.id}/connectors/{connector.connector_id}",
        json=payload,
        headers=auth["headers"],
    )
    assert response.status_code == 404


async def test_update_connector_prompt_addon_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company = auth["company"]
    connector = await Connector.create(
        connector_id="test-connector-4",
        company=company,
        type=ConnectorType.TELEGRAM,
        channel_type="telegram",
        display_name="Test Bot",
        managed=True,
        config={"bot_token": "token"},
    )
    payload = {"prompt_addon_id": 99999}
    response = await api_client.patch(
        f"/api/v1/companies/{company.id}/connectors/{connector.connector_id}",
        json=payload,
        headers=auth["headers"],
    )
    assert response.status_code == 404
