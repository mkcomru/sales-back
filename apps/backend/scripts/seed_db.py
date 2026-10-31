#!/usr/bin/env python3
"""Seed the database with minimum required data to run the project.

Creates:
  - Company
  - Prompt (agent type, loaded from agent.md)
  - Connector (custom type)
  - Default stages for the company
  - CompanyUser link (if --user-email provided)

Usage:
    cd apps/backend
    uv run python -m scripts.seed_db

    uv run python -m scripts.seed_db \\
        --company-name "My Company" \\
        --assistant-name "Алиса" \\
        --connector-id "my-connector" \\
        --user-email admin@example.com
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

from tortoise import Tortoise

from src.backend.modules.core.database import tortoise_config
from src.backend.modules.core.settings import get_settings

CONNECTION_TIMEOUT_SECONDS = 10
AGENT_MD_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "apps"
    / "sales-agent"
    / "src"
    / "sales_agent"
    / "agents"
    / "prompts"
    / "agent.md"
)


def ping_database_host(db_url: str) -> bool:
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
    except Exception as e:
        print(f"✗ Network error: {e}")
        return False


async def seed(
    company_name: str,
    company_description: str,
    assistant_name: str,
    rules: str,
    tone_of_voice: str,
    qualification_workflow: str,
    qualification_examples: str,
    collection_name: str,
    user_email: str | None,
) -> None:
    from src.backend.modules.companies.models import Company
    from src.backend.modules.prompts.models import AgentType, Prompt
    from src.backend.modules.stages.service import StagesService
    from src.backend.modules.users.models import CompanyUser, User, UserRole

    # --- Company ---
    existing_company = await Company.filter(name=company_name).first()
    if existing_company:
        print(f"  Company '{company_name}' already exists (id={existing_company.id}), skipping.")
        company = existing_company
    else:
        company = await Company.create(
            name=company_name,
            description=company_description,
            rules=rules,
            tone_of_voice=tone_of_voice,
            assistant_name=assistant_name,
            qualification_workflow=qualification_workflow,
            qualification_examples=qualification_examples,
            collection_name=collection_name,
            enabled_tools=[],
        )
        print(f"✓ Company created: '{company.name}' (id={company.id})")

        stages = await StagesService().create_default_stages(company.id)
        print(f"✓ Default stages created: {[s.name for s in stages]}")

    # --- Prompt ---
    existing_prompt = await Prompt.get_or_none(agent_type=AgentType.AGENT)
    if existing_prompt:
        print("  Prompt (agent) already exists, skipping.")
    else:
        if not AGENT_MD_PATH.exists():
            print(f"✗ agent.md not found at {AGENT_MD_PATH}")
            sys.exit(1)
        prompt_content = AGENT_MD_PATH.read_text(encoding="utf-8")
        await Prompt.create(agent_type=AgentType.AGENT, content=prompt_content)
        print("✓ Prompt (agent) created from agent.md")

    # --- CompanyUser ---
    if user_email:
        user = await User.filter(email=user_email.lower()).first()
        if not user:
            print(f"✗ User '{user_email}' not found. Create it first with scripts.create_superuser.")
            sys.exit(1)
        existing_cu = await CompanyUser.filter(user=user, company=company).first()
        if existing_cu:
            print(f"  CompanyUser '{user_email}' → '{company.name}' already exists, skipping.")
        else:
            await CompanyUser.create(user=user, company=company, role=UserRole.OWNER)
            print(f"✓ CompanyUser created: '{user_email}' as owner of '{company.name}'")

    print()
    print("Done. Minimum seed complete.")


async def run(args: argparse.Namespace) -> None:
    settings = get_settings()

    if not ping_database_host(settings.resolved_database_url):
        sys.exit(1)

    config = tortoise_config(db_url=settings.resolved_database_url)
    try:
        await asyncio.wait_for(Tortoise.init(config=config), timeout=CONNECTION_TIMEOUT_SECONDS)
    except TimeoutError:
        print(f"✗ Database connection timed out after {CONNECTION_TIMEOUT_SECONDS}s")
        sys.exit(1)

    try:
        await seed(
            company_name=args.company_name,
            company_description=args.company_description,
            assistant_name=args.assistant_name,
            rules=args.rules,
            tone_of_voice=args.tone_of_voice,
            qualification_workflow=args.qualification_workflow,
            qualification_examples=args.qualification_examples,
            collection_name=args.collection_name,
            user_email=args.user_email,
        )
    finally:
        await Tortoise.close_connections()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed the database with minimum required data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--company-name", default="My Company", dest="company_name")
    parser.add_argument("--company-description", default="Компания по продаже продуктов", dest="company_description")
    parser.add_argument("--assistant-name", default="Алиса", dest="assistant_name")
    parser.add_argument("--rules", default="Отвечай вежливо и по делу.", dest="rules")
    parser.add_argument("--tone-of-voice", default="Дружелюбный, профессиональный.", dest="tone_of_voice")
    parser.add_argument(
        "--qualification-workflow",
        default="1. Узнай имя клиента.\n2. Выясни потребность.\n3. Предложи решение.",
        dest="qualification_workflow",
    )
    parser.add_argument("--qualification-examples", default="", dest="qualification_examples")
    parser.add_argument("--collection-name", default="default", dest="collection_name")
    parser.add_argument(
        "--user-email", default=None, dest="user_email", help="Email of existing user to link as company owner"
    )

    args = parser.parse_args()

    print("Seeding database...")
    print()

    try:
        asyncio.run(run(args))
    except Exception as e:
        print(f"✗ Error: {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
