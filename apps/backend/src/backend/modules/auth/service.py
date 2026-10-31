from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from jose import JWTError, jwt
from passlib.context import CryptContext

from src.backend.modules.auth.models import RefreshToken
from src.backend.modules.core.settings import Settings
from src.backend.modules.users.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
log = structlog.get_logger(__name__)


class AuthService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._secret_key = settings.auth.jwt_secret_key.get_secret_value()
        self._algorithm = settings.auth.jwt_algorithm
        self._access_token_expire_minutes = settings.auth.access_token_expire_minutes
        self._refresh_token_expire_days = settings.auth.refresh_token_expire_days

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password: str) -> str:
        return pwd_context.hash(password)

    def create_access_token(
        self,
        user_id: int,
        is_superuser: bool,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        now = datetime.now(UTC)
        expire = now + timedelta(minutes=self._access_token_expire_minutes)

        payload = {
            "sub": str(user_id),
            "type": "access",
            "is_superuser": is_superuser,
            "iat": now,
            "exp": expire,
        }
        if extra_claims:
            payload.update(extra_claims)

        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def create_refresh_token(self, user_id: int) -> tuple[str, str, datetime]:
        now = datetime.now(UTC)
        expire = now + timedelta(days=self._refresh_token_expire_days)
        jti = secrets.token_urlsafe(32)

        payload = {
            "sub": str(user_id),
            "type": "refresh",
            "jti": jti,
            "iat": now,
            "exp": expire,
        }

        token = jwt.encode(payload, self._secret_key, algorithm=self._algorithm)
        return token, jti, expire

    def decode_token(self, token: str) -> dict[str, Any]:
        try:
            return jwt.decode(token, self._secret_key, algorithms=[self._algorithm])
        except JWTError as exc:
            raise ValueError("Invalid token") from exc

    async def authenticate_user(self, email: str, password: str) -> User | None:
        user = await User.filter(email=email.lower()).first()
        if not user:
            return None
        if not self.verify_password(password, user.hashed_password):
            return None
        if not user.is_active:
            return None
        return user

    async def save_refresh_token(self, user_id: int, jti: str, expires_at: datetime) -> RefreshToken:
        return await RefreshToken.create(user_id=user_id, jti=jti, expires_at=expires_at)

    async def revoke_refresh_token(self, jti: str) -> None:
        await RefreshToken.filter(jti=jti).delete()

    async def revoke_all_user_tokens(self, user_id: int) -> None:
        await RefreshToken.filter(user_id=user_id).delete()

    async def is_refresh_token_valid(self, jti: str) -> bool:
        token = await RefreshToken.filter(jti=jti).first()
        if not token:
            return False
        now = datetime.now(UTC)
        if token.expires_at < now:
            await token.delete()
            return False
        return True

    async def cleanup_expired_tokens(self) -> None:
        now = datetime.now(UTC)
        await RefreshToken.filter(expires_at__lt=now).delete()
