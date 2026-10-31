"""Tests for authentication dependencies."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from src.backend.modules.auth.dependencies import (
    get_auth_service,
    get_current_user,
    require_company_role,
    require_superuser,
)
from src.backend.modules.auth.service import AuthService
from src.backend.modules.companies.models import Company
from src.backend.modules.core.settings import Settings
from src.backend.modules.users.models import CompanyUser, User, UserRole


@pytest_asyncio.fixture
async def test_company(company_factory) -> Company:
    return await company_factory(name="Test Company")


class TestGetAuthService:
    """Test get_auth_service dependency."""

    def test_get_auth_service(self, settings: Settings) -> None:
        service = get_auth_service(settings)

        assert isinstance(service, AuthService)
        assert service._secret_key == settings.auth.jwt_secret_key.get_secret_value()
        assert service._algorithm == settings.auth.jwt_algorithm


class TestGetCurrentUser:
    """Test get_current_user dependency."""

    async def test_get_current_user_success(self, test_user: User, auth_service: AuthService) -> None:
        access_token = auth_service.create_access_token(test_user.id, False)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=access_token)

        user = await get_current_user(credentials, auth_service)

        assert user.id == test_user.id
        assert user.email == test_user.email

    async def test_get_current_user_no_credentials(self, auth_service: AuthService) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(None, auth_service)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Missing authentication credentials"

    async def test_get_current_user_invalid_token(self, auth_service: AuthService) -> None:
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid_token")

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials, auth_service)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Invalid token"

    async def test_get_current_user_with_refresh_token(self, test_user: User, auth_service: AuthService) -> None:
        refresh_token, _, _ = auth_service.create_refresh_token(test_user.id)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=refresh_token)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials, auth_service)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Invalid token type"

    async def test_get_current_user_user_not_found(self, auth_service: AuthService, settings: Settings) -> None:
        from jose import jwt

        payload = {
            "sub": "999999",
            "type": "access",
            "is_superuser": False,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=15),
        }

        token = jwt.encode(
            payload,
            settings.auth.jwt_secret_key.get_secret_value(),
            algorithm=settings.auth.jwt_algorithm,
        )

        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials, auth_service)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "User not found"

    async def test_get_current_user_inactive_user(self, test_user: User, auth_service: AuthService) -> None:
        test_user.is_active = False
        await test_user.save()

        access_token = auth_service.create_access_token(test_user.id, False)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=access_token)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials, auth_service)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc_info.value.detail == "Inactive user"


class TestRequireSuperuser:
    """Test require_superuser dependency."""

    async def test_require_superuser_success(self, test_superuser: User) -> None:
        user = await require_superuser(test_superuser)

        assert user.id == test_superuser.id
        assert user.is_superuser is True

    async def test_require_superuser_not_superuser(self, test_user: User) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await require_superuser(test_user)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert exc_info.value.detail == "Superuser access required"


class TestRequireCompanyRole:
    """Test require_company_role dependency."""

    async def test_require_company_role_superuser_auto_owner(self, test_superuser: User, test_company: Company) -> None:
        company_user = await require_company_role(test_company.id, test_superuser)

        assert company_user.user_id == test_superuser.id
        assert company_user.company_id == test_company.id
        assert company_user.role == UserRole.OWNER

    async def test_require_company_role_superuser_existing_access(
        self, test_superuser: User, test_company: Company
    ) -> None:
        existing_company_user = await CompanyUser.create(
            user_id=test_superuser.id,
            company_id=test_company.id,
            role=UserRole.VIEWER,
        )

        company_user = await require_company_role(test_company.id, test_superuser)

        assert company_user.id == existing_company_user.id
        assert company_user.role == UserRole.VIEWER

    async def test_require_company_role_owner(self, test_user: User, test_company: Company) -> None:
        await CompanyUser.create(
            user_id=test_user.id,
            company_id=test_company.id,
            role=UserRole.OWNER,
        )

        company_user = await require_company_role(test_company.id, test_user)

        assert company_user.user_id == test_user.id
        assert company_user.role == UserRole.OWNER

    async def test_require_company_role_admin(self, test_user: User, test_company: Company) -> None:
        await CompanyUser.create(
            user_id=test_user.id,
            company_id=test_company.id,
            role=UserRole.ADMIN,
        )

        company_user = await require_company_role(test_company.id, test_user)

        assert company_user.user_id == test_user.id
        assert company_user.role == UserRole.ADMIN

    async def test_require_company_role_viewer(self, test_user: User, test_company: Company) -> None:
        await CompanyUser.create(
            user_id=test_user.id,
            company_id=test_company.id,
            role=UserRole.VIEWER,
        )

        company_user = await require_company_role(test_company.id, test_user)

        assert company_user.user_id == test_user.id
        assert company_user.role == UserRole.VIEWER

    async def test_require_company_role_no_access(self, test_user: User, test_company: Company) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await require_company_role(test_company.id, test_user)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert exc_info.value.detail == "No access to this company"

    async def test_require_company_role_with_required_role_owner(self, test_user: User, test_company: Company) -> None:
        await CompanyUser.create(
            user_id=test_user.id,
            company_id=test_company.id,
            role=UserRole.OWNER,
        )

        company_user = await require_company_role(test_company.id, test_user, UserRole.OWNER)

        assert company_user.role == UserRole.OWNER

    async def test_require_company_role_with_required_role_admin_has_owner(
        self, test_user: User, test_company: Company
    ) -> None:
        await CompanyUser.create(
            user_id=test_user.id,
            company_id=test_company.id,
            role=UserRole.OWNER,
        )

        company_user = await require_company_role(test_company.id, test_user, UserRole.ADMIN)

        assert company_user.role == UserRole.OWNER

    async def test_require_company_role_with_required_role_admin_has_admin(
        self, test_user: User, test_company: Company
    ) -> None:
        await CompanyUser.create(
            user_id=test_user.id,
            company_id=test_company.id,
            role=UserRole.ADMIN,
        )

        company_user = await require_company_role(test_company.id, test_user, UserRole.ADMIN)

        assert company_user.role == UserRole.ADMIN

    async def test_require_company_role_with_required_role_insufficient(
        self, test_user: User, test_company: Company
    ) -> None:
        await CompanyUser.create(
            user_id=test_user.id,
            company_id=test_company.id,
            role=UserRole.VIEWER,
        )

        with pytest.raises(HTTPException) as exc_info:
            await require_company_role(test_company.id, test_user, UserRole.ADMIN)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert exc_info.value.detail == "Role admin or higher required"

    async def test_require_company_role_hierarchy_viewer_requires_owner(
        self, test_user: User, test_company: Company
    ) -> None:
        await CompanyUser.create(
            user_id=test_user.id,
            company_id=test_company.id,
            role=UserRole.VIEWER,
        )

        with pytest.raises(HTTPException) as exc_info:
            await require_company_role(test_company.id, test_user, UserRole.OWNER)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    async def test_require_company_role_hierarchy_admin_requires_owner(
        self, test_user: User, test_company: Company
    ) -> None:
        await CompanyUser.create(
            user_id=test_user.id,
            company_id=test_company.id,
            role=UserRole.ADMIN,
        )

        with pytest.raises(HTTPException) as exc_info:
            await require_company_role(test_company.id, test_user, UserRole.OWNER)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
