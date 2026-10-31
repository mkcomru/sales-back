"""Tests for request_handoff endpoint."""

from __future__ import annotations

import pytest

from src.backend.modules.chat.models import AssistantMode, Customer, Thread, ThreadState
from src.backend.modules.companies.models import Company
from src.backend.modules.orders.models import Order
from src.backend.modules.users.models import CompanyUser, User, UserRole


@pytest.fixture
async def customer(company: Company) -> Customer:
    """Create test customer."""
    return await Customer.create(
        user_id="test-customer",
        company_id=company.id,
        name="Test Customer",
        meta={},
    )


@pytest.fixture
async def manager(company: Company) -> CompanyUser:
    """Create test manager with schedule."""
    user = await User.create(
        first_name="Manager",
        last_name="User",
        email="manager@test.com",
        hashed_password="hashed",  # pragma: allowlist secret
    )
    work_schedule = {
        "version": 1,
        "timezone": "Europe/Moscow",
        "weekly": {
            "mon": [{"start": "09:00", "end": "18:00"}],
            "tue": [{"start": "09:00", "end": "18:00"}],
            "wed": [{"start": "09:00", "end": "18:00"}],
            "thu": [{"start": "09:00", "end": "18:00"}],
            "fri": [{"start": "09:00", "end": "18:00"}],
            "sat": [],
            "sun": [],
        },
    }
    return await CompanyUser.create(
        user=user,
        company=company,
        role=UserRole.MANAGER,
        work_schedule=work_schedule,
        is_available=True,
    )


@pytest.fixture
async def order(company: Company, customer: Customer) -> Order:
    """Create test order."""
    from src.backend.modules.orders.repository import OrdersRepository

    orders_repo = OrdersRepository()
    order_number = await orders_repo.get_next_order_number(company.id)
    return await orders_repo.create_order(
        company_id=company.id,
        customer_id=customer.id,
        order_number=order_number,
    )


@pytest.fixture
async def thread(company: Company, customer: Customer, order: Order) -> Thread:
    """Create test thread with order."""
    return await Thread.create(
        thread_id="test-thread-123",
        customer=customer,
        company=company,
        active_order=order,
        channel_type="telegram",
        conversation_id="conv-123",
        state=ThreadState.ACTIVE,
        assistant_mode=AssistantMode.ACTIVE,
    )


@pytest.mark.asyncio
class TestRequestHandoffEndpoint:
    """Test POST /internal/orders/{order_id}/handoff endpoint."""

    async def test_request_handoff_success(
        self, api_client, order: Order, manager: CompanyUser, thread: Thread, service_headers
    ) -> None:
        response = await api_client.post(
            f"/api/v1/internal/orders/{order.id}/handoff",
            json={"summary": "Test summary", "reason": "Test reason"},
            headers=service_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["manager"] is not None
        assert data["manager"]["id"] == manager.id
        assert data["availability"] is not None
        assert "message_hint" in data

    async def test_request_handoff_assigns_manager(
        self, api_client, order: Order, manager: CompanyUser, service_headers
    ) -> None:
        assert order.assignee_id is None

        response = await api_client.post(
            f"/api/v1/internal/orders/{order.id}/handoff",
            json={"summary": "Test", "reason": "Test"},
            headers=service_headers,
        )

        assert response.status_code == 200
        await order.refresh_from_db()
        assert order.assignee_id == manager.id

    async def test_request_handoff_deactivates_ai(
        self, api_client, order: Order, manager: CompanyUser, thread: Thread, service_headers
    ) -> None:
        assert thread.assistant_mode == AssistantMode.ACTIVE
        assert thread.state == ThreadState.ACTIVE

        await api_client.post(
            f"/api/v1/internal/orders/{order.id}/handoff",
            json={"summary": "Test", "reason": "Test"},
            headers=service_headers,
        )

        await thread.refresh_from_db()
        assert thread.assistant_mode == AssistantMode.SHADOWING
        assert thread.state == ThreadState.HANDOFF

    async def test_request_handoff_no_available_managers(
        self, api_client, order: Order, company: Company, customer: Customer, service_headers
    ) -> None:
        thread = await Thread.create(
            thread_id="handoff-no-mgr-thread",
            customer=customer,
            company=company,
            active_order=order,
            channel_type="telegram",
            conversation_id="conv-no-mgr",
            state=ThreadState.ACTIVE,
            assistant_mode=AssistantMode.ACTIVE,
        )

        response = await api_client.post(
            f"/api/v1/internal/orders/{order.id}/handoff",
            json={"summary": "Test", "reason": "Test"},
            headers=service_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["manager"] is None

        await thread.refresh_from_db()
        assert thread.assistant_mode == AssistantMode.ACTIVE
        assert thread.state == ThreadState.ACTIVE

    async def test_request_handoff_order_not_found(self, api_client, service_headers) -> None:
        response = await api_client.post(
            "/api/v1/internal/orders/99999/handoff",
            json={"summary": "Test", "reason": "Test"},
            headers=service_headers,
        )

        assert response.status_code == 404

    async def test_request_handoff_requires_service_key(self, api_client, order: Order) -> None:
        response = await api_client.post(
            f"/api/v1/internal/orders/{order.id}/handoff",
            json={"summary": "Test", "reason": "Test"},
        )

        assert response.status_code == 401

    async def test_request_handoff_updates_last_assigned_at(
        self, api_client, order: Order, manager: CompanyUser, service_headers
    ) -> None:
        from datetime import UTC, datetime

        assert manager.last_assigned_at is None

        await api_client.post(
            f"/api/v1/internal/orders/{order.id}/handoff",
            json={"summary": "Test", "reason": "Test"},
            headers=service_headers,
        )

        await manager.refresh_from_db()
        assert manager.last_assigned_at is not None
        assert manager.last_assigned_at <= datetime.now(UTC)
