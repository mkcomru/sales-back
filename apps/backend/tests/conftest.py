from __future__ import annotations

import asyncio
import inspect
import os
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from importlib import import_module
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from passlib.context import CryptContext
from tortoise import Tortoise
from tortoise.models import Model

from src.backend.modules.chat.service import ChatService
from src.backend.modules.companies.models import Company
from src.backend.modules.core.settings import get_settings
from src.backend.modules.orders.service import OrderService
from src.backend.modules.users.models import User

# AICODE-NOTE: Fast bcrypt for ALL tests (4 rounds instead of default 12).
# This patches the module-level pwd_context in auth and users services.
_FAST_PWD_CONTEXT = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")


def _patch_bcrypt_globally() -> None:
    """Patch pwd_context in service modules to use fast bcrypt rounds."""
    import src.backend.modules.auth.service as auth_service
    import src.backend.modules.users.service as users_service

    auth_service.pwd_context = _FAST_PWD_CONTEXT
    users_service.pwd_context = _FAST_PWD_CONTEXT


_patch_bcrypt_globally()

TEST_DATABASE_URL = "sqlite://:memory:?cache=shared"
TEST_SERVICE_KEY = "test-service-key"  # pragma: allowlist secret
TEST_JWT_SECRET = "test-jwt-secret-key-for-testing-purposes-only"  # pragma: allowlist secret

TEST_ENCRYPTION_KEY = "test-encryption-master-key-32by!"  # pragma: allowlist secret

DEFAULT_ENV = {
    "APP__ENVIRONMENT": "test",
    "DATABASE__URL": TEST_DATABASE_URL,
    "SERVICE__API_KEY": TEST_SERVICE_KEY,
    "AUTH__JWT_SECRET_KEY": TEST_JWT_SECRET,
    "ENCRYPTION__MASTER_KEY": TEST_ENCRYPTION_KEY,
    "EVENTING__ENABLED": "false",
    "S3__ENDPOINT_URL": "http://localhost:9000",
    "S3__ACCESS_KEY_ID": "test-access-key",  # pragma: allowlist secret
    "S3__SECRET_ACCESS_KEY": "test-secret-key",  # pragma: allowlist secret
    "S3__BUCKET_NAME": "test-bucket",
}

for key, value in DEFAULT_ENV.items():
    os.environ.setdefault(key, value)


def _disable_env_files() -> None:
    import common.config as common_config

    common_config.SHARED_ENV_FILES = ()
    common_config.CommonSettingsBase.model_config["env_file"] = ()
    common_config.BackendModuleSettings._env_files = ()
    common_config.BackendModuleSettings.model_config["env_file"] = ()


_disable_env_files()


if TYPE_CHECKING:
    from src.backend.modules.core.settings import Settings

PayloadFactory = Callable[..., dict[str, Any]]
CompanyFactory = Callable[..., Awaitable[Company]]

_SQLITE_TABLES: list[str] | None = None


@pytest.fixture(scope="session")
def settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture(scope="session")
def base_url() -> str:
    return "http://testserver"


@pytest.fixture(scope="session")
def service_headers(settings: Settings) -> dict[str, str]:
    api_key = settings.service.api_key
    if api_key is None:
        raise RuntimeError("SERVICE__API_KEY must be configured for tests")
    return {settings.service.resolved_header(): api_key.get_secret_value()}


def _clear_schemas_for_sqlite() -> None:
    """Auto-discover and clear schema from all Tortoise models.

    AICODE-NOTE: SQLite doesn't support PostgreSQL schemas. This function
    automatically finds all Tortoise Model subclasses and clears their schema
    attribute, allowing models to work in both environments without manual updates.
    """
    for module_name, module in list(sys.modules.items()):
        if not module or not module_name.startswith("src."):
            continue
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, Model)
                and obj is not Model
                and not getattr(obj._meta, "abstract", False)
                and hasattr(obj._meta, "schema")
            ):
                obj._meta.schema = None


@pytest.fixture(scope="session")
def event_loop() -> AsyncIterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def tortoise_init(settings: Settings) -> AsyncIterator[None]:
    from src.backend import db

    import_module("src.backend.modules.core.models")
    _clear_schemas_for_sqlite()
    await db.init()
    await Tortoise.generate_schemas(safe=False)
    global _SQLITE_TABLES
    connection = Tortoise.get_connection("default")
    tables = await connection.execute_query_dict(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    _SQLITE_TABLES = [row["name"] for row in tables if row.get("name")]
    try:
        yield
    finally:
        await Tortoise._drop_databases()
        await db.close()


@pytest_asyncio.fixture(scope="function", autouse=True)
async def db_cleanup(settings: Settings) -> AsyncIterator[None]:
    yield

    db_url = settings.resolved_database_url
    if not db_url.startswith("sqlite"):
        raise RuntimeError(f"Backend tests expect sqlite database, got: {db_url}")

    if _SQLITE_TABLES is None:
        raise RuntimeError("SQLite table cache is not initialized; tortoise_init must run before db_cleanup")

    connection = Tortoise.get_connection("default")
    await connection.execute_query("PRAGMA foreign_keys = OFF")

    for table in _SQLITE_TABLES:
        await connection.execute_query(f'DELETE FROM "{table}"')

    sqlite_sequence = await connection.execute_query_dict(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
    )
    if sqlite_sequence:
        await connection.execute_query('DELETE FROM "sqlite_sequence"')

    await connection.execute_query("PRAGMA foreign_keys = ON")


@pytest_asyncio.fixture(scope="function")
async def fastapi_app(settings: Settings) -> AsyncIterator[FastAPI]:
    from fastapi import FastAPI

    from src.backend.modules import router
    from src.backend.modules.core.exceptions import exception_handlers

    app = FastAPI(exception_handlers=exception_handlers)
    app.include_router(router)

    @app.get("/health")
    async def check_health():
        from fastapi import status
        from fastapi.responses import Response

        return Response(status_code=status.HTTP_200_OK)

    yield app


@pytest_asyncio.fixture
async def api_client(fastapi_app: FastAPI, base_url: str) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url=base_url, follow_redirects=True) as client:
        yield client


