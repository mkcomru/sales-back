"""Orders test fixtures."""

from __future__ import annotations

from typing import Any

import pytest

from src.backend.modules.chat.models import Customer
from src.backend.modules.companies.models import Company
from src.backend.modules.orders.models import Order
from src.backend.modules.orders.repository import OrdersRepository
from src.backend.modules.orders.service import OrderService
from src.backend.modules.stages.models import StageTemplate
from src.backend.modules.users.models import CompanyUser, User, UserRole


@pytest.fixture
def orders_repo() -> OrdersRepository:
    """Create orders repository instance."""
    return OrdersRepository()


@pytest.fixture
def order_service(orders_repo: OrdersRepository) -> OrderService:
    """Create order service instance."""
    return OrderService()


@pytest.fixture
async def customer_with_company(company) -> tuple[Customer, Company]:
    """Create customer with company."""
    customer = await Customer.create(
        user_id="test-customer-123",
        company_id=company.id,
        name="Test Customer",
        meta={},
    )
    return customer, company


@pytest.fixture
async def order_with_customer(
    customer_with_company: tuple[Customer, Company],
    orders_repo: OrdersRepository,
) -> tuple[Order, Customer, Company]:
    """Create order with customer and company."""
    customer, company = customer_with_company
    order_number = await orders_repo.get_next_order_number(company.id)
    order = await orders_repo.create_order(
        company_id=company.id,
        customer_id=customer.id,
        order_number=order_number,
        initial_channel="telegram",
    )
    return order, customer, company


@pytest.fixture
async def manager_user(company) -> tuple[CompanyUser, User, Company]:
    """Create manager user."""
    user = await User.create(
        first_name="Manager",
        last_name="User",
        email="manager@test.com",
        hashed_password="hashed",  # pragma: allowlist secret
        is_active=True,
        is_superuser=False,
    )
    company_user = await CompanyUser.create(
        user_id=user.id,
        company_id=company.id,
        role=UserRole.ADMIN,
    )
    return company_user, user, company


@pytest.fixture
async def order_for_authenticated_user(
    authenticated_user_with_company,
    orders_repo: OrdersRepository,
) -> tuple[Order, Customer, dict[str, Any]]:
    """Create order for authenticated user's company."""
    auth_data = authenticated_user_with_company

    customer = await Customer.create(
        user_id="test-customer-auth",
        company_id=auth_data["company"].id,
        name="Auth Test Customer",
        meta={},
    )

    order_number = await orders_repo.get_next_order_number(auth_data["company"].id)
    order = await orders_repo.create_order(
        company_id=auth_data["company"].id,
        customer_id=customer.id,
        order_number=order_number,
        initial_channel="telegram",
    )

    return order, customer, auth_data


@pytest.fixture
async def clear_stages():
    """Helper fixture to clear default stages for companies."""

    async def _clear(company_id: int):
        await StageTemplate.filter(company_id=company_id).delete()

    return _clear


@pytest.fixture
async def stage_templates(company) -> list[StageTemplate]:
    """Get default stage templates created for company."""
    stages = await StageTemplate.filter(company_id=company.id).order_by("position").all()
    return stages


@pytest.fixture
async def custom_test_stages(company, clear_stages) -> list[StageTemplate]:
    """Create custom test stages with specific conditions for transition tests."""
    await clear_stages(company.id)

    stages = []

    # Stage 0: Initial stage (always matches)
    stages.append(
        await StageTemplate.create(
            company_id=company.id,
            name="Новый",
            position=0,
            color="#64748b",
            transition_condition={"$any": True},
        )
    )

    # Stage 1: Qualification (budget >= 1000)
    stages.append(
        await StageTemplate.create(
            company_id=company.id,
            name="Квалификация",
            position=1,
            color="#3b82f6",
            transition_condition={"order_fields.budget": {"$gte": 1000}},
        )
    )

    # Stage 2: Proposal (budget >= 1000 AND city exists)
    stages.append(
        await StageTemplate.create(
            company_id=company.id,
            name="Предложение",
            position=2,
            color="#f59e0b",
            transition_condition={
                "$and": [
                    {"order_fields.budget": {"$gte": 1000}},
                    {"customer_fields.city": {"$exists": True}},
                ]
            },
        )
    )

    # Stage 3: Deal Closed (final stage, no result field)
    stages.append(
        await StageTemplate.create(
            company_id=company.id,
            name="Закрыто",
            position=3,
            color="#10b981",
            is_final=True,
            auto_close=True,
            transition_condition=None,
        )
    )

    return stages
