"""Router tests for health endpoints."""

import httpx


async def test_health_endpoint_returns_200(api_client: httpx.AsyncClient):
    response = await api_client.get("/health")
    assert response.status_code == 200


async def test_health_endpoint_no_auth_required(api_client: httpx.AsyncClient):
    response = await api_client.get("/health")
    assert response.status_code == 200
