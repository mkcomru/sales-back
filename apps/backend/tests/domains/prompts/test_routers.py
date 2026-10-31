"""Router tests for prompts."""

import httpx


async def test_list_prompts_empty(api_client: httpx.AsyncClient, superuser_headers: dict[str, str]):
    response = await api_client.get("/api/v1/prompts", headers=superuser_headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_list_prompts_forbidden_without_superuser(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    response = await api_client.get("/api/v1/prompts", headers=auth["headers"])
    assert response.status_code == 403


async def test_list_prompts_with_data(api_client: httpx.AsyncClient, superuser_headers: dict[str, str]):
    payload = {"content": "Agent prompt content"}
    await api_client.put("/api/v1/prompts/agent", json=payload, headers=superuser_headers)
    response = await api_client.get("/api/v1/prompts", headers=superuser_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    agent_types = {item["agent_type"] for item in data}
    assert "agent" in agent_types


async def test_get_prompt_success(api_client: httpx.AsyncClient, superuser_headers: dict[str, str]):
    payload = {"content": "Test prompt content"}
    await api_client.put("/api/v1/prompts/agent", json=payload, headers=superuser_headers)
    response = await api_client.get("/api/v1/prompts/agent", headers=superuser_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["agent_type"] == "agent"
    assert data["content"] == payload["content"]
    assert isinstance(data["id"], int)


async def test_get_prompt_not_found(api_client: httpx.AsyncClient, superuser_headers: dict[str, str]):
    response = await api_client.get("/api/v1/prompts/nonexistent", headers=superuser_headers)
    assert response.status_code == 422


async def test_get_prompt_invalid_agent_type(api_client: httpx.AsyncClient, superuser_headers: dict[str, str]):
    response = await api_client.get("/api/v1/prompts/invalid_type", headers=superuser_headers)
    assert response.status_code == 422


async def test_upsert_prompt_create(api_client: httpx.AsyncClient, superuser_headers: dict[str, str]):
    payload = {"content": "New prompt content"}
    response = await api_client.put("/api/v1/prompts/agent", json=payload, headers=superuser_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["agent_type"] == "agent"
    assert data["content"] == payload["content"]
    assert isinstance(data["id"], int)


async def test_upsert_prompt_update(api_client: httpx.AsyncClient, superuser_headers: dict[str, str]):
    payload1 = {"content": "Original content"}
    payload2 = {"content": "Updated content"}
    await api_client.put("/api/v1/prompts/agent", json=payload1, headers=superuser_headers)
    response = await api_client.put("/api/v1/prompts/agent", json=payload2, headers=superuser_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["agent_type"] == "agent"
    assert data["content"] == payload2["content"]


async def test_upsert_prompt_validation_error(api_client: httpx.AsyncClient, superuser_headers: dict[str, str]):
    response = await api_client.put("/api/v1/prompts/agent", json={}, headers=superuser_headers)
    assert response.status_code == 422


async def test_upsert_prompt_invalid_agent_type(api_client: httpx.AsyncClient, superuser_headers: dict[str, str]):
    payload = {"content": "Test content"}
    response = await api_client.put("/api/v1/prompts/invalid_type", json=payload, headers=superuser_headers)
    assert response.status_code == 422


async def test_delete_prompt_success(api_client: httpx.AsyncClient, superuser_headers: dict[str, str]):
    payload = {"content": "Test prompt"}
    await api_client.put("/api/v1/prompts/agent", json=payload, headers=superuser_headers)
    response = await api_client.delete("/api/v1/prompts/agent", headers=superuser_headers)
    assert response.status_code == 200
    assert "deleted successfully" in response.json()["message"].lower()
    get_response = await api_client.get("/api/v1/prompts/agent", headers=superuser_headers)
    assert get_response.status_code == 404


async def test_delete_prompt_not_found(api_client: httpx.AsyncClient, superuser_headers: dict[str, str]):
    response = await api_client.delete("/api/v1/prompts/nonexistent", headers=superuser_headers)
    assert response.status_code == 422


async def test_delete_prompt_invalid_agent_type(api_client: httpx.AsyncClient, superuser_headers: dict[str, str]):
    response = await api_client.delete("/api/v1/prompts/invalid_type", headers=superuser_headers)
    assert response.status_code == 422
