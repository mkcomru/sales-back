"""Tests for repository encapsulation (last_assigned_at updates)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.backend.modules.chat.models import Customer
from src.backend.modules.companies.models import Company
from src.backend.modules.orders.repository import OrdersRepository
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
def orders_repo() -> OrdersRepository:
    """Create orders repository."""
    return OrdersRepository()


@pytest.mark.asyncio
class TestUpdateAssignee:
    """Test update_assignee updates last_assigned_at."""

    async def test_update_assignee_updates_last_assigned_at(
        self, orders_repo: OrdersRepository, company: Company, customer: Customer, manager: CompanyUser
    ) -> None:
        order_number = await orders_repo.get_next_order_number(company.id)
        order = await orders_repo.create_order(
            company_id=company.id,
            customer_id=customer.id,
            order_number=order_number,
        )

        assert manager.last_assigned_at is None

        before_update = datetime.now(UTC)
        await orders_repo.update_assignee(order, manager.id, author_id=None)
        after_update = datetime.now(UTC)

        await manager.refresh_from_db()
        assert manager.last_assigned_at is not None
        assert before_update <= manager.last_assigned_at <= after_update

    async def test_update_assignee_to_none_does_not_update(
        self, orders_repo: OrdersRepository, company: Company, customer: Customer, manager: CompanyUser
    ) -> None:
        order_number = await orders_repo.get_next_order_number(company.id)
        order = await orders_repo.create_order(
            company_id=company.id,
            customer_id=customer.id,
            order_number=order_number,
            assignee_id=manager.id,
        )

        await manager.refresh_from_db()
        previous_assigned_at = manager.last_assigned_at

        await orders_repo.update_assignee(order, None, author_id=None)

        await manager.refresh_from_db()
        assert manager.last_assigned_at == previous_assigned_at

    async def test_update_assignee_changes_manager_updates_both(
        self,
        orders_repo: OrdersRepository,
        company: Company,
        customer: Customer,
        manager: CompanyUser,
    ) -> None:
        user2 = await User.create(
            first_name="Manager",
            last_name="Two",
            email="manager2@test.com",
            hashed_password="hashed",  # pragma: allowlist secret
        )
        manager2 = await CompanyUser.create(
            user=user2,
            company=company,
            role=UserRole.MANAGER,
        )

        order_number = await orders_repo.get_next_order_number(company.id)
        order = await orders_repo.create_order(
            company_id=company.id,
            customer_id=customer.id,
            order_number=order_number,
            assignee_id=manager.id,
        )

        await manager.refresh_from_db()
        await manager2.refresh_from_db()
        manager1_previous = manager.last_assigned_at

        await orders_repo.update_assignee(order, manager2.id, author_id=None)

        await manager.refresh_from_db()
        await manager2.refresh_from_db()

        assert manager.last_assigned_at == manager1_previous
        assert manager2.last_assigned_at is not None


@pytest.mark.asyncio
class TestCreateOrder:
    """Test create_order updates last_assigned_at."""

    async def test_create_order_with_assignee_updates_last_assigned_at(
        self, orders_repo: OrdersRepository, company: Company, customer: Customer, manager: CompanyUser
    ) -> None:
        assert manager.last_assigned_at is None

        before_create = datetime.now(UTC)
        order_number = await orders_repo.get_next_order_number(company.id)
        await orders_repo.create_order(
            company_id=company.id,
            customer_id=customer.id,
            order_number=order_number,
            assignee_id=manager.id,
        )
        after_create = datetime.now(UTC)

        await manager.refresh_from_db()
        assert manager.last_assigned_at is not None
        assert before_create <= manager.last_assigned_at <= after_create

    async def test_create_order_without_assignee_does_not_update(
        self, orders_repo: OrdersRepository, company: Company, customer: Customer, manager: CompanyUser
    ) -> None:
        await manager.refresh_from_db()
        previous_assigned_at = manager.last_assigned_at

        order_number = await orders_repo.get_next_order_number(company.id)
        await orders_repo.create_order(
            company_id=company.id,
            customer_id=customer.id,
            order_number=order_number,
            assignee_id=None,
        )

        await manager.refresh_from_db()
        assert manager.last_assigned_at == previous_assigned_at
