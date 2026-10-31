"""Billing test fixtures."""

from __future__ import annotations

import pytest

from src.backend.modules.billing.models import CompanyBalance
from src.backend.modules.billing.repository import BillingRepository, LedgerRepository
from src.backend.modules.billing.service import BillingService
from src.backend.modules.chat.models import Customer, Thread, ThreadState
from src.backend.modules.companies.models import Company
from src.backend.modules.orders.models import Order
from src.backend.modules.orders.repository import OrdersRepository
from src.backend.modules.users.models import CompanyUser, User, UserRole


@pytest.fixture
def billing_repo() -> BillingRepository:
    """Create billing repository instance."""
    return BillingRepository()


@pytest.fixture
def ledger_repo() -> LedgerRepository:
    """Create ledger repository instance."""
    return LedgerRepository()


@pytest.fixture
def billing_service(billing_repo: BillingRepository, ledger_repo: LedgerRepository) -> BillingService:
    """Create billing service instance."""
    return BillingService(billing_repo, ledger_repo)


@pytest.fixture
async def company_with_balance(company_factory) -> tuple[Company, CompanyBalance]:
    """Create company with balance."""
    company = await company_factory()
    balance = await CompanyBalance.create(company_id=company.id, balance=10)
    return company, balance


@pytest.fixture
async def company_with_zero_balance(company_factory) -> tuple[Company, CompanyBalance]:
    """Create company with zero balance."""
    company = await company_factory()
    balance = await CompanyBalance.create(company_id=company.id, balance=0)
    return company, balance


@pytest.fixture
async def thread_with_customer(company_factory) -> tuple[Thread, Customer, Company]:
    """Create thread with customer and company."""
    company = await company_factory()
    customer = await Customer.create(
        user_id="user-123",
        company_id=company.id,
        meta={},
    )
    thread = await Thread.create(
        thread_id="thread-123",
        customer_id=customer.id,
        company_id=company.id,
        channel_type="telegram",
        conversation_id="conv-123",
        state=ThreadState.ACTIVE,
    )
    return thread, customer, company


@pytest.fixture
async def operator_user(company_factory) -> tuple[CompanyUser, User, Company]:
    """Create operator user."""
    company = await company_factory()
    user = await User.create(
        first_name="Operator",
        last_name="User",
        email="operator@test.com",
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
async def order_with_customer(company_factory) -> tuple[Order, Customer, Company]:
    """Create order with customer and company."""
    company = await company_factory()
    customer = await Customer.create(
        user_id="user-order-123",
        company_id=company.id,
        meta={},
    )
    orders_repo = OrdersRepository()
    order_number = await orders_repo.get_next_order_number(company.id)
    order = await orders_repo.create_order(
        company_id=company.id,
        customer_id=customer.id,
        order_number=order_number,
        initial_channel="telegram",
    )
    return order, customer, company
