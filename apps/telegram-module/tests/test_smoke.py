from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_endpoint_returns_ok(api_client: TestClient):
    response = api_client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_endpoint_no_auth_required(api_client: TestClient):
    response = api_client.get("/healthz")
    assert response.status_code == 200
