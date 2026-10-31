"""Router tests for billing endpoints."""

from __future__ import annotations

import httpx
import pytest

from src.backend.modules.billing.models import CompanyBalance, OperationType
from src.backend.modules.billing.service import BillingService


@pytest.mark.asyncio
async def test_top_up_success(
    api_client: httpx.AsyncClient,
    authenticated_user_with_company: dict,
    superuser_headers: dict[str, str],
):
    """Test successful top-up via API."""
    company = authenticated_user_with_company["company"]
    headers = superuser_headers

    payload = {
        "amount": 50,
        "comment": "Test top-up",
    }

    response = await api_client.post(
        f"/api/v1/companies/{company.id}/billing/top-up",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["new_balance"] == 50
    assert data["amount_added"] == 50
    assert data["balance_id"] is not None
    assert data["ledger_entry_id"] is not None

    balance = await CompanyBalance.get(company_id=company.id)
    assert balance.balance == 50


@pytest.mark.asyncio
async def test_top_up_invalid_amount_zero(
    api_client: httpx.AsyncClient,
    authenticated_user_with_company: dict,
    superuser_headers: dict[str, str],
):
    """Test top-up fails with zero amount."""
    company = authenticated_user_with_company["company"]
    headers = superuser_headers

    payload = {
        "amount": 0,
        "comment": "Invalid top-up",
    }

    response = await api_client.post(
        f"/api/v1/companies/{company.id}/billing/top-up",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_top_up_invalid_amount_negative(
    api_client: httpx.AsyncClient,
    authenticated_user_with_company: dict,
    superuser_headers: dict[str, str],
):
    """Test top-up fails with negative amount."""
    company = authenticated_user_with_company["company"]
    headers = superuser_headers

    payload = {
        "amount": -10,
        "comment": "Invalid top-up",
    }

    response = await api_client.post(
        f"/api/v1/companies/{company.id}/billing/top-up",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_top_up_increments_existing_balance(
    api_client: httpx.AsyncClient,
    authenticated_user_with_company: dict,
    company_with_balance: tuple,
    superuser_headers: dict[str, str],
):
    """Test top-up increments existing balance."""
    company, balance = company_with_balance
    headers = superuser_headers

    initial_balance = balance.balance
    amount = 25

    payload = {
        "amount": amount,
        "comment": "Additional top-up",
    }

    response = await api_client.post(
        f"/api/v1/companies/{company.id}/billing/top-up",
        json=payload,
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["new_balance"] == initial_balance + amount

    updated_balance = await CompanyBalance.get(company_id=company.id)
    assert updated_balance.balance == initial_balance + amount


@pytest.mark.asyncio
async def test_get_balance_success(
    api_client: httpx.AsyncClient,
    authenticated_user_with_company: dict,
    company_with_balance: tuple,
):
    """Test get balance endpoint."""
    company, balance = company_with_balance
    company_user = authenticated_user_with_company["company_user"]
    company_user.company_id = company.id
    await company_user.save()
    headers = authenticated_user_with_company["headers"]

    response = await api_client.get(
        f"/api/v1/companies/{company.id}/billing/balance",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["company_id"] == company.id
    assert data["balance"] == balance.balance
    assert data["balance_warning"] is False
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_get_balance_zero_warning(
    api_client: httpx.AsyncClient,
    authenticated_user_with_company: dict,
    company_with_zero_balance: tuple,
):
    """Test get balance returns warning when balance is zero."""
    company, _ = company_with_zero_balance
    company_user = authenticated_user_with_company["company_user"]
    company_user.company_id = company.id
    await company_user.save()
    headers = authenticated_user_with_company["headers"]

    response = await api_client.get(
        f"/api/v1/companies/{company.id}/billing/balance",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["balance"] == 0
    assert data["balance_warning"] is True


@pytest.mark.asyncio
async def test_get_ledger_empty(
    api_client: httpx.AsyncClient,
    authenticated_user_with_company: dict,
):
    """Test get ledger returns empty list for new company."""
    company = authenticated_user_with_company["company"]
    headers = authenticated_user_with_company["headers"]

    response = await api_client.get(
        f"/api/v1/companies/{company.id}/billing/ledger",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["entries"]) == 0
    assert data["limit"] == 50
    assert data["offset"] == 0


@pytest.mark.asyncio
async def test_get_ledger_with_entries(
    api_client: httpx.AsyncClient,
    authenticated_user_with_company: dict,
    billing_service: BillingService,
):
    """Test get ledger returns entries."""
    company = authenticated_user_with_company["company"]
    headers = authenticated_user_with_company["headers"]

    await billing_service.top_up(
        company_id=company.id,
        amount=100,
        comment="Initial top-up",
    )

    await billing_service.top_up(
        company_id=company.id,
        amount=50,
        comment="Second top-up",
    )

    response = await api_client.get(
        f"/api/v1/companies/{company.id}/billing/ledger",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["entries"]) == 2
    assert all(entry["operation_type"] == OperationType.TOP_UP.value for entry in data["entries"])


@pytest.mark.asyncio
async def test_get_ledger_filter_operation_type(
    api_client: httpx.AsyncClient,
    authenticated_user_with_company: dict,
    billing_service: BillingService,
    order_with_customer: tuple,
):
    """Test get ledger filters by operation_type."""
    company = authenticated_user_with_company["company"]
    headers = authenticated_user_with_company["headers"]
    order, _, _ = order_with_customer
    order.company_id = company.id
    await order.save()

    await billing_service.top_up(
        company_id=company.id,
        amount=100,
        comment="Top-up",
    )

    await billing_service.charge_for_order(
        company_id=company.id,
        order_id=order.id,
        channel_type="telegram",
        conversation_id="conv-123",
    )

    response = await api_client.get(
        f"/api/v1/companies/{company.id}/billing/ledger",
        params={"operation_type": OperationType.CHARGE.value},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["entries"]) == 1
    assert data["entries"][0]["operation_type"] == OperationType.CHARGE.value


@pytest.mark.asyncio
async def test_get_ledger_pagination(
    api_client: httpx.AsyncClient,
    authenticated_user_with_company: dict,
    billing_service: BillingService,
):
    """Test get ledger pagination."""
    company = authenticated_user_with_company["company"]
    headers = authenticated_user_with_company["headers"]

    for i in range(15):
        await billing_service.top_up(
            company_id=company.id,
            amount=10,
            comment=f"Top-up {i}",
        )

    response_page1 = await api_client.get(
        f"/api/v1/companies/{company.id}/billing/ledger",
        params={"limit": 10, "offset": 0},
        headers=headers,
    )

    assert response_page1.status_code == 200
    data_page1 = response_page1.json()
    assert data_page1["total"] == 15
    assert len(data_page1["entries"]) == 10
    assert data_page1["limit"] == 10
    assert data_page1["offset"] == 0

    response_page2 = await api_client.get(
        f"/api/v1/companies/{company.id}/billing/ledger",
        params={"limit": 10, "offset": 10},
        headers=headers,
    )

    assert response_page2.status_code == 200
    data_page2 = response_page2.json()
    assert data_page2["total"] == 15
    assert len(data_page2["entries"]) == 5
    assert data_page2["limit"] == 10
    assert data_page2["offset"] == 10


@pytest.mark.asyncio
async def test_get_ledger_filter_order_id(
    api_client: httpx.AsyncClient,
    authenticated_user_with_company: dict,
    billing_service: BillingService,
    order_with_customer: tuple,
):
    """Test get ledger filters by order_id."""
    company = authenticated_user_with_company["company"]
    headers = authenticated_user_with_company["headers"]
    order, _, _ = order_with_customer
    order.company_id = company.id
    await order.save()

    await billing_service.top_up(
        company_id=company.id,
        amount=100,
        comment="Top-up",
    )

    await billing_service.charge_for_order(
        company_id=company.id,
        order_id=order.id,
        channel_type="telegram",
        conversation_id="conv-123",
    )

    response = await api_client.get(
        f"/api/v1/companies/{company.id}/billing/ledger",
        params={"order_id": order.id},
        headers=headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["entries"]) == 1
    assert data["entries"][0]["order_id"] == order.id
