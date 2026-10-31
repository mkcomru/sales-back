"""Tests for authentication routers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import status
from jose import jwt

from src.backend.modules.auth.models import RefreshToken
from src.backend.modules.auth.service import AuthService
from src.backend.modules.core.settings import Settings
from src.backend.modules.users.models import User


@pytest.mark.asyncio
async def test_login_success(auth_api_client: httpx.AsyncClient, test_user: User) -> None:
    response = await auth_api_client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "test_password_123",  # pragma: allowlist secret
        },
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_email_case_insensitive(auth_api_client: httpx.AsyncClient, test_user: User) -> None:
    response = await auth_api_client.post(
        "/api/v1/auth/login",
        json={
            "email": "TEST@EXAMPLE.COM",
            "password": "test_password_123",  # pragma: allowlist secret
        },
    )

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_login_wrong_password(auth_api_client: httpx.AsyncClient, test_user: User) -> None:
    response = await auth_api_client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "wrong_password",  # pragma: allowlist secret
        },
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Incorrect email or password"


@pytest.mark.asyncio
async def test_login_user_not_found(auth_api_client: httpx.AsyncClient) -> None:
    response = await auth_api_client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "password",  # pragma: allowlist secret
        },
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Incorrect email or password"


@pytest.mark.asyncio
async def test_login_invalid_email_format(auth_api_client: httpx.AsyncClient) -> None:
    response = await auth_api_client.post(
        "/api/v1/auth/login",
        json={
            "email": "invalid-email",
            "password": "password",  # pragma: allowlist secret
        },
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_login_password_too_short(auth_api_client: httpx.AsyncClient, test_user: User) -> None:
    response = await auth_api_client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "short",  # pragma: allowlist secret
        },
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_login_creates_refresh_token(auth_api_client: httpx.AsyncClient, test_user: User) -> None:
    response = await auth_api_client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "test_password_123",  # pragma: allowlist secret
        },
    )

    assert response.status_code == status.HTTP_200_OK

    tokens = await RefreshToken.filter(user_id=test_user.id).all()
    assert len(tokens) == 1


@pytest.mark.asyncio
async def test_login_inactive_user(
    auth_api_client: httpx.AsyncClient,
    auth_service: AuthService,
    precomputed_password_hash: dict[str, str],
) -> None:
    await User.create(
        first_name="Inactive",
        last_name="User",
        email="inactive@example.com",
        hashed_password=precomputed_password_hash["test_password_123"],
        is_active=False,
        is_superuser=False,
    )

    response = await auth_api_client.post(
        "/api/v1/auth/login",
        json={
            "email": "inactive@example.com",
            "password": "test_password_123",  # pragma: allowlist secret
        },
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_refresh_success(
    auth_api_client: httpx.AsyncClient,
    test_user: User,
    auth_service: AuthService,
) -> None:
    refresh_token, jti, expires_at = auth_service.create_refresh_token(test_user.id)
    await auth_service.save_refresh_token(test_user.id, jti, expires_at)

    response = await auth_api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_refresh_creates_new_token(
    auth_api_client: httpx.AsyncClient,
    test_user: User,
    auth_service: AuthService,
) -> None:
    refresh_token, jti, expires_at = auth_service.create_refresh_token(test_user.id)
    await auth_service.save_refresh_token(test_user.id, jti, expires_at)

    response = await auth_api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == status.HTTP_200_OK

    new_refresh_token = response.json()["refresh_token"]
    assert new_refresh_token != refresh_token


@pytest.mark.asyncio
async def test_refresh_revokes_old_token(
    auth_api_client: httpx.AsyncClient,
    test_user: User,
    auth_service: AuthService,
) -> None:
    refresh_token, jti, expires_at = auth_service.create_refresh_token(test_user.id)
    await auth_service.save_refresh_token(test_user.id, jti, expires_at)

    response = await auth_api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == status.HTTP_200_OK

    old_token = await RefreshToken.filter(jti=jti).first()
    assert old_token is None


@pytest.mark.asyncio
async def test_refresh_invalid_token(auth_api_client: httpx.AsyncClient) -> None:
    response = await auth_api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "invalid_token"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Invalid refresh token"


@pytest.mark.asyncio
async def test_refresh_with_access_token(
    auth_api_client: httpx.AsyncClient,
    test_user: User,
    auth_service: AuthService,
) -> None:
    access_token = auth_service.create_access_token(test_user.id, False)

    response = await auth_api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": access_token},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Invalid token type"


@pytest.mark.asyncio
async def test_refresh_expired_token(
    auth_api_client: httpx.AsyncClient,
    test_user: User,
    auth_service: AuthService,
    settings: Settings,
) -> None:
    now = datetime.now(UTC)
    past_time = now - timedelta(days=1)

    payload = {
        "sub": str(test_user.id),
        "type": "refresh",
        "jti": "expired_jti",
        "iat": past_time,
        "exp": past_time,
    }

    expired_token = jwt.encode(
        payload,
        settings.auth.jwt_secret_key.get_secret_value(),
        algorithm=settings.auth.jwt_algorithm,
    )

    response = await auth_api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": expired_token},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_refresh_revoked_token(
    auth_api_client: httpx.AsyncClient,
    test_user: User,
    auth_service: AuthService,
) -> None:
    refresh_token, jti, expires_at = auth_service.create_refresh_token(test_user.id)
    await auth_service.save_refresh_token(test_user.id, jti, expires_at)
    await auth_service.revoke_refresh_token(jti)

    response = await auth_api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "Refresh token revoked or expired"


@pytest.mark.asyncio
async def test_refresh_user_not_found(
    auth_api_client: httpx.AsyncClient,
    auth_service: AuthService,
    settings: Settings,
    precomputed_password_hash: dict[str, str],
) -> None:
    test_user = await User.create(
        first_name="Temp",
        last_name="User",
        email="temp@example.com",
        hashed_password=precomputed_password_hash["temp_password_123"],
        is_active=True,
        is_superuser=False,
    )

    payload = {
        "sub": str(test_user.id),
        "type": "refresh",
        "jti": "test_jti",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(days=7),
    }

    token = jwt.encode(
        payload,
        settings.auth.jwt_secret_key.get_secret_value(),
        algorithm=settings.auth.jwt_algorithm,
    )

    await RefreshToken.create(
        user_id=test_user.id,
        jti="test_jti",
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )

    await test_user.delete()

    response = await auth_api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] in [
        "User not found or inactive",
        "Refresh token revoked or expired",
    ]


@pytest.mark.asyncio
async def test_refresh_inactive_user(
    auth_api_client: httpx.AsyncClient,
    test_user: User,
    auth_service: AuthService,
) -> None:
    refresh_token, jti, expires_at = auth_service.create_refresh_token(test_user.id)
    await auth_service.save_refresh_token(test_user.id, jti, expires_at)

    test_user.is_active = False
    await test_user.save()

    response = await auth_api_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["detail"] == "User not found or inactive"


@pytest.mark.asyncio
async def test_logout_success(
    auth_api_client: httpx.AsyncClient,
    test_user: User,
    auth_service: AuthService,
) -> None:
    refresh_token, jti, expires_at = auth_service.create_refresh_token(test_user.id)
    await auth_service.save_refresh_token(test_user.id, jti, expires_at)

    response = await auth_api_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT

    token = await RefreshToken.filter(jti=jti).first()
    assert token is None


@pytest.mark.asyncio
async def test_logout_invalid_token(auth_api_client: httpx.AsyncClient) -> None:
    response = await auth_api_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": "invalid_token"},
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_logout_with_access_token(
    auth_api_client: httpx.AsyncClient,
    test_user: User,
    auth_service: AuthService,
) -> None:
    access_token = auth_service.create_access_token(test_user.id, False)

    response = await auth_api_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": access_token},
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_logout_already_revoked_token(
    auth_api_client: httpx.AsyncClient,
    test_user: User,
    auth_service: AuthService,
) -> None:
    refresh_token, jti, expires_at = auth_service.create_refresh_token(test_user.id)
    await auth_service.save_refresh_token(test_user.id, jti, expires_at)
    await auth_service.revoke_refresh_token(jti)

    response = await auth_api_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_logout_all_success(
    auth_api_client: httpx.AsyncClient,
    test_user: User,
    auth_service: AuthService,
) -> None:
    expires_at = datetime.now(UTC) + timedelta(days=7)
    await auth_service.save_refresh_token(test_user.id, "jti_1", expires_at)
    await auth_service.save_refresh_token(test_user.id, "jti_2", expires_at)
    await auth_service.save_refresh_token(test_user.id, "jti_3", expires_at)

    access_token = auth_service.create_access_token(test_user.id, False)

    response = await auth_api_client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT

    tokens = await RefreshToken.filter(user_id=test_user.id).all()
    assert len(tokens) == 0


@pytest.mark.asyncio
async def test_logout_all_no_tokens(
    auth_api_client: httpx.AsyncClient,
    test_user: User,
    auth_service: AuthService,
) -> None:
    access_token = auth_service.create_access_token(test_user.id, False)

    response = await auth_api_client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_logout_all_unauthorized(auth_api_client: httpx.AsyncClient) -> None:
    response = await auth_api_client.post("/api/v1/auth/logout-all")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_logout_all_invalid_token(auth_api_client: httpx.AsyncClient) -> None:
    response = await auth_api_client.post(
        "/api/v1/auth/logout-all",
        headers={"Authorization": "Bearer invalid_token"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_create_user_success(
    auth_api_client: httpx.AsyncClient,
    test_superuser: User,
    auth_service: AuthService,
) -> None:
    access_token = auth_service.create_access_token(test_superuser.id, True)

    response = await auth_api_client.post(
        "/api/v1/auth/signup",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "first_name": "John",
            "last_name": "Doe",
            "email": "newuser@example.com",
            "password": "new_password_123",  # pragma: allowlist secret
            "is_superuser": False,
        },
    )

    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert data["first_name"] == "John"
    assert data["last_name"] == "Doe"
    assert data["email"] == "newuser@example.com"
    assert data["is_active"] is True
    assert data["is_superuser"] is False
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_create_user_as_superuser(
    auth_api_client: httpx.AsyncClient,
    test_superuser: User,
    auth_service: AuthService,
) -> None:
    access_token = auth_service.create_access_token(test_superuser.id, True)

    response = await auth_api_client.post(
        "/api/v1/auth/signup",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "first_name": "Admin",
            "last_name": "User",
            "email": "newadmin@example.com",
            "password": "admin_password_123",  # pragma: allowlist secret
            "is_superuser": True,
        },
    )

    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert data["first_name"] == "Admin"
    assert data["last_name"] == "User"
    assert data["is_superuser"] is True


@pytest.mark.asyncio
async def test_create_user_duplicate_email(
    auth_api_client: httpx.AsyncClient,
    test_superuser: User,
    auth_service: AuthService,
) -> None:
    from src.backend.modules.users.repository import UsersRepository
    from src.backend.modules.users.service import UsersService

    users_service = UsersService(UsersRepository())
    await users_service.create_user(
        first_name="Existing",
        last_name="User",
        email="existing@example.com",
        password="password_123",  # pragma: allowlist secret
    )

    access_token = auth_service.create_access_token(test_superuser.id, True)

    response = await auth_api_client.post(
        "/api/v1/auth/signup",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "first_name": "New",
            "last_name": "User",
            "email": "existing@example.com",
            "password": "new_password_123",  # pragma: allowlist secret
            "is_superuser": False,
        },
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["detail"] == "User with this email already exists"


@pytest.mark.asyncio
async def test_create_user_duplicate_email_case_insensitive(
    auth_api_client: httpx.AsyncClient,
    test_superuser: User,
    auth_service: AuthService,
) -> None:
    from src.backend.modules.users.repository import UsersRepository
    from src.backend.modules.users.service import UsersService

    users_service = UsersService(UsersRepository())
    await users_service.create_user(
        first_name="Existing",
        last_name="User",
        email="existing@example.com",
        password="password_123",  # pragma: allowlist secret
    )

    access_token = auth_service.create_access_token(test_superuser.id, True)

    response = await auth_api_client.post(
        "/api/v1/auth/signup",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "first_name": "EXISTING",
            "last_name": "USER",
            "email": "EXISTING@EXAMPLE.COM",
            "password": "new_password_123",  # pragma: allowlist secret
            "is_superuser": False,
        },
    )

    assert response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_create_user_not_superuser(
    auth_api_client: httpx.AsyncClient,
    test_user: User,
    auth_service: AuthService,
) -> None:
    access_token = auth_service.create_access_token(test_user.id, False)

    response = await auth_api_client.post(
        "/api/v1/auth/signup",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "email": "newuser@example.com",
            "password": "new_password_123",  # pragma: allowlist secret
            "is_superuser": False,
        },
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"] == "Superuser access required"


@pytest.mark.asyncio
async def test_create_user_unauthorized(auth_api_client: httpx.AsyncClient) -> None:
    response = await auth_api_client.post(
        "/api/v1/auth/signup",
        json={
            "email": "newuser@example.com",
            "password": "new_password_123",  # pragma: allowlist secret
            "is_superuser": False,
        },
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_create_user_invalid_email(
    auth_api_client: httpx.AsyncClient,
    test_superuser: User,
    auth_service: AuthService,
) -> None:
    access_token = auth_service.create_access_token(test_superuser.id, True)

    response = await auth_api_client.post(
        "/api/v1/auth/signup",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "email": "invalid-email",
            "password": "new_password_123",  # pragma: allowlist secret
            "is_superuser": False,
        },
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_create_user_password_too_short(
    auth_api_client: httpx.AsyncClient,
    test_superuser: User,
    auth_service: AuthService,
) -> None:
    access_token = auth_service.create_access_token(test_superuser.id, True)

    response = await auth_api_client.post(
        "/api/v1/auth/signup",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "email": "newuser@example.com",
            "password": "short",  # pragma: allowlist secret
            "is_superuser": False,
        },
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
