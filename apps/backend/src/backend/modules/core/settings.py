from functools import lru_cache

from common import BackendModuleSettings


class Settings(BackendModuleSettings):
    """Backend module specific settings derived from common defaults."""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
