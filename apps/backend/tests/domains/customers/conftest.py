"""Fixtures for customer/threads tests."""

import pytest_asyncio
from passlib.context import CryptContext

from src.backend.modules.auth.service import AuthService
from src.backend.modules.core.settings import get_settings
from src.backend.modules.users.models import CompanyUser, User, UserRole

_test_pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")


@pytest_asyncio.fixture
async def authenticated_user_with_token(company_factory):
    """Create authenticated user with access token for tests."""
    settings = get_settings()
    auth_service = AuthService(settings)

    # Create user
    hashed_password = _test_pwd_context.hash("test_password_123")
    user = await User.create(
        first_name="Test",
        last_name="Threads",
        email="test_threads@example.com",
        hashed_password=hashed_password,
        is_active=True,
        is_superuser=False,
    )

    # Create company and company_user
    company = await company_factory()

    company_user = await CompanyUser.create(
        user=user,
        company=company,
        role=UserRole.ADMIN,
    )

    # Create access token
    access_token = auth_service.create_access_token(user.id, False)

    return {
        "user": user,
        "company": company,
        "company_user": company_user,
        "token": access_token,
        "headers": {"Authorization": f"Bearer {access_token}"},
    }
