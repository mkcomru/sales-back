"""Database configuration helpers for Tortoise ORM.

IMPORTANT: Aerich Schema Limitation
====================================
Aerich does NOT automatically add schema qualifiers to generated migrations.
After running `aerich migrate --name <name>`, you MUST manually edit the
migration file to add "backend" prefix to all table names:

    Before: CREATE TABLE "table_name" (...)
    After:  CREATE TABLE "backend"."table_name" (...)

This is required because Aerich ignores Meta.schema when generating SQL.
See docs/tech.md for full explanation.
"""

import logging
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from aerich.models import Aerich
from tortoise import Tortoise

from src.backend.modules.core.settings import get_settings

log = logging.getLogger(__name__)


def _configure_sql_logging() -> None:
    """SQL query logging is controlled by setup_logging() in common.logging_setup."""
    pass


# AICODE-NOTE: Override Aerich model schema to match backend
# Without this, Aerich creates/reads from public.aerich while our tables
# are in backend schema, causing duplicate migration tracking
Aerich._meta.schema = "backend"


def tortoise_config(db_url: str) -> dict[str, Any]:
    parsed = urlparse(db_url)
    query_params = parse_qs(parsed.query)

    if parsed.scheme == "sqlite":
        file_path = parsed.path.lstrip("/") if parsed.path else ":memory:"
        return {
            "connections": {
                "default": {
                    "engine": "tortoise.backends.sqlite",
                    "credentials": {"file_path": file_path},
                }
            },
            "apps": {
                "models": {
                    "models": [
                        "src.backend.modules.core.models",
                        "aerich.models",
                    ],
                    "default_connection": "default",
                }
            },
            "use_tz": True,
            "timezone": "UTC",
        }

    if not parsed.hostname:
        raise ValueError("Database URL must include hostname")
    if not parsed.port:
        raise ValueError("Database URL must include port")
    if not parsed.username:
        raise ValueError("Database URL must include username")
    if parsed.password is None:
        raise ValueError("Database URL must include password")
    if not parsed.path or not parsed.path.lstrip("/"):
        raise ValueError("Database URL must include database name")

    credentials: dict[str, Any] = {
        "host": parsed.hostname,
        "port": parsed.port,
        "user": parsed.username,
        "password": unquote(parsed.password),
        "database": parsed.path.lstrip("/"),
        "minsize": 5,
        "maxsize": 20,
        "command_timeout": 30,
    }

    if query_params.get("sslmode"):
        credentials["ssl"] = query_params["sslmode"][0]

    return {
        "connections": {
            "default": {
                "engine": "tortoise.backends.asyncpg",
                "credentials": credentials,
            }
        },
        "apps": {
            "models": {
                "models": [
                    "src.backend.modules.core.models",
                    "aerich.models",
                ],
                "default_connection": "default",
            }
        },
        "use_tz": True,
        "timezone": "UTC",
    }


async def init():
    log.info("db.init.start")

    await Tortoise.init(config=tortoise_config(db_url=get_settings().resolved_database_url))
    _configure_sql_logging()

    log.info("db.init.ready")


async def close():
    try:
        await Tortoise.close_connections()
        log.info("db.close.success")
    except Exception as e:
        log.warning("db.close.error: %s", str(e))
