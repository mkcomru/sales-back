from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.backend.integrations.yclients.client import YClientsClient, YClientsError
from src.backend.integrations.yclients.config import YClientsConfig, YClientsCredentials
from src.backend.integrations.yclients.schemas import YClientsBookingDates, YClientsBookingResult
from src.backend.modules.integrations.dependencies import _integration_service


class _FakeIntegrationService:
    def __init__(self, client: YClientsClient) -> None:
        self._client = client

    async def resolve_by_capability(self, company_id: int, capability: object) -> object:
        return SimpleNamespace(company_id=company_id, capability=capability)

    @asynccontextmanager
    async def build_client(self, integration: object):
        yield self._client


def _make_yclients_client() -> YClientsClient:
    return YClientsClient(
        credentials=YClientsCredentials(partner_token="test-token"),
        config=YClientsConfig(yclients_company_id=1221062),
    )


@pytest.mark.asyncio
async def test_get_available_dates_returns_booking_dates(api_client, service_headers) -> None:
    client = _make_yclients_client()
    client.get_available_dates = AsyncMock(  # type: ignore[method-assign]
        return_value=YClientsBookingDates(
            booking_dates=["2026-03-12", "2026-03-13"],
            working_dates=["2026-03-12", "2026-03-13", "2026-03-14"],
        )
    )

    api_client._transport.app.dependency_overrides[_integration_service] = lambda: _FakeIntegrationService(client)
    try:
        response = await api_client.post(
            "/api/v1/internal/capabilities/scheduling/dates",
            headers=service_headers,
            json={"company_id": 1, "staff_id": 3676906, "service_ids": [18277420]},
        )
    finally:
        api_client._transport.app.dependency_overrides.pop(_integration_service, None)

    assert response.status_code == 200
    assert response.json() == {"dates": ["2026-03-12", "2026-03-13"]}
    client.get_available_dates.assert_awaited_once_with(staff_id=3676906, service_ids=[18277420])


@pytest.mark.asyncio
async def test_create_booking_checks_slot_before_booking(api_client, service_headers) -> None:
    client = _make_yclients_client()
    client.check_booking = AsyncMock(return_value=None)  # type: ignore[method-assign]
    client.create_booking = AsyncMock(  # type: ignore[method-assign]
        return_value=[YClientsBookingResult(id=1, record_id=1563410415, record_hash="hash-1")]
    )

    api_client._transport.app.dependency_overrides[_integration_service] = lambda: _FakeIntegrationService(client)
    try:
        response = await api_client.post(
            "/api/v1/internal/capabilities/scheduling/bookings",
            headers=service_headers,
            json={
                "company_id": 1,
                "phone": "+79001234567",
                "fullname": "Test User",
                "appointments": [
                    {
                        "service_ids": [18850082],
                        "staff_id": 3676906,
                        "datetime": "2026-03-12 16:30",
                    }
                ],
            },
        )
    finally:
        api_client._transport.app.dependency_overrides.pop(_integration_service, None)

    assert response.status_code == 200
    assert response.json() == {"bookings": [{"record_id": 1563410415, "record_hash": "hash-1"}]}
    client.check_booking.assert_awaited_once()
    client.create_booking.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_booking_returns_conflict_when_check_fails(api_client, service_headers) -> None:
    client = _make_yclients_client()
    client.check_booking = AsyncMock(  # type: ignore[method-assign]
        side_effect=YClientsError(status_code=200, code=None, message="slot unavailable")
    )
    client.create_booking = AsyncMock()  # type: ignore[method-assign]

    api_client._transport.app.dependency_overrides[_integration_service] = lambda: _FakeIntegrationService(client)
    try:
        response = await api_client.post(
            "/api/v1/internal/capabilities/scheduling/bookings",
            headers=service_headers,
            json={
                "company_id": 1,
                "phone": "+79001234567",
                "fullname": "Test User",
                "appointments": [
                    {
                        "service_ids": [18850082],
                        "staff_id": 3676906,
                        "datetime": "2026-03-12 16:30",
                    }
                ],
            },
        )
    finally:
        api_client._transport.app.dependency_overrides.pop(_integration_service, None)

    assert response.status_code == 409
    assert response.json() == {"detail": "slot unavailable"}
    client.create_booking.assert_not_called()


def _make_http_status_error(status_code: int = 401) -> httpx.HTTPStatusError:
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    return httpx.HTTPStatusError("Unauthorized", request=MagicMock(), response=mock_response)


@pytest.mark.asyncio
async def test_create_booking_proceeds_when_check_returns_http_error(api_client, service_headers) -> None:
    """book_check infrastructure failure (401/500) should not block booking."""
    client = _make_yclients_client()
    client.check_booking = AsyncMock(side_effect=_make_http_status_error(401))  # type: ignore[method-assign]
    client.create_booking = AsyncMock(  # type: ignore[method-assign]
        return_value=[YClientsBookingResult(id=1, record_id=999, record_hash="h")]
    )

    api_client._transport.app.dependency_overrides[_integration_service] = lambda: _FakeIntegrationService(client)
    try:
        response = await api_client.post(
            "/api/v1/internal/capabilities/scheduling/bookings",
            headers=service_headers,
            json={
                "company_id": 1,
                "phone": "+79001234567",
                "fullname": "Test User",
                "appointments": [{"service_ids": [18850082], "staff_id": 3676906, "datetime": "2026-03-12 16:30"}],
            },
        )
    finally:
        api_client._transport.app.dependency_overrides.pop(_integration_service, None)

    assert response.status_code == 200
    assert response.json() == {"bookings": [{"record_id": 999, "record_hash": "h"}]}
    client.check_booking.assert_awaited_once()
    client.create_booking.assert_awaited_once()
