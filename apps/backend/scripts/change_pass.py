
#!/usr/bin/env python3

import argparse
import asyncio
import sys

from tortoise import Tortoise

from src.backend.modules.core.database import tortoise_config
from src.backend.modules.core.settings import get_settings
from src.backend.modules.users.models import User
from src.backend.modules.auth.models import RefreshToken
from src.backend.modules.users.service import UsersService


async def change_password(email: str, password: str) -> None:
    settings = get_settings()
    config = tortoise_config(db_url=settings.resolved_database_url)

    await Tortoise.init(config=config)

    try:
        user = await User.get_or_none(email=email)

        if user is None:
            print(f"User with email {email} not found")
            sys.exit(1)

        user.hashed_password = UsersService.get_password_hash(password)
        await user.save(update_fields=["hashed_password", "updated_at"])

        # Отзываем все refresh-токены пользователя
        deleted_tokens = await RefreshToken.filter(user_id=user.id).delete()

        print("Password changed successfully!")
        print(f"Email: {user.email}")
        print(f"User ID: {user.id}")
        print(f"Revoked refresh tokens: {deleted_tokens}")

    finally:
        await Tortoise.close_connections()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Change user password by email"
    )

    parser.add_argument(
        "--email",
        required=True,
        help="User email",
    )
    parser.add_argument(
        "--password",
        required=True,
        help="New password",
    )

    args = parser.parse_args()

    if len(args.password) < 8:
        print("Password must contain at least 8 characters")
        sys.exit(1)

    asyncio.run(change_password(args.email, args.password))


if __name__ == "__main__":
    main()
