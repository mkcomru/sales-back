
#!/usr/bin/env python3

import argparse
import asyncio
import getpass
import sys

from tortoise import Tortoise

from src.backend.modules.core.database import tortoise_config
from src.backend.modules.core.settings import get_settings
from src.backend.modules.users.models import User
from src.backend.modules.auth.models import RefreshToken
from src.backend.modules.users.service import UsersService


async def change_password(user_id: int, password: str) -> None:
    settings = get_settings()
    config = tortoise_config(db_url=settings.resolved_database_url)

    await Tortoise.init(config=config)

    try:
        user = await User.get_or_none(id=user_id)

        if user is None:
            print(f"User with ID {user_id} not found")
            return

        user.hashed_password = UsersService.get_password_hash(password)
        await user.save(update_fields=["hashed_password", "updated_at"])

        # Завершаем существующие сессии пользователя
        await RefreshToken.filter(user_id=user.id).delete()

        print("Password changed successfully!")
        print(f"User ID: {user.id}")
        print(f"Email: {user.email}")
        print("Refresh tokens revoked.")

    finally:
        await Tortoise.close_connections()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Change user password by ID"
    )
    parser.add_argument("--user-id", type=int, required=True)

    args = parser.parse_args()

    password = getpass.getpass("New password: ")
    password_confirm = getpass.getpass("Confirm password: ")

    if len(password) < 8:
        print("Password must be at least 8 characters")
        sys.exit(1)

    if password != password_confirm:
        print("Passwords do not match")
        sys.exit(1)

    asyncio.run(change_password(args.user_id, password))


if __name__ == "__main__":
    main()
