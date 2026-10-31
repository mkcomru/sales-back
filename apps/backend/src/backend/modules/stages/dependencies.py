"""Dependencies for stages module."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from src.backend.modules.stages.service import StagesService


@lru_cache
def stages_service() -> StagesService:
    return StagesService()


StagesServiceDep = Annotated[StagesService, Depends(stages_service)]
