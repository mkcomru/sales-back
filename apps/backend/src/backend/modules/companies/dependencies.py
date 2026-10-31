from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from src.backend.modules.companies.service import CompaniesService, FAQsService
from src.backend.modules.users.dependencies import UsersServiceDep


@lru_cache
def faqs() -> FAQsService:
    return FAQsService()


def companies(users_service: UsersServiceDep) -> CompaniesService:
    return CompaniesService(users_service=users_service)


CompaniesServiceDep = Annotated[CompaniesService, Depends(companies)]
FAQsServiceDep = Annotated[FAQsService, Depends(faqs)]
