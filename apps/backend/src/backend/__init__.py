"""Backend package exports."""

from src.backend.modules.core.database import close, init, tortoise_config
from src.backend.modules.core.settings import get_settings


class _DB:
    async def init(self):
        return await init()

    async def close(self):
        return await close()


db = _DB()


def __getattr__(name: str):
    """Dynamic attribute access for Aerich compatibility."""
    if name == "TORTOISE_ORM":
        return tortoise_config(db_url=get_settings().resolved_database_url)
    raise AttributeError(f"module 'src.backend' has no attribute '{name}'")
