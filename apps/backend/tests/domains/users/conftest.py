"""Fixtures for users tests."""

import pytest

from src.backend.modules.users.repository import UsersRepository
from src.backend.modules.users.service import UsersService


@pytest.fixture
def users_service() -> UsersService:
    return UsersService(UsersRepository())
