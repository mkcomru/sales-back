"""Router tests for fields."""

import httpx


async def test_list_fields_empty(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    response = await api_client.get(f"/api/v1/companies/{company_id}/fields", headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_list_fields_with_data(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    field1 = {
        "name": "Field 1",
        "question": "Question 1?",
        "type": "string",
        "required": False,
    }
    field2 = {
        "name": "Field 2",
        "question": "Question 2?",
        "type": "number",
        "required": True,
    }
    await api_client.post(f"/api/v1/companies/{company_id}/fields", json=field1, headers=auth["headers"])
    await api_client.post(f"/api/v1/companies/{company_id}/fields", json=field2, headers=auth["headers"])

    response = await api_client.get(f"/api/v1/companies/{company_id}/fields", headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    names = {item["name"] for item in data["items"]}
    assert "Field 1" in names
    assert "Field 2" in names


async def test_create_field_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    payload = {
        "name": "Test Field",
        "question": "What is your name?",
        "type": "string",
        "required": False,
    }
    response = await api_client.post(f"/api/v1/companies/{company_id}/fields", json=payload, headers=auth["headers"])
    assert response.status_code == 201
    data = response.json()
    assert isinstance(data["id"], int)
    assert data["name"] == payload["name"]
    assert data["question"] == payload["question"]
    assert data["type"] == payload["type"]
    assert data["required"] == payload["required"]


async def test_create_field_with_category(
    api_client: httpx.AsyncClient, authenticated_user_with_company, category_payload
):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    cat_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/categories",
        json=category_payload(company_id=company_id),
        headers=auth["headers"],
    )
    category_id = cat_resp.json()["id"]

    payload = {
        "name": "Category Field",
        "question": "Question?",
        "type": "string",
        "category_id": category_id,
    }
    response = await api_client.post(f"/api/v1/companies/{company_id}/fields", json=payload, headers=auth["headers"])
    assert response.status_code == 201
    data = response.json()
    assert data["category_id"] == category_id


async def test_create_field_validation_error(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    response = await api_client.post(f"/api/v1/companies/{company_id}/fields", json={}, headers=auth["headers"])
    assert response.status_code == 422


async def test_get_field_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    payload = {
        "name": "Get Field",
        "question": "Question?",
        "type": "string",
    }
    create_resp = await api_client.post(f"/api/v1/companies/{company_id}/fields", json=payload, headers=auth["headers"])
    field_id = create_resp.json()["id"]

    response = await api_client.get(f"/api/v1/companies/{company_id}/fields/{field_id}", headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == field_id
    assert data["name"] == payload["name"]


async def test_get_field_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    response = await api_client.get(f"/api/v1/companies/{company_id}/fields/99999", headers=auth["headers"])
    assert response.status_code == 404


async def test_get_field_wrong_company(api_client: httpx.AsyncClient, company_factory, settings):
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

    payload = {"name": "Field", "question": "Q?", "type": "string"}
    create_resp = await api_client.post(f"/api/v1/companies/{company1.id}/fields", json=payload, headers=headers)
    field_id = create_resp.json()["id"]

    response = await api_client.get(f"/api/v1/companies/{company2.id}/fields/{field_id}", headers=headers)
    assert response.status_code == 404


async def test_update_field_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    payload = {
        "name": "Original",
        "question": "Original?",
        "type": "string",
    }
    create_resp = await api_client.post(f"/api/v1/companies/{company_id}/fields", json=payload, headers=auth["headers"])
    field_id = create_resp.json()["id"]

    update_payload = {"name": "Updated", "question": "Updated?"}
    response = await api_client.patch(
        f"/api/v1/companies/{company_id}/fields/{field_id}",
        json=update_payload,
        headers=auth["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated"
    assert data["question"] == "Updated?"
    assert data["type"] == payload["type"]


async def test_update_field_change_type(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    payload = {
        "name": "Field",
        "question": "Question?",
        "type": "string",
    }
    create_resp = await api_client.post(f"/api/v1/companies/{company_id}/fields", json=payload, headers=auth["headers"])
    field_id = create_resp.json()["id"]

    update_payload = {"type": "number"}
    response = await api_client.patch(
        f"/api/v1/companies/{company_id}/fields/{field_id}",
        json=update_payload,
        headers=auth["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "number"


async def test_update_field_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    update_payload = {"name": "Updated"}
    response = await api_client.patch(
        f"/api/v1/companies/{company_id}/fields/99999",
        json=update_payload,
        headers=auth["headers"],
    )
    assert response.status_code == 404


async def test_delete_field_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    payload = {
        "name": "Delete Field",
        "question": "Question?",
        "type": "string",
    }
    create_resp = await api_client.post(f"/api/v1/companies/{company_id}/fields", json=payload, headers=auth["headers"])
    field_id = create_resp.json()["id"]

    response = await api_client.delete(f"/api/v1/companies/{company_id}/fields/{field_id}", headers=auth["headers"])
    assert response.status_code == 204

    get_response = await api_client.get(f"/api/v1/companies/{company_id}/fields/{field_id}", headers=auth["headers"])
    assert get_response.status_code == 404


async def test_delete_field_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    response = await api_client.delete(f"/api/v1/companies/{company_id}/fields/99999", headers=auth["headers"])
    assert response.status_code == 404


async def test_list_field_options_empty(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    field_payload = {"name": "Field", "question": "Q?", "type": "enum"}
    create_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/fields",
        json=field_payload,
        headers=auth["headers"],
    )
    field_id = create_resp.json()["id"]

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

    field_payload = {"name": "Field", "question": "Q?", "type": "enum"}
    create_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/fields",
        json=field_payload,
        headers=auth["headers"],
    )
    field_id = create_resp.json()["id"]

    option_payload = {"value": "Option 1", "order": 1}
    response = await api_client.post(
        f"/api/v1/companies/{company_id}/fields/{field_id}/options",
        json=option_payload,
        headers=auth["headers"],
    )
    assert response.status_code == 201
    data = response.json()
    assert isinstance(data["id"], int)
    assert data["value"] == option_payload["value"]
    assert data["order"] == option_payload["order"]


async def test_update_field_option_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    field_payload = {"name": "Field", "question": "Q?", "type": "enum"}
    create_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/fields",
        json=field_payload,
        headers=auth["headers"],
    )
    field_id = create_resp.json()["id"]

    option_payload = {"value": "Original", "order": 1}
    option_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/fields/{field_id}/options",
        json=option_payload,
        headers=auth["headers"],
    )
    option_id = option_resp.json()["id"]

    update_payload = {"value": "Updated", "order": 2}
    response = await api_client.patch(
        f"/api/v1/companies/{company_id}/fields/{field_id}/options/{option_id}",
        json=update_payload,
        headers=auth["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert data["value"] == "Updated"
    assert data["order"] == 2


async def test_delete_field_option_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    field_payload = {"name": "Field", "question": "Q?", "type": "enum"}
    create_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/fields",
        json=field_payload,
        headers=auth["headers"],
    )
    field_id = create_resp.json()["id"]

    option_payload = {"value": "Option", "order": 1}
    option_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/fields/{field_id}/options",
        json=option_payload,
        headers=auth["headers"],
    )
    option_id = option_resp.json()["id"]

    response = await api_client.delete(
        f"/api/v1/companies/{company_id}/fields/{field_id}/options/{option_id}",
        headers=auth["headers"],
    )
    assert response.status_code == 204

    get_response = await api_client.get(
        f"/api/v1/companies/{company_id}/fields/{field_id}/options",
        headers=auth["headers"],
    )
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_list_fields_filter_by_level_customer(api_client: httpx.AsyncClient, authenticated_user_with_company):
    """Test filtering fields by level=customer."""
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    # Create customer-level field
    customer_field = {
        "name": "phone",
        "question": "What is your phone?",
        "type": "string",
        "level": "customer",
    }
    await api_client.post(f"/api/v1/companies/{company_id}/fields", json=customer_field, headers=auth["headers"])

    # Create order-level field
    order_field = {
        "name": "budget",
        "question": "What is your budget?",
        "type": "number",
        "level": "order",
    }
    await api_client.post(f"/api/v1/companies/{company_id}/fields", json=order_field, headers=auth["headers"])

    # Filter by customer level
    response = await api_client.get(f"/api/v1/companies/{company_id}/fields?level=customer", headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "phone"
    assert data["items"][0]["level"] == "customer"


async def test_list_fields_filter_by_level_order(api_client: httpx.AsyncClient, authenticated_user_with_company):
    """Test filtering fields by level=order."""
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    # Create customer-level field
    customer_field = {
        "name": "phone",
        "question": "What is your phone?",
        "type": "string",
        "level": "customer",
    }
    await api_client.post(f"/api/v1/companies/{company_id}/fields", json=customer_field, headers=auth["headers"])

    # Create order-level field
    order_field = {
        "name": "budget",
        "question": "What is your budget?",
        "type": "number",
        "level": "order",
    }
    await api_client.post(f"/api/v1/companies/{company_id}/fields", json=order_field, headers=auth["headers"])

    # Filter by order level
    response = await api_client.get(f"/api/v1/companies/{company_id}/fields?level=order", headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "budget"
    assert data["items"][0]["level"] == "order"


async def test_list_fields_without_level_returns_all(api_client: httpx.AsyncClient, authenticated_user_with_company):
    """Test that listing fields without level parameter returns all fields."""
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    # Create customer-level field
    customer_field = {
        "name": "phone",
        "question": "What is your phone?",
        "type": "string",
        "level": "customer",
    }
    await api_client.post(f"/api/v1/companies/{company_id}/fields", json=customer_field, headers=auth["headers"])

    # Create order-level field
    order_field = {
        "name": "budget",
        "question": "What is your budget?",
        "type": "number",
        "level": "order",
    }
    await api_client.post(f"/api/v1/companies/{company_id}/fields", json=order_field, headers=auth["headers"])

    # List all fields without level filter
    response = await api_client.get(f"/api/v1/companies/{company_id}/fields", headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    names = {item["name"] for item in data["items"]}
    assert "phone" in names
    assert "budget" in names