@pytest.fixture
def chat_service() -> ChatService:
    """ChatService with injected OrderService for use in tests."""
    return ChatService(order_service=OrderService())


@pytest.fixture
def company_payload() -> PayloadFactory:
    def _factory(**overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "name": "Acme Corp",
            "description": "Leading provider of testing data.",
            "rules": "Stay professional.",
            "tone_of_voice": "Friendly",
            "assistant_name": "Pulse",
            "qualification_workflow": "Standard",
            "qualification_examples": "Example 1",
            "collection_name": "acme",
            "stages_config": [],
            "category_rules": [],
            "crm_forward_metadata_keys": [],
            "crm_default_stage_id": "PROCESSED",
            "crm_manager_attention_stage_id": None,
        }
        base.update(overrides)
        return base

    return _factory


@pytest.fixture
def category_payload() -> PayloadFactory:
    def _factory(**overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "name": "Default Category",
            "description": "Category description",
            "rules": "Standard rules",
            "examples": "Example dialog",
            "workflow": "Default workflow",
            "company_id": 1,
        }
        base.update(overrides)
        return base

    return _factory


@pytest.fixture
def product_payload() -> PayloadFactory:
    def _factory(**overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "name": "Product",
            "description": "Description",
            "category_id": None,
        }
        base.update(overrides)
        return base

    return _factory


@pytest.fixture
def company_factory(company_payload: PayloadFactory) -> CompanyFactory:
    async def _factory(**overrides: Any) -> Company:
        from src.backend.modules.stages.service import StagesService

        payload = company_payload(**overrides)
        company = await Company.create(**payload)

        # Create default stages for the company (mimics production behavior)
        await StagesService().create_default_stages(company.id)

        return company

    return _factory


@pytest_asyncio.fixture
async def company(company_factory: CompanyFactory) -> Company:
    return await company_factory()


@pytest.fixture
def company_factory_without_stages(company_payload: PayloadFactory) -> CompanyFactory:
    """Factory for creating companies without default stages (for specific tests)."""

    async def _factory(**overrides: Any) -> Company:
        payload = company_payload(**overrides)
        company = await Company.create(**payload)
        return company

    return _factory


@pytest_asyncio.fixture
async def company_without_stages(company_factory_without_stages: CompanyFactory) -> Company:
    """Company fixture without default stages."""
    return await company_factory_without_stages()


@pytest.fixture
def assert_has_int_id():
    def _assert(obj: dict[str, Any]) -> None:
        assert isinstance(obj, dict)
        assert isinstance(obj.get("id"), int)

    return _assert


@pytest_asyncio.fixture
async def test_superuser() -> User:
    """Create a superuser for tests requiring superuser access."""
    from passlib.context import CryptContext

    from src.backend.modules.users.models import User

    pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")
    hashed_password = pwd_context.hash("superuser_password_123")

    user = await User.create(
        first_name="Super",
        last_name="User",
        email="superuser@test.com",
        hashed_password=hashed_password,
        is_active=True,
        is_superuser=True,
    )
    return user


@pytest.fixture
def superuser_headers(test_superuser: User, settings: Settings) -> dict[str, str]:
    """Generate authorization headers for superuser."""
    from src.backend.modules.auth.service import AuthService

    auth_service = AuthService(settings)
    access_token = auth_service.create_access_token(test_superuser.id, is_superuser=True)
    return {"Authorization": f"Bearer {access_token}"}


@pytest_asyncio.fixture
async def authenticated_user_with_company(company_factory: CompanyFactory, settings: Settings) -> dict[str, Any]:
    """Create authenticated user with company and access token."""
    from passlib.context import CryptContext

    from src.backend.modules.auth.service import AuthService
    from src.backend.modules.users.models import CompanyUser, User, UserRole

    pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")
    hashed_password = pwd_context.hash("test_password_123")

    user = await User.create(
        first_name="Test",
        last_name="User",
        email="test_auth@example.com",
        hashed_password=hashed_password,
        is_active=True,
        is_superuser=False,
    )

    company = await company_factory()

    company_user = await CompanyUser.create(
        user=user,
        company=company,
        role=UserRole.ADMIN,
    )

    auth_service = AuthService(settings)
    access_token = auth_service.create_access_token(user.id, is_superuser=False)

    return {
        "user": user,
        "company": company,
        "company_user": company_user,
        "token": access_token,
        "headers": {"Authorization": f"Bearer {access_token}"},
    }


@pytest.fixture
def user_factory() -> Callable[..., Awaitable[User]]:
    """Factory for creating test users."""
    from passlib.context import CryptContext

    from src.backend.modules.users.models import User

    async def _factory(**overrides: Any) -> User:
        pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=4, deprecated="auto")
        hashed_password = pwd_context.hash("test_password_123")

        defaults = {
            "first_name": "Test",
            "last_name": "User",
            "email": f"test_{id(overrides)}@example.com",
            "hashed_password": hashed_password,
            "is_active": True,
            "is_superuser": False,
        }
        defaults.update(overrides)
        return await User.create(**defaults)

    return _factory
