from fastapi import status
from fastapi.requests import Request
from fastapi.responses import JSONResponse


class FieldNotFoundError(Exception):
    """Raised when requested field not found"""


class FieldOptionNotFoundError(Exception):
    """Raised when requested field option not found"""


class SystemFieldError(Exception):
    """Raised when trying to delete or modify system field"""


async def field_not_found_handler(request: Request, exc: FieldNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"message": "Field not found"},
    )


async def field_option_not_found_handler(request: Request, exc: FieldOptionNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"message": "Field option not found"},
    )


async def system_field_error_handler(request: Request, exc: SystemFieldError):
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={"message": str(exc)},
    )
