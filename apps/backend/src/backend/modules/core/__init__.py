"""Core package exports."""

from src.backend.modules.core.base_model import BaseModel
from src.backend.modules.core.base_repo import BaseRepository, ModelType
from src.backend.modules.core.dependencies import SettingsDep, require_service_api_key
from src.backend.modules.core.settings import Settings, get_settings

__all__ = [
    "BaseModel",
    "BaseRepository",
    "ModelType",
    "Settings",
    "get_settings",
    "SettingsDep",
    "require_service_api_key",
]
