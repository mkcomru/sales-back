from fastapi import status
from fastapi.requests import Request
from fastapi.responses import JSONResponse


class UserAlreadyExistsError(Exception):
    """Raised when trying to create a user that already exists"""


async def user_already_exists_handler(request: Request, exc: UserAlreadyExistsError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "User with this email already exists"},
    )
