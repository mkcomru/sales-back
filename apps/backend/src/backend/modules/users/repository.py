from src.backend.modules.core.base_repo import BaseRepository
from src.backend.modules.users.models import CompanyUser, User


class UsersRepository(BaseRepository):
    def __init__(self):
        super().__init__(User)

    async def update_user(
        self,
        user_id: int,
        first_name: str | None,
        last_name: str | None,
        email: str | None,
        hashed_password: str | None,
    ) -> User:
        user = await User.get(id=user_id)
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name
        if email is not None:
            user.email = email.lower()
        if hashed_password is not None:
            user.hashed_password = hashed_password
        await user.save()
        return user


class CompanyUsersRepository(BaseRepository):
    def __init__(self):
        super().__init__(CompanyUser)
