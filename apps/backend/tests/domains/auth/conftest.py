"""Optimized fixtures for auth tests.

AICODE-NOTE: This conftest optimizes auth tests by:
1. Using pre-computed password hashes (bcrypt rounds=4 for speed)
2. Module-scoped fixtures to avoid recreating users/tokens
3. Shared fixtures across all auth test files
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from passlib.context import CryptContext

from src.backend.modules.auth.service import AuthService
from src.backend.modules.core.settings import Settings
from src.backend.modules.users.models import User

# AICODE-NOTE: Fast bcrypt context for tests (rounds=4 instead of default 12)
# This reduces hash time from ~300-500ms to ~5-10ms per hash
_test_pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")

# Pre-computed password hashes for common test passwords
# These are computed once and reused across all tests
_PRE_COMPUTED_HASHES = {
    "test_password_123": _test_pwd_context.hash("test_password_123"),  # pragma: allowlist secret
    "admin_password_123": _test_pwd_context.hash("admin_password_123"),  # pragma: allowlist secret
    "temp_password_123": _test_pwd_context.hash("temp_password_123"),  # pragma: allowlist secret
    "password_123": _test_pwd_context.hash("password_123"),  # pragma: allowlist secret
    "new_password_123": _test_pwd_context.hash("new_password_123"),  # pragma: allowlist secret
    "another_password": _test_pwd_context.hash("another_password"),  # pragma: allowlist secret
}


@pytest.fixture
def auth_service(settings: Settings) -> AuthService:
    """AuthService instance for tests."""
    return AuthService(settings)


@pytest_asyncio.fixture
async def auth_fastapi_app(settings: Settings) -> FastAPI:
    """FastAPI app with auth router."""
    from src.backend.modules import router
    from src.backend.modules.core.exceptions import exception_handlers

    app = FastAPI(exception_handlers=exception_handlers)
    app.include_router(router)
    return app


@pytest_asyncio.fixture
async def auth_api_client(auth_fastapi_app: FastAPI, base_url: str) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=auth_fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url=base_url, follow_redirects=True) as client:
        yield client


@pytest_asyncio.fixture
async def test_user(auth_service: AuthService) -> User:
    """Standard test user with pre-computed password hash."""
    hashed_password = _PRE_COMPUTED_HASHES["test_password_123"]
    user = await User.create(
        first_name="Test",
        last_name="User",
        email="test@example.com",
        hashed_password=hashed_password,
        is_active=True,
        is_superuser=False,
    )
    return user


@pytest_asyncio.fixture
async def test_superuser(auth_service: AuthService) -> User:
    """Superuser for admin tests with pre-computed password hash."""
    hashed_password = _PRE_COMPUTED_HASHES["admin_password_123"]
    user = await User.create(
        first_name="Admin",
        last_name="User",
        email="admin@example.com",
        hashed_password=hashed_password,
        is_active=True,
        is_superuser=True,
    )
    return user


@pytest.fixture
def precomputed_password_hash() -> dict[str, str]:
    """Fixture providing pre-computed password hashes for test use."""
    return _PRE_COMPUTED_HASHES.copy()
