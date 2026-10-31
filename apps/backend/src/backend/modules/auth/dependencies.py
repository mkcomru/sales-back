from __future__ import annotations

import secrets
from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Path, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.backend.modules.auth.service import AuthService
from src.backend.modules.core.settings import Settings, get_settings
from src.backend.modules.users.models import CompanyUser, User, UserRole

log = structlog.get_logger(__name__)
security = HTTPBearer(auto_error=False)


def get_auth_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthService:
    return AuthService(settings)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    if not credentials:
        log.debug("auth.missing_credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
        )

    try:
        payload = auth_service.decode_token(credentials.credentials)
    except ValueError as exc:
        log.debug("auth.invalid_token")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    if payload.get("type") != "access":
        log.debug("auth.wrong_token_type")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    user_id = int(payload["sub"])
    user = await User.get_or_none(id=user_id)
    if not user:
        log.debug("auth.user_not_found", user_id=user_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if not user.is_active:
        log.debug("auth.user_inactive", user_id=user_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")

    return user


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def require_superuser(
    current_user: CurrentUserDep,
) -> User:
    if not current_user.is_superuser:
        log.debug("auth.requires_superuser", user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser access required",
        )
    return current_user


async def require_company_role(
    company_id: int,
    current_user: CurrentUserDep,
    required_role: UserRole | None = None,
) -> CompanyUser:
    from src.backend.modules.companies.models import Company

    company = await Company.get_or_none(id=company_id)
    if not company:
        log.debug("auth.company_not_found", company_id=company_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

    if current_user.is_superuser:
        company_user = await CompanyUser.filter(user_id=current_user.id, company_id=company_id).first()
        if not company_user:
            company_user = await CompanyUser.create(user_id=current_user.id, company_id=company_id, role=UserRole.OWNER)
        return company_user

    company_user = await CompanyUser.filter(user_id=current_user.id, company_id=company_id).first()
    if not company_user:
        log.debug(
            "auth.no_company_access",
            user_id=current_user.id,
            company_id=company_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this company",
        )

    if required_role:
        role_hierarchy = {
            UserRole.VIEWER: 1,
            UserRole.MANAGER: 2,
            UserRole.ADMIN: 3,
            UserRole.OWNER: 4,
        }
        if role_hierarchy.get(company_user.role, 0) < role_hierarchy.get(required_role, 99):
            log.debug(
                "auth.insufficient_role",
                user_id=current_user.id,
                company_id=company_id,
                required=required_role.value,
                actual=company_user.role.value,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {required_role.value} or higher required",
            )

    return company_user


async def require_company_viewer(
    current_user: CurrentUserDep,
    company_id: int = Path(..., ge=1),
) -> CompanyUser:
    """Require VIEWER+ access to company."""
    return await require_company_role(
        company_id=company_id,
        current_user=current_user,
        required_role=UserRole.VIEWER,
    )


async def require_company_viewer_query(
    current_user: CurrentUserDep,
    company_id: int = Query(..., ge=1),
) -> CompanyUser:
    """Require VIEWER+ access to company (company_id from query string)."""
    return await require_company_role(
        company_id=company_id,
        current_user=current_user,
        required_role=UserRole.VIEWER,
    )


async def require_company_manager(
    current_user: CurrentUserDep,
    company_id: int = Path(..., ge=1),
) -> CompanyUser:
    """Require MANAGER+ access to company."""
    return await require_company_role(
        company_id=company_id,
        current_user=current_user,
        required_role=UserRole.MANAGER,
    )


async def require_company_admin(
    current_user: CurrentUserDep,
    company_id: int = Path(..., ge=1),
) -> CompanyUser:
    """Require ADMIN+ access to company."""
    return await require_company_role(
        company_id=company_id,
        current_user=current_user,
        required_role=UserRole.ADMIN,
    )


async def require_company_owner(
    current_user: CurrentUserDep,
    company_id: int = Path(..., ge=1),
) -> CompanyUser:
    """Require OWNER access to company."""
    return await require_company_role(
        company_id=company_id,
        current_user=current_user,
        required_role=UserRole.OWNER,
    )


async def require_company_viewer_by_company_user_id(
    current_user: CurrentUserDep,
    company_user_id: int = Path(..., ge=1),
) -> CompanyUser:
    """Require VIEWER+ access to company via company_user_id."""
    company_user = await CompanyUser.get_or_none(id=company_user_id)
    if not company_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company user not found")
    return await require_company_role(
        company_id=company_user.company_id,
        current_user=current_user,
        required_role=UserRole.VIEWER,
    )


async def require_company_manager_by_company_user_id(
    current_user: CurrentUserDep,
    company_user_id: int = Path(..., ge=1),
) -> CompanyUser:
    """Require MANAGER+ access to company via company_user_id."""
    company_user = await CompanyUser.get_or_none(id=company_user_id)
    if not company_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company user not found")
    return await require_company_role(
        company_id=company_user.company_id,
        current_user=current_user,
        required_role=UserRole.MANAGER,
    )


def require_service_api_key(request: Request) -> None:
    cfg = get_settings()
    service_key = cfg.service.api_key
    if service_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service API key not configured",
        )

    header_name = cfg.service.resolved_header()
    provided = request.headers.get(header_name)
    if not provided or not secrets.compare_digest(provided, service_key.get_secret_value()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service API key",
        )


SuperuserDep = Annotated[User, Depends(require_superuser)]
CompanyViewerDep = Annotated[CompanyUser, Depends(require_company_viewer)]
CompanyViewerQueryDep = Annotated[CompanyUser, Depends(require_company_viewer_query)]
CompanyManagerDep = Annotated[CompanyUser, Depends(require_company_manager)]
CompanyAdminDep = Annotated[CompanyUser, Depends(require_company_admin)]
CompanyOwnerDep = Annotated[CompanyUser, Depends(require_company_owner)]
CompanyViewerByCompanyUserIdDep = Annotated[CompanyUser, Depends(require_company_viewer_by_company_user_id)]
CompanyManagerByCompanyUserIdDep = Annotated[CompanyUser, Depends(require_company_manager_by_company_user_id)]
