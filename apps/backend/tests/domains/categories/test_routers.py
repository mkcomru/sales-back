"""Router tests for categories."""

import httpx


async def test_list_categories_empty(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    response = await api_client.get(f"/api/v1/companies/{company_id}/categories", headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_list_categories_with_data(
    api_client: httpx.AsyncClient, authenticated_user_with_company, category_payload
):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    cat1 = category_payload(company_id=company_id, name="Category 1")
    cat2 = category_payload(company_id=company_id, name="Category 2")
    await api_client.post(f"/api/v1/companies/{company_id}/categories", json=cat1, headers=auth["headers"])
    await api_client.post(f"/api/v1/companies/{company_id}/categories", json=cat2, headers=auth["headers"])

    response = await api_client.get(f"/api/v1/companies/{company_id}/categories", headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    names = {item["name"] for item in data["items"]}
    assert "Category 1" in names
    assert "Category 2" in names


async def test_list_categories_company_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    response = await api_client.get("/api/v1/companies/99999/categories", headers=auth["headers"])
    assert response.status_code == 404


async def test_create_category_success(
    api_client: httpx.AsyncClient, authenticated_user_with_company, category_payload
):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    payload = category_payload(company_id=company_id)
    response = await api_client.post(
        f"/api/v1/companies/{company_id}/categories", json=payload, headers=auth["headers"]
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["id"], int)
    assert data["name"] == payload["name"]
    assert data["description"] == payload["description"]
    assert data["company_id"] == company_id
    assert isinstance(data["enabled_tools"], list)


async def test_create_category_with_tools(
    api_client: httpx.AsyncClient, authenticated_user_with_company, category_payload
):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    payload = category_payload(company_id=company_id, enabled_tools=["search_kb", "handoff"])
    response = await api_client.post(
        f"/api/v1/companies/{company_id}/categories", json=payload, headers=auth["headers"]
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["enabled_tools"]) == 2
    assert "search_kb" in data["enabled_tools"]
    assert "handoff" in data["enabled_tools"]


async def test_create_category_validation_error(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    response = await api_client.post(f"/api/v1/companies/{company_id}/categories", json={}, headers=auth["headers"])
    assert response.status_code == 422


async def test_get_category_success(api_client: httpx.AsyncClient, authenticated_user_with_company, category_payload):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    payload = category_payload(company_id=company_id)
    create_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/categories", json=payload, headers=auth["headers"]
    )
    category_id = create_resp.json()["id"]

    response = await api_client.get(f"/api/v1/companies/{company_id}/categories/{category_id}", headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == category_id
    assert data["name"] == payload["name"]


async def test_get_category_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    response = await api_client.get(f"/api/v1/companies/{company_id}/categories/99999", headers=auth["headers"])
    assert response.status_code == 404
    assert "not found" in response.json()["message"].lower()


async def test_get_category_wrong_company(api_client: httpx.AsyncClient, company_factory, category_payload, settings):
    from passlib.context import CryptContext

    from src.backend.modules.auth.service import AuthService
    from src.backend.modules.users.models import CompanyUser, User, UserRole

    company1 = await company_factory(name="Company 1")
    company2 = await company_factory(name="Company 2")

    pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")
    user = await User.create(
        first_name="Test",
        last_name="User",
        email="user@test.com",
        hashed_password=pwd_context.hash("password"),
        is_active=True,
        is_superuser=False,
    )

    await CompanyUser.create(user=user, company=company1, role=UserRole.ADMIN)
    await CompanyUser.create(user=user, company=company2, role=UserRole.ADMIN)

    auth_service = AuthService(settings)
    token = auth_service.create_access_token(user.id, is_superuser=False)
    headers = {"Authorization": f"Bearer {token}"}

    payload = category_payload(company_id=company1.id)
    create_resp = await api_client.post(f"/api/v1/companies/{company1.id}/categories", json=payload, headers=headers)
    category_id = create_resp.json()["id"]

    response = await api_client.get(f"/api/v1/companies/{company2.id}/categories/{category_id}", headers=headers)
    assert response.status_code == 404


async def test_update_category_success(
    api_client: httpx.AsyncClient, authenticated_user_with_company, category_payload
):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    payload = category_payload(company_id=company_id)
    create_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/categories", json=payload, headers=auth["headers"]
    )
    category_id = create_resp.json()["id"]

    update_payload = {"name": "Updated Name", "description": "Updated Description"}
    response = await api_client.patch(
        f"/api/v1/companies/{company_id}/categories/{category_id}", json=update_payload, headers=auth["headers"]
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["description"] == "Updated Description"
    assert data["rules"] == payload["rules"]


async def test_update_category_partial(
    api_client: httpx.AsyncClient, authenticated_user_with_company, category_payload
):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    payload = category_payload(company_id=company_id)
    create_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/categories", json=payload, headers=auth["headers"]
    )
    category_id = create_resp.json()["id"]

    update_payload = {"name": "Only Name Updated"}
    response = await api_client.patch(
        f"/api/v1/companies/{company_id}/categories/{category_id}", json=update_payload, headers=auth["headers"]
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Only Name Updated"
    assert data["description"] == payload["description"]


async def test_update_category_tools(api_client: httpx.AsyncClient, authenticated_user_with_company, category_payload):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    payload = category_payload(company_id=company_id, enabled_tools=["search_kb"])
    create_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/categories", json=payload, headers=auth["headers"]
    )
    category_id = create_resp.json()["id"]

    update_payload = {"enabled_tools": ["handoff", "geo_metrics"]}
    response = await api_client.patch(
        f"/api/v1/companies/{company_id}/categories/{category_id}", json=update_payload, headers=auth["headers"]
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["enabled_tools"]) == 2
    assert "handoff" in data["enabled_tools"]
    assert "geo_metrics" in data["enabled_tools"]


async def test_update_category_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    update_payload = {"name": "Updated"}
    response = await api_client.patch(
        f"/api/v1/companies/{company_id}/categories/99999", json=update_payload, headers=auth["headers"]
    )
    assert response.status_code == 404


async def test_delete_category_success(
    api_client: httpx.AsyncClient, authenticated_user_with_company, category_payload
):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    payload = category_payload(company_id=company_id)
    create_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/categories", json=payload, headers=auth["headers"]
    )
    category_id = create_resp.json()["id"]

    response = await api_client.delete(
        f"/api/v1/companies/{company_id}/categories/{category_id}", headers=auth["headers"]
    )
    assert response.status_code == 200
    assert "deleted successfully" in response.json()["message"].lower()

    get_response = await api_client.get(
        f"/api/v1/companies/{company_id}/categories/{category_id}", headers=auth["headers"]
    )
    assert get_response.status_code == 404


async def test_delete_category_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    response = await api_client.delete(f"/api/v1/companies/{company_id}/categories/99999", headers=auth["headers"])
    assert response.status_code == 404


async def test_list_category_fields_empty(
    api_client: httpx.AsyncClient, authenticated_user_with_company, category_payload
):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    payload = category_payload(company_id=company_id)
    create_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/categories", json=payload, headers=auth["headers"]
    )
    category_id = create_resp.json()["id"]

    response = await api_client.get(
        f"/api/v1/companies/{company_id}/categories/{category_id}/fields", headers=auth["headers"]
    )
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_list_category_fields_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    response = await api_client.get(f"/api/v1/companies/{company_id}/categories/99999/fields", headers=auth["headers"])
    assert response.status_code == 404
