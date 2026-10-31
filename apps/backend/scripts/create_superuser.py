#!/usr/bin/env python3
"""Create a superuser in the backend database.

Interactive mode (no arguments):
    cd apps/backend
    uv run python -m scripts.create_superuser

CLI mode (with arguments):
    cd apps/backend
    uv run python -m scripts.create_superuser \
        --first-name Admin \
        --last-name User \
        --email admin@example.com \
        --password secret \
        --superuser

Requirements:
    - Run from apps/backend (or use: just script create_superuser)
    - DATABASE__URL environment variable configured
    - AUTH__JWT_SECRET_KEY environment variable configured
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from urllib.parse import urlparse

from tortoise import Tortoise

from src.backend.modules.core.database import tortoise_config
from src.backend.modules.core.settings import get_settings
from src.backend.modules.users.exceptions import UserAlreadyExistsError
from src.backend.modules.users.repository import UsersRepository
from src.backend.modules.users.service import UsersService

CONNECTION_TIMEOUT_SECONDS = 10


def ping_database_host(db_url: str) -> bool:
    """Check if database host is reachable via TCP."""
    import socket

    try:
        parsed = urlparse(db_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 5432

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(CONNECTION_TIMEOUT_SECONDS)
        result = sock.connect_ex((host, port))
        sock.close()

        if result == 0:
            return True
        print(f"✗ Database host {host}:{port} unreachable")
        return False
    except socket.gaierror as e:
        print(f"✗ DNS resolution failed for database host: {e}")
        return False
    except Exception as e:
        print(f"✗ Network error: {e}")
        return False


async def validate_config() -> None:
    """Validate settings and database connection before proceeding."""
    try:
        settings = get_settings()
        db_url = settings.resolved_database_url

        if not ping_database_host(db_url):
            sys.exit(1)

        config = tortoise_config(db_url=db_url)
        await asyncio.wait_for(Tortoise.init(config=config), timeout=CONNECTION_TIMEOUT_SECONDS)
        await Tortoise.close_connections()
    except TimeoutError:
        print(f"✗ Database connection timed out after {CONNECTION_TIMEOUT_SECONDS}s")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Configuration error: {type(e).__name__}: {e}")
        sys.exit(1)


async def create_user_async(
    first_name: str, last_name: str, email: str, password: str, is_superuser: bool
) -> int | None:
    """Create a user in the database.

    Returns:
        User ID if created, None if user already exists
    """
    settings = get_settings()
    config = tortoise_config(db_url=settings.resolved_database_url)

    await Tortoise.init(config=config)

    try:
        users_repository = UsersRepository()
        users_service = UsersService(users_repository=users_repository)

        try:
            user = await users_service.create_user(
                first_name=first_name,
                last_name=last_name,
                email=email,
                password=password,
                is_superuser=is_superuser,
            )
            print("✓ User created successfully!")
            print(f"  ID: {user.id}")
            print(f"  Name: {user.first_name} {user.last_name}")
            print(f"  Email: {user.email}")
            print(f"  Superuser: {user.is_superuser}")
            return user.id

        except UserAlreadyExistsError:
            print(f"✗ User with email '{email}' already exists")
            return None

    finally:
        await Tortoise.close_connections()


def prompt_interactive() -> tuple[str, str, str, str, bool]:
    """Prompt for user details interactively."""
    print("Creating user...")
    print()

    first_name = input("First name: ").strip()
    while not first_name:
        print("✗ First name cannot be empty")
        first_name = input("First name: ").strip()

    last_name = input("Last name: ").strip()
    while not last_name:
        print("✗ Last name cannot be empty")
        last_name = input("Last name: ").strip()

    email = input("Email address: ").strip()
    while not email:
        print("✗ Email cannot be empty")
        email = input("Email address: ").strip()

    password = getpass.getpass("Password: ")
    while len(password) < 8:
        print("✗ Error: Password must be at least 8 characters long")
        password = getpass.getpass("Password: ")

    password_confirm = getpass.getpass("Password (again): ")
    while password != password_confirm:
        print("✗ Error: Passwords don't match")
        password = getpass.getpass("Password: ")
        while len(password) < 8:
            print("✗ Error: Password must be at least 8 characters long")
            password = getpass.getpass("Password: ")
        password_confirm = getpass.getpass("Password (again): ")

    superuser_input = input("Superuser? (y/N): ").strip().lower()
    is_superuser = superuser_input in ("y", "yes")

    return first_name, last_name, email, password, is_superuser


def main() -> None:
    """Parse arguments and create user."""
    parser = argparse.ArgumentParser(
        description="Create a superuser in the backend database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (no arguments)
  python scripts/create_superuser.py

  # Create regular user
  python scripts/create_superuser.py \
    --first-name John \
    --last-name Doe \
    --email user@example.com \
    --password secret123

  # Create superuser
  python scripts/create_superuser.py \
    --first-name Admin \
    --last-name User \
    --email admin@example.com \
    --password secret123 \
    --superuser

Note: Make sure DATABASE__URL and AUTH__JWT_SECRET_KEY are set in environment.
        """,
    )

    parser.add_argument("--first-name", dest="first_name", help="User first name")
    parser.add_argument("--last-name", dest="last_name", help="User last name")
    parser.add_argument("--email", help="User email address")
    parser.add_argument("--password", help="User password (min 8 chars)")
    parser.add_argument(
        "--superuser",
        action="store_true",
        help="Create user as superuser (can create other users)",
    )

    args = parser.parse_args()

    # Validate configuration before prompting
    print("Validating configuration...")
    try:
        asyncio.run(validate_config())
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
    print("✓ Configuration validated")
    print()

    # Check if any arguments provided
    has_args = any(
        [
            args.first_name is not None,
            args.last_name is not None,
            args.email is not None,
            args.password is not None,
            args.superuser,
        ]
    )

    if not has_args:
        first_name, last_name, email, password, is_superuser = prompt_interactive()
    else:
        if not args.first_name:
            print("✗ Error: --first-name is required when using arguments")
            sys.exit(1)
        if not args.last_name:
            print("✗ Error: --last-name is required when using arguments")
            sys.exit(1)
        if not args.email:
            print("✗ Error: --email is required when using arguments")
            sys.exit(1)
        if not args.password:
            print("✗ Error: --password is required when using arguments")
            sys.exit(1)

        first_name = args.first_name
        last_name = args.last_name
        email = args.email
        password = args.password
        is_superuser = args.superuser

        # Validate password length
        if len(password) < 8:
            print("✗ Error: Password must be at least 8 characters long")
            sys.exit(1)

    print(f"\nCreating {'superuser' if is_superuser else 'user'}: {email}")

    try:
        asyncio.run(create_user_async(first_name, last_name, email, password, is_superuser))
    except Exception as e:
        print(f"✗ Error: {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
