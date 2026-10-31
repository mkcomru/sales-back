"""Fixtures for chat module tests."""

import pytest_asyncio

from src.backend.modules.chat.models import Customer, Thread, ThreadState
from src.backend.modules.companies.models import Company
from src.backend.modules.core.settings import Settings
from src.backend.modules.users.models import CompanyUser, User, UserRole


@pytest_asyncio.fixture
async def customer(company: Company) -> Customer:
    """Create test customer."""
    return await Customer.create(
        user_id="test_user_123",
        company=company,
        quiz_answers={"name": "Иван", "phone": "+79001234567"},
        meta={"username": "ivan123"},
    )


@pytest_asyncio.fixture
async def thread(customer: Customer, company: Company) -> Thread:
    """Create test thread."""
    return await Thread.create(
        thread_id="telegram_user123_company1_abc",
        customer=customer,
        company=company,
        channel_type="telegram",
        conversation_id="user123",
        state=ThreadState.ACTIVE,
        metadata={"source": "telegram"},
    )


@pytest_asyncio.fixture
async def manager_user(company: Company) -> tuple[User, CompanyUser]:
    """Create test manager user with company access."""
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")
    hashed_password = pwd_context.hash("test_manager_password")

    user = await User.create(
        first_name="Manager",
        last_name="Test",
        email="manager@test.com",
        hashed_password=hashed_password,
        is_active=True,
        is_superuser=False,
    )

    company_user = await CompanyUser.create(
        user=user,
        company=company,
        role=UserRole.ADMIN,  # ADMIN role for access to all customers/threads
    )

    return user, company_user


@pytest_asyncio.fixture
async def manager_headers(manager_user: tuple[User, CompanyUser], settings: Settings) -> dict[str, str]:
    """Generate authorization headers for manager."""
    from src.backend.modules.auth.service import AuthService

    user, _ = manager_user
    auth_service = AuthService(settings)
    access_token = auth_service.create_access_token(user.id, is_superuser=False)
    return {"Authorization": f"Bearer {access_token}"}
