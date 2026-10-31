from functools import lru_cache
from typing import Any

from common import WappiModuleSettings


class Settings(WappiModuleSettings):
    """Wappi module specific settings derived from shared defaults."""

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
