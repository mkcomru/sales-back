"""Tests for notification hooks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.backend.modules.chat.models import Customer
from src.backend.modules.companies.models import Company
from src.backend.modules.orders.hooks import on_order_assigned_outside_working_hours
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
    """Create test manager."""
    user = await User.create(
        first_name="Manager",
        last_name="User",
        email="manager@test.com",
        hashed_password="hashed",  # pragma: allowlist secret
    )
    return await CompanyUser.create(
        user=user,
        company=company,
        role=UserRole.MANAGER,
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


@pytest.mark.asyncio
class TestOnOrderAssignedOutsideWorkingHours:
    """Test on_order_assigned_outside_working_hours hook."""

    async def test_hook_is_noop_mvp(self, order: Order, manager: CompanyUser) -> None:
        next_working_time = datetime.now(UTC) + timedelta(hours=8)

        result = await on_order_assigned_outside_working_hours(
            order=order,
            manager=manager,
            next_working_time=next_working_time,
        )

        assert result is None

    async def test_hook_accepts_none_next_working_time(self, order: Order, manager: CompanyUser) -> None:
        result = await on_order_assigned_outside_working_hours(
            order=order,
            manager=manager,
            next_working_time=None,
        )

        assert result is None
