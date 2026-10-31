from typing import Annotated

from fastapi import Depends

from src.backend.modules.users.repository import UsersRepository
from src.backend.modules.users.service import UsersService


def get_users_repository() -> UsersRepository:
    return UsersRepository()


def get_users_service(users_repository: Annotated[UsersRepository, Depends(get_users_repository)]) -> UsersService:
    return UsersService(users_repository)


UsersServiceDep = Annotated[UsersService, Depends(get_users_service)]
