from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, status

from src.backend.modules.auth.dependencies import AuthServiceDep, CurrentUserDep, SuperuserDep
from src.backend.modules.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
)
from src.backend.modules.users.dependencies import UsersServiceDep
from src.backend.modules.users.models import User
from src.backend.modules.users.schemas import CreateUserRequest, UserResponse

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    auth_service: AuthServiceDep,
) -> TokenResponse:
    user = await auth_service.authenticate_user(request.email, request.password)
    if not user:
        log.warning("auth.login.failed", email=request.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    access_token = auth_service.create_access_token(user_id=user.id, is_superuser=user.is_superuser)
    refresh_token, jti, expires_at = auth_service.create_refresh_token(user_id=user.id)
    await auth_service.save_refresh_token(user.id, jti, expires_at)

    log.info("auth.login.success", user_id=user.id, email=user.email)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: RefreshRequest,
    auth_service: AuthServiceDep,
) -> TokenResponse:
    try:
        payload = auth_service.decode_token(request.refresh_token)
    except ValueError as exc:
        log.warning("auth.refresh.invalid_token")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

    if payload.get("type") != "refresh":
        log.warning("auth.refresh.wrong_token_type")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    jti = payload.get("jti")
    if not jti or not await auth_service.is_refresh_token_valid(jti):
        log.warning("auth.refresh.token_revoked_or_expired", jti=jti)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token revoked or expired",
        )

    user_id = int(payload["sub"])
    user = await User.get_or_none(id=user_id)
    if not user or not user.is_active:
        log.warning("auth.refresh.user_not_found_or_inactive", user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    await auth_service.revoke_refresh_token(jti)

    access_token = auth_service.create_access_token(user_id=user.id, is_superuser=user.is_superuser)
    new_refresh_token, new_jti, new_expires_at = auth_service.create_refresh_token(user_id=user.id)
    await auth_service.save_refresh_token(user.id, new_jti, new_expires_at)

    log.info("auth.refresh.success", user_id=user.id)
    return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: LogoutRequest,
    auth_service: AuthServiceDep,
) -> None:
    try:
        payload = auth_service.decode_token(request.refresh_token)
    except ValueError:
        return

    if payload.get("type") != "refresh":
        return

    jti = payload.get("jti")
    if jti:
        await auth_service.revoke_refresh_token(jti)
        log.info("auth.logout.success", jti=jti)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    current_user: CurrentUserDep,
    auth_service: AuthServiceDep,
) -> None:
    await auth_service.revoke_all_user_tokens(current_user.id)
    log.info("auth.logout_all.success", user_id=current_user.id)


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    request: CreateUserRequest,
    current_user: SuperuserDep,
    users_service: UsersServiceDep,
) -> UserResponse:
    """Create a new user. Only superusers can create users."""

    user = await users_service.create_user(
        first_name=request.first_name,
        last_name=request.last_name,
        email=request.email,
        password=request.password,
        is_superuser=request.is_superuser,
    )

    log.info(
        "auth.signup.success",
        user_id=user.id,
        email=user.email,
        created_by=current_user.id,
    )

    return UserResponse(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        created_at=user.created_at.isoformat(),
    )
