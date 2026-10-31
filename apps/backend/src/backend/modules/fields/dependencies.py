from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from src.backend.modules.fields.service import FieldOptionsService, FieldsService


@lru_cache
def fields() -> FieldsService:
    return FieldsService()


@lru_cache
def field_options() -> FieldOptionsService:
    return FieldOptionsService()


FieldsServiceDep = Annotated[FieldsService, Depends(fields)]
FieldOptionsServiceDep = Annotated[FieldOptionsService, Depends(field_options)]
