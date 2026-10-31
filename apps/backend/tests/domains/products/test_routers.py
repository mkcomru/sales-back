"""Router tests for products."""

import httpx


async def test_list_products_empty(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    response = await api_client.get(f"/api/v1/products?company_id={company_id}", headers=auth["headers"])
    assert response.status_code == 200
    assert response.json() == []


async def test_list_products_with_data(
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

    prod1 = {"name": "Product 1", "description": "Desc 1", "category_id": category_id}
    prod2 = {"name": "Product 2", "description": "Desc 2", "category_id": category_id}
    await api_client.post("/api/v1/products", json=prod1, headers=auth["headers"])
    await api_client.post("/api/v1/products", json=prod2, headers=auth["headers"])

    response = await api_client.get(f"/api/v1/products?company_id={company_id}", headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    names = {item["name"] for item in data}
    assert "Product 1" in names
    assert "Product 2" in names


async def test_create_product_success(api_client: httpx.AsyncClient, authenticated_user_with_company, category_payload):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    cat_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/categories",
        json=category_payload(company_id=company_id),
        headers=auth["headers"],
    )
    category_id = cat_resp.json()["id"]

    payload = {
        "name": "Test Product",
        "description": "Description",
        "category_id": category_id,
    }
    response = await api_client.post("/api/v1/products", json=payload, headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["id"], int)
    assert data["name"] == payload["name"]
    assert data["description"] == payload["description"]
    assert data["category_id"] == category_id


async def test_create_product_unauthenticated(api_client: httpx.AsyncClient):
    payload = {"name": "x", "description": "y", "category_id": 1}
    response = await api_client.post("/api/v1/products", json=payload)
    assert response.status_code == 401


async def test_create_product_validation_error(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    response = await api_client.post("/api/v1/products", json={}, headers=auth["headers"])
    assert response.status_code == 422


async def test_get_product_success(api_client: httpx.AsyncClient, authenticated_user_with_company, category_payload):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    cat_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/categories",
        json=category_payload(company_id=company_id),
        headers=auth["headers"],
    )
    category_id = cat_resp.json()["id"]

    payload = {"name": "Get Product", "description": "Desc", "category_id": category_id}
    create_resp = await api_client.post("/api/v1/products", json=payload, headers=auth["headers"])
    product_id = create_resp.json()["id"]

    response = await api_client.get(f"/api/v1/products/{product_id}", headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == product_id
    assert data["name"] == payload["name"]


async def test_get_product_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    response = await api_client.get("/api/v1/products/99999", headers=auth["headers"])
    assert response.status_code == 404
    assert "not found" in response.json()["message"].lower()


async def test_update_product_success(api_client: httpx.AsyncClient, authenticated_user_with_company, category_payload):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    cat_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/categories",
        json=category_payload(company_id=company_id),
        headers=auth["headers"],
    )
    category_id = cat_resp.json()["id"]

    payload = {
        "name": "Original",
        "description": "Original",
        "category_id": category_id,
    }
    create_resp = await api_client.post("/api/v1/products", json=payload, headers=auth["headers"])
    product_id = create_resp.json()["id"]

    update_payload = {"name": "Updated Name", "description": "Updated Description"}
    response = await api_client.patch(f"/api/v1/products/{product_id}", json=update_payload, headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["description"] == "Updated Description"
    assert data["category_id"] == category_id


async def test_update_product_partial(api_client: httpx.AsyncClient, authenticated_user_with_company, category_payload):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    cat_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/categories",
        json=category_payload(company_id=company_id),
        headers=auth["headers"],
    )
    category_id = cat_resp.json()["id"]

    payload = {"name": "Partial", "description": "Original", "category_id": category_id}
    create_resp = await api_client.post("/api/v1/products", json=payload, headers=auth["headers"])
    product_id = create_resp.json()["id"]

    update_payload = {"name": "Only Name Updated"}
    response = await api_client.patch(f"/api/v1/products/{product_id}", json=update_payload, headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Only Name Updated"
    assert data["description"] == "Original"


async def test_update_product_change_category(
    api_client: httpx.AsyncClient, authenticated_user_with_company, category_payload
):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    cat1_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/categories",
        json=category_payload(company_id=company_id, name="Category 1"),
        headers=auth["headers"],
    )
    category1_id = cat1_resp.json()["id"]

    cat2_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/categories",
        json=category_payload(company_id=company_id, name="Category 2"),
        headers=auth["headers"],
    )
    category2_id = cat2_resp.json()["id"]

    payload = {"name": "Product", "description": "Desc", "category_id": category1_id}
    create_resp = await api_client.post("/api/v1/products", json=payload, headers=auth["headers"])
    product_id = create_resp.json()["id"]

    update_payload = {"category_id": category2_id}
    response = await api_client.patch(f"/api/v1/products/{product_id}", json=update_payload, headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert data["category_id"] == category2_id


async def test_update_product_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    update_payload = {"name": "Updated"}
    response = await api_client.patch("/api/v1/products/99999", json=update_payload, headers=auth["headers"])
    assert response.status_code == 404


async def test_delete_product_success(api_client: httpx.AsyncClient, authenticated_user_with_company, category_payload):
    auth = authenticated_user_with_company
    company_id = auth["company"].id

    cat_resp = await api_client.post(
        f"/api/v1/companies/{company_id}/categories",
        json=category_payload(company_id=company_id),
        headers=auth["headers"],
    )
    category_id = cat_resp.json()["id"]

    payload = {
        "name": "Delete Product",
        "description": "Desc",
        "category_id": category_id,
    }
    create_resp = await api_client.post("/api/v1/products", json=payload, headers=auth["headers"])
    product_id = create_resp.json()["id"]

    response = await api_client.delete(f"/api/v1/products/{product_id}", headers=auth["headers"])
    assert response.status_code == 200
    assert "deleted successfully" in response.json()["message"].lower()

    get_response = await api_client.get(f"/api/v1/products/{product_id}", headers=auth["headers"])
    assert get_response.status_code == 404


async def test_delete_product_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    response = await api_client.delete("/api/v1/products/99999", headers=auth["headers"])
    assert response.status_code == 404


async def test_get_company_products_success(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    response = await api_client.get(f"/api/v1/companies/{company_id}/products", headers=auth["headers"])
    assert response.status_code == 200
    data = response.json()
    assert "categories" in data
    assert "products" in data
    assert "fields" in data
    assert isinstance(data["categories"], list)
    assert isinstance(data["products"], list)
    assert isinstance(data["fields"], list)


async def test_get_company_products_not_found(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    response = await api_client.get("/api/v1/companies/99999/products", headers=auth["headers"])
    assert response.status_code == 404
