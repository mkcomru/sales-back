#!/usr/bin/env python3
"""One-time migration: encrypt plaintext credentials stored in Connector.config.

Idempotent: skips connectors whose sensitive fields are already encrypted
(a present sensitive field is a dict, not a string).

Usage:
    cd apps/backend
    uv run python -m scripts.encrypt_connector_credentials

Requirements:
    - Run from apps/backend (or use: just script encrypt_connector_credentials)
    - DATABASE__URL and ENCRYPTION__MASTER_KEY environment variables configured
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import traceback

from src.backend.modules.core.database import close, init
from src.backend.modules.transport.models import Connector
from src.backend.modules.transport.service import SENSITIVE_FIELDS, ConnectorsService


def print_info(msg: str) -> None:
    print(f"[INFO] {msg}")


def print_success(msg: str) -> None:
    print(f"[SUCCESS] {msg}")


def print_error(msg: str) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)


async def encrypt_connector_credentials() -> int:
    connectors = await Connector.filter(config__not={}).all()
    if not connectors:
        print_info("No connectors with non-empty config found.")
        return 0

    service = ConnectorsService()
    encrypted = 0
    skipped = 0
    failed = 0

    for connector in connectors:
        sensitive = SENSITIVE_FIELDS[connector.type]
        if not sensitive:
            skipped += 1
            continue

        config = dict(connector.config or {})

        already_encrypted = any(isinstance(config.get(field), dict) for field in sensitive if field in config)
        if already_encrypted:
            print_info(f"Skip (already encrypted): connector_id={connector.connector_id} type={connector.type.value}")
            skipped += 1
            continue

        try:
            connector.config = service._encrypt_config(connector.type, config)  # noqa: SLF001
            await connector.save(update_fields=["config"])
            print_success(f"Encrypted: connector_id={connector.connector_id} type={connector.type.value}")
            encrypted += 1
        except Exception:
            traceback.print_exc()
            print_error(f"Failed: connector_id={connector.connector_id} type={connector.type.value}")
            failed += 1

    print("\n[SUMMARY]")
    print(f"  encrypted: {encrypted}")
    print(f"  skipped:   {skipped}")
    print(f"  failed:    {failed}")

    return 1 if failed else 0


async def main() -> None:
    parser = argparse.ArgumentParser(description="Encrypt plaintext connector credentials in the database")
    parser.parse_args()

    await init()
    try:
        exit_code = await encrypt_connector_credentials()
    finally:
        await close()

    if exit_code:
        sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
