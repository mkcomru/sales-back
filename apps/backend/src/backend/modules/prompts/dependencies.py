from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from src.backend.modules.prompts.service import PromptsService


@lru_cache
def prompts() -> PromptsService:
    return PromptsService()


PromptsServiceDep = Annotated[PromptsService, Depends(prompts)]
