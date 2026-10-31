"""Tests for AuthService."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from jose import jwt

from src.backend.modules.auth.models import RefreshToken
from src.backend.modules.auth.service import AuthService
from src.backend.modules.core.settings import Settings
from src.backend.modules.users.models import User


@pytest.fixture
def auth_service(settings: Settings) -> AuthService:
    return AuthService(settings)


class TestPasswordHandling:
    """Test password hashing and verification."""

    def test_get_password_hash(self, auth_service: AuthService) -> None:
        password = "test_password_123"  # pragma: allowlist secret
        hashed = auth_service.get_password_hash(password)

        assert hashed != password
        assert len(hashed) > 0
        assert hashed.startswith("$2b$")

    def test_verify_password_correct(self, auth_service: AuthService) -> None:
        password = "test_password_123"  # pragma: allowlist secret
        hashed = auth_service.get_password_hash(password)

        assert auth_service.verify_password(password, hashed)

    def test_verify_password_incorrect(self, auth_service: AuthService) -> None:
        password = "test_password_123"  # pragma: allowlist secret
        wrong_password = "wrong_password_456"  # pragma: allowlist secret
        hashed = auth_service.get_password_hash(password)

        assert not auth_service.verify_password(wrong_password, hashed)

    def test_verify_password_empty(self, auth_service: AuthService) -> None:
        password = "test_password_123"  # pragma: allowlist secret
        hashed = auth_service.get_password_hash(password)

        assert not auth_service.verify_password("", hashed)


class TestAccessToken:
    """Test access token creation and validation."""

    def test_create_access_token(self, auth_service: AuthService) -> None:
        user_id = 123
        is_superuser = False

        token = auth_service.create_access_token(user_id, is_superuser)

        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_access_token_payload(self, auth_service: AuthService, settings: Settings) -> None:
        user_id = 123
        is_superuser = True

        token = auth_service.create_access_token(user_id, is_superuser)
        payload = jwt.decode(
            token,
            settings.auth.jwt_secret_key.get_secret_value(),
            algorithms=[settings.auth.jwt_algorithm],
        )

        assert payload["sub"] == str(user_id)
        assert payload["type"] == "access"
        assert payload["is_superuser"] is True
        assert "iat" in payload
        assert "exp" in payload

    def test_create_access_token_expiration(self, auth_service: AuthService, settings: Settings) -> None:
        user_id = 123
        is_superuser = False

        before_creation = datetime.now(UTC)
        token = auth_service.create_access_token(user_id, is_superuser)
        after_creation = datetime.now(UTC)

        payload = jwt.decode(
            token,
            settings.auth.jwt_secret_key.get_secret_value(),
            algorithms=[settings.auth.jwt_algorithm],
        )

        exp_timestamp = payload["exp"]
        exp_datetime = datetime.fromtimestamp(exp_timestamp, UTC)

        expected_min = before_creation + timedelta(minutes=settings.auth.access_token_expire_minutes)
        expected_max = after_creation + timedelta(minutes=settings.auth.access_token_expire_minutes)

        assert expected_min - timedelta(seconds=1) <= exp_datetime <= expected_max + timedelta(seconds=1)

    def test_create_access_token_with_extra_claims(self, auth_service: AuthService, settings: Settings) -> None:
        user_id = 123
        is_superuser = False
        extra_claims = {"custom_field": "custom_value", "role": "admin"}

        token = auth_service.create_access_token(user_id, is_superuser, extra_claims=extra_claims)
        payload = jwt.decode(
            token,
            settings.auth.jwt_secret_key.get_secret_value(),
            algorithms=[settings.auth.jwt_algorithm],
        )

        assert payload["custom_field"] == "custom_value"
        assert payload["role"] == "admin"


class TestRefreshToken:
    """Test refresh token creation and validation."""

    def test_create_refresh_token(self, auth_service: AuthService) -> None:
        user_id = 123

        token, jti, expires_at = auth_service.create_refresh_token(user_id)

        assert isinstance(token, str)
        assert len(token) > 0
        assert isinstance(jti, str)
        assert len(jti) > 0
        assert isinstance(expires_at, datetime)

    def test_create_refresh_token_payload(self, auth_service: AuthService, settings: Settings) -> None:
        user_id = 123

        token, jti, expires_at = auth_service.create_refresh_token(user_id)
        payload = jwt.decode(
            token,
            settings.auth.jwt_secret_key.get_secret_value(),
            algorithms=[settings.auth.jwt_algorithm],
        )

        assert payload["sub"] == str(user_id)
        assert payload["type"] == "refresh"
        assert payload["jti"] == jti
        assert "iat" in payload
        assert "exp" in payload

    def test_create_refresh_token_expiration(self, auth_service: AuthService, settings: Settings) -> None:
        user_id = 123

        before_creation = datetime.now(UTC)
        token, jti, expires_at = auth_service.create_refresh_token(user_id)
        after_creation = datetime.now(UTC)

        expected_min = before_creation + timedelta(days=settings.auth.refresh_token_expire_days)
        expected_max = after_creation + timedelta(days=settings.auth.refresh_token_expire_days)

        assert expected_min <= expires_at <= expected_max

    def test_create_refresh_token_unique_jti(self, auth_service: AuthService) -> None:
        user_id = 123

        _, jti1, _ = auth_service.create_refresh_token(user_id)
        _, jti2, _ = auth_service.create_refresh_token(user_id)

        assert jti1 != jti2


class TestTokenDecoding:
    """Test token decoding and validation."""

    def test_decode_access_token(self, auth_service: AuthService, settings: Settings) -> None:
        user_id = 123
        is_superuser = False

        token = auth_service.create_access_token(user_id, is_superuser)
        payload = auth_service.decode_token(token)

        assert payload["sub"] == str(user_id)
        assert payload["type"] == "access"

    def test_decode_refresh_token(self, auth_service: AuthService, settings: Settings) -> None:
        user_id = 123

        token, jti, _ = auth_service.create_refresh_token(user_id)
        payload = auth_service.decode_token(token)

        assert payload["sub"] == str(user_id)
        assert payload["type"] == "refresh"
        assert payload["jti"] == jti

    def test_decode_invalid_token(self, auth_service: AuthService) -> None:
        with pytest.raises(ValueError, match="Invalid token"):
            auth_service.decode_token("invalid_token")

    def test_decode_expired_token(self, auth_service: AuthService, settings: Settings) -> None:
        user_id = 123
        now = datetime.now(UTC)
        past_time = now - timedelta(days=1)

        payload = {
            "sub": str(user_id),
            "type": "access",
            "is_superuser": False,
            "iat": past_time,
            "exp": past_time,
        }

        token = jwt.encode(
            payload,
            settings.auth.jwt_secret_key.get_secret_value(),
            algorithm=settings.auth.jwt_algorithm,
        )

        with pytest.raises(ValueError, match="Invalid token"):
            auth_service.decode_token(token)

    def test_decode_token_with_wrong_secret(self, auth_service: AuthService, settings: Settings) -> None:
        user_id = 123
        payload = {
            "sub": str(user_id),
            "type": "access",
            "is_superuser": False,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=15),
        }

        token = jwt.encode(payload, "wrong_secret", algorithm=settings.auth.jwt_algorithm)

        with pytest.raises(ValueError, match="Invalid token"):
            auth_service.decode_token(token)


class TestUserAuthentication:
    """Test user authentication."""

    async def test_authenticate_user_success(
        self, auth_service: AuthService, precomputed_password_hash: dict[str, str]
    ) -> None:
        password = "test_password_123"  # pragma: allowlist secret
        hashed = precomputed_password_hash[password]

        user = await User.create(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            hashed_password=hashed,
            is_active=True,
        )

        result = await auth_service.authenticate_user("test@example.com", password)

        assert result is not None
        assert result.id == user.id
        assert result.email == "test@example.com"

    async def test_authenticate_user_email_case_insensitive(
        self, auth_service: AuthService, precomputed_password_hash: dict[str, str]
    ) -> None:
        password = "test_password_123"  # pragma: allowlist secret
        hashed = precomputed_password_hash[password]

        await User.create(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            hashed_password=hashed,
            is_active=True,
        )

        result = await auth_service.authenticate_user("TEST@EXAMPLE.COM", password)

        assert result is not None
        assert result.email == "test@example.com"

    async def test_authenticate_user_wrong_password(
        self, auth_service: AuthService, precomputed_password_hash: dict[str, str]
    ) -> None:
        password = "test_password_123"  # pragma: allowlist secret
        hashed = precomputed_password_hash[password]

        await User.create(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            hashed_password=hashed,
            is_active=True,
        )

        result = await auth_service.authenticate_user("test@example.com", "wrong_password")

        assert result is None

    async def test_authenticate_user_not_found(self, auth_service: AuthService) -> None:
        result = await auth_service.authenticate_user("nonexistent@example.com", "password")

        assert result is None

    async def test_authenticate_user_inactive(
        self, auth_service: AuthService, precomputed_password_hash: dict[str, str]
    ) -> None:
        password = "test_password_123"  # pragma: allowlist secret
        hashed = precomputed_password_hash[password]

        await User.create(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            hashed_password=hashed,
            is_active=False,
        )

        result = await auth_service.authenticate_user("test@example.com", password)

        assert result is None


class TestUserCreation:
    """Test user creation."""

    async def test_create_user(self, auth_service: AuthService) -> None:
        from src.backend.modules.users.repository import UsersRepository
        from src.backend.modules.users.service import UsersService

        users_service = UsersService(UsersRepository())
        user = await users_service.create_user(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            password="test_password_123",  # pragma: allowlist secret
            is_superuser=False,
        )

        assert user.id is not None
        assert user.first_name == "Test"
        assert user.last_name == "User"
        assert user.email == "test@example.com"
        assert user.is_active is True
        assert user.is_superuser is False
        assert user.hashed_password != "test_password_123"  # pragma: allowlist secret
        assert auth_service.verify_password("test_password_123", user.hashed_password)  # pragma: allowlist secret

    async def test_create_user_email_lowercase(self, auth_service: AuthService) -> None:
        from src.backend.modules.users.repository import UsersRepository
        from src.backend.modules.users.service import UsersService

        users_service = UsersService(UsersRepository())
        user = await users_service.create_user(
            first_name="JOHN",
            last_name="DOE",
            email="TEST@EXAMPLE.COM",
            password="test_password_123",  # pragma: allowlist secret
            is_superuser=False,
        )

        assert user.first_name == "JOHN"
        assert user.last_name == "DOE"
        assert user.email == "test@example.com"

    async def test_create_superuser(self, auth_service: AuthService) -> None:
        from src.backend.modules.users.repository import UsersRepository
        from src.backend.modules.users.service import UsersService

        users_service = UsersService(UsersRepository())
        user = await users_service.create_user(
            first_name="Admin",
            last_name="User",
            email="admin@example.com",
            password="admin_password_123",  # pragma: allowlist secret
            is_superuser=True,
        )

        assert user.first_name == "Admin"
        assert user.last_name == "User"
        assert user.is_superuser is True

    async def test_create_user_duplicate_email(self, auth_service: AuthService) -> None:
        from src.backend.modules.users.exceptions import UserAlreadyExistsError
        from src.backend.modules.users.repository import UsersRepository
        from src.backend.modules.users.service import UsersService

        users_service = UsersService(UsersRepository())
        await users_service.create_user(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            password="test_password_123",  # pragma: allowlist secret
        )

        with pytest.raises(UserAlreadyExistsError):
            await users_service.create_user(
                first_name="Test",
                last_name="User",
                email="test@example.com",
                password="another_password",  # pragma: allowlist secret
            )


class TestRefreshTokenManagement:
    """Test refresh token management."""

    async def test_save_refresh_token(self, auth_service: AuthService) -> None:
        user = await User.create(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            hashed_password="hashed",  # pragma: allowlist secret
            is_active=True,
        )

        jti = "test_jti_123"
        expires_at = datetime.now(UTC) + timedelta(days=7)

        token = await auth_service.save_refresh_token(user.id, jti, expires_at)

        assert token.user_id == user.id
        assert token.jti == jti
        assert token.expires_at == expires_at

    async def test_is_refresh_token_valid_success(self, auth_service: AuthService) -> None:
        user = await User.create(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            hashed_password="hashed",  # pragma: allowlist secret
            is_active=True,
        )

        jti = "test_jti_123"
        expires_at = datetime.now(UTC) + timedelta(days=7)
        await auth_service.save_refresh_token(user.id, jti, expires_at)

        is_valid = await auth_service.is_refresh_token_valid(jti)

        assert is_valid is True

    async def test_is_refresh_token_valid_not_found(self, auth_service: AuthService) -> None:
        is_valid = await auth_service.is_refresh_token_valid("nonexistent_jti")

        assert is_valid is False

    async def test_is_refresh_token_valid_expired(self, auth_service: AuthService) -> None:
        user = await User.create(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            hashed_password="hashed",  # pragma: allowlist secret
            is_active=True,
        )

        jti = "test_jti_expired"
        expires_at = datetime.now(UTC) - timedelta(days=1)
        await auth_service.save_refresh_token(user.id, jti, expires_at)

        is_valid = await auth_service.is_refresh_token_valid(jti)

        assert is_valid is False

        token = await RefreshToken.filter(jti=jti).first()
        assert token is None

    async def test_revoke_refresh_token(self, auth_service: AuthService) -> None:
        user = await User.create(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            hashed_password="hashed",  # pragma: allowlist secret
            is_active=True,
        )

        jti = "test_jti_123"
        expires_at = datetime.now(UTC) + timedelta(days=7)
        await auth_service.save_refresh_token(user.id, jti, expires_at)

        await auth_service.revoke_refresh_token(jti)

        token = await RefreshToken.filter(jti=jti).first()
        assert token is None

    async def test_revoke_all_user_tokens(self, auth_service: AuthService) -> None:
        user = await User.create(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            hashed_password="hashed",  # pragma: allowlist secret
            is_active=True,
        )

        expires_at = datetime.now(UTC) + timedelta(days=7)
        await auth_service.save_refresh_token(user.id, "jti_1", expires_at)
        await auth_service.save_refresh_token(user.id, "jti_2", expires_at)
        await auth_service.save_refresh_token(user.id, "jti_3", expires_at)

        await auth_service.revoke_all_user_tokens(user.id)

        tokens = await RefreshToken.filter(user_id=user.id).all()
        assert len(tokens) == 0

    async def test_revoke_all_user_tokens_no_tokens(self, auth_service: AuthService) -> None:
        user = await User.create(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            hashed_password="hashed",  # pragma: allowlist secret
            is_active=True,
        )

        await auth_service.revoke_all_user_tokens(user.id)

        tokens = await RefreshToken.filter(user_id=user.id).all()
        assert len(tokens) == 0

    async def test_cleanup_expired_tokens(self, auth_service: AuthService) -> None:
        user = await User.create(
            first_name="Test",
            last_name="User",
            email="test@example.com",
            hashed_password="hashed",  # pragma: allowlist secret
            is_active=True,
        )

        expired_time = datetime.now(UTC) - timedelta(days=1)
        valid_time = datetime.now(UTC) + timedelta(days=7)

        await auth_service.save_refresh_token(user.id, "expired_1", expired_time)
        await auth_service.save_refresh_token(user.id, "expired_2", expired_time)
        await auth_service.save_refresh_token(user.id, "valid_1", valid_time)

        await auth_service.cleanup_expired_tokens()

        expired_tokens = await RefreshToken.filter(jti__in=["expired_1", "expired_2"]).all()
        valid_tokens = await RefreshToken.filter(jti="valid_1").all()

        assert len(expired_tokens) == 0
        assert len(valid_tokens) == 1
