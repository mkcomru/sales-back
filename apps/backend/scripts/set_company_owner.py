#!/usr/bin/env python3
"""Set a user as company owner.

Interactive mode (no arguments):
    cd apps/backend
    uv run python -m scripts.set_company_owner

CLI mode (with arguments):
    cd apps/backend
    uv run python -m scripts.set_company_owner --user-id 5 --company-id 1

    # Or by email:
    uv run python -m scripts.set_company_owner --email owner@example.com --company-id 1

Requirements:
    - Run from apps/backend (or use: just script set_company_owner)
    - DATABASE__URL environment variable configured
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from urllib.parse import urlparse

from tortoise import Tortoise

from src.backend.modules.companies.models import Company
from src.backend.modules.core.database import tortoise_config
from src.backend.modules.core.settings import get_settings
from src.backend.modules.users.models import CompanyUser, User, UserRole

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


async def set_company_owner_async(user_id: int, company_id: int) -> bool:
    """Set user as company owner.

    Creates CompanyUser if not exists, updates role if exists.
    """
    settings = get_settings()
    config = tortoise_config(db_url=settings.resolved_database_url)

    await Tortoise.init(config=config)

    try:
        user = await User.get_or_none(id=user_id)
        if not user:
            print(f"✗ User with ID {user_id} not found")
            return False

        company = await Company.get_or_none(id=company_id)
        if not company:
            print(f"✗ Company with ID {company_id} not found")
            return False

        company_user, created = await CompanyUser.get_or_create(
            user_id=user_id,
            company_id=company_id,
            defaults={"role": UserRole.OWNER},
        )

        if not created and company_user.role != UserRole.OWNER:
            old_role = company_user.role.value
            company_user.role = UserRole.OWNER
            await company_user.save()
            print(f"✓ Updated role from '{old_role}' to 'owner'")
        elif created:
            print("✓ Created new CompanyUser with role 'owner'")
        else:
            print("✓ User is already owner of this company")

        print(f"  User: {user.first_name} {user.last_name} ({user.email})")
        print(f"  Company: {company.name} (ID: {company.id})")
        return True

    finally:
        await Tortoise.close_connections()


async def get_user_by_email(email: str) -> int | None:
    """Get user ID by email."""
    settings = get_settings()
    config = tortoise_config(db_url=settings.resolved_database_url)

    await Tortoise.init(config=config)

    try:
        user = await User.get_or_none(email=email.lower())
        if user:
            return user.id
        return None
    finally:
        await Tortoise.close_connections()


async def list_companies() -> list[tuple[int, str]]:
    """List all companies."""
    settings = get_settings()
    config = tortoise_config(db_url=settings.resolved_database_url)

    await Tortoise.init(config=config)

    try:
        companies = await Company.all()
        return [(c.id, c.name) for c in companies]
    finally:
        await Tortoise.close_connections()


async def list_users() -> list[tuple[int, str, str]]:
    """List all users."""
    settings = get_settings()
    config = tortoise_config(db_url=settings.resolved_database_url)

    await Tortoise.init(config=config)

    try:
        users = await User.all()
        return [(u.id, f"{u.first_name} {u.last_name}", u.email) for u in users]
    finally:
        await Tortoise.close_connections()


def prompt_interactive() -> tuple[int, int]:
    """Prompt for user and company interactively."""
    print("Set company owner...")
    print()

    # List users
    print("Available users:")
    users = asyncio.run(list_users())
    if not users:
        print("✗ No users found. Create a user first.")
        sys.exit(1)
    for uid, name, email in users:
        print(f"  [{uid}] {name} ({email})")
    print()

    user_id_str = input("User ID: ").strip()
    while not user_id_str.isdigit():
        print("✗ Please enter a valid user ID (number)")
        user_id_str = input("User ID: ").strip()
    user_id = int(user_id_str)

    # List companies
    print()
    print("Available companies:")
    companies = asyncio.run(list_companies())
    if not companies:
        print("✗ No companies found. Create a company first.")
        sys.exit(1)
    for cid, name in companies:
        print(f"  [{cid}] {name}")
    print()

    company_id_str = input("Company ID: ").strip()
    while not company_id_str.isdigit():
        print("✗ Please enter a valid company ID (number)")
        company_id_str = input("Company ID: ").strip()
    company_id = int(company_id_str)

    return user_id, company_id


def main() -> None:
    """Parse arguments and set company owner."""
    parser = argparse.ArgumentParser(
        description="Set a user as company owner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (no arguments)
  python scripts/set_company_owner.py

  # Set by user ID
  python scripts/set_company_owner.py --user-id 5 --company-id 1

  # Set by email
  python scripts/set_company_owner.py --email owner@example.com --company-id 1

Note: Make sure DATABASE__URL is set in environment.
        """,
    )

    parser.add_argument("--user-id", dest="user_id", type=int, help="User ID")
    parser.add_argument("--email", help="User email (alternative to --user-id)")
    parser.add_argument("--company-id", dest="company_id", type=int, help="Company ID")

    args = parser.parse_args()

    print("Validating configuration...")
    try:
        asyncio.run(validate_config())
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
    print("✓ Configuration validated")
    print()

    has_args = any([args.user_id is not None, args.email is not None, args.company_id is not None])

    if not has_args:
        user_id, company_id = prompt_interactive()
    else:
        if args.user_id is None and args.email is None:
            print("✗ Error: --user-id or --email is required")
            sys.exit(1)
        if args.company_id is None:
            print("✗ Error: --company-id is required")
            sys.exit(1)

        if args.email:
            user_id = asyncio.run(get_user_by_email(args.email))
            if user_id is None:
                print(f"✗ User with email '{args.email}' not found")
                sys.exit(1)
        else:
            user_id = args.user_id

        company_id = args.company_id

    print(f"Setting user {user_id} as owner of company {company_id}...")
    print()

    try:
        success = asyncio.run(set_company_owner_async(user_id, company_id))
        if not success:
            sys.exit(1)
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
