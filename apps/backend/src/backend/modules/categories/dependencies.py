from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from src.backend.modules.categories.service import CategoriesService


@lru_cache
def categories() -> CategoriesService:
    return CategoriesService()


CategoriesServiceDep = Annotated[CategoriesService, Depends(categories)]
