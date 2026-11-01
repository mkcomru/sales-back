"""Customer store — write-only facade to backend.

All read operations eliminated: data comes in envelope's AgentContext.
"""

from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger()

_backend_client = None


def set_backend_client(client, company_id: int = 1) -> None:
    global _backend_client
    _backend_client = client


def get_backend_client():
    if _backend_client is None:
        raise RuntimeError("BackendClient not initialized. Call set_backend_client() during startup.")
    return _backend_client


async def update_customer_fields(user_id: int | str, company_id: int, updates: dict[str, Any]) -> None:
    if company_id is None:
        raise ValueError("company_id is required")
    client = get_backend_client()
    await client.update_customer_fields(str(user_id), company_id, updates)
    log.debug("store.update_fields", user_id=user_id, fields=list(updates.keys()))


async def reset_customer_profile(user_id: int | str, company_id: int) -> None:
    if company_id is None:
        raise ValueError("company_id is required")
    client = get_backend_client()
    await client.reset_customer_profile(str(user_id), company_id)
    log.info("store.reset_profile", user_id=user_id)
