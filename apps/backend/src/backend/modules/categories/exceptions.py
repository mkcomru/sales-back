from fastapi import status
from fastapi.requests import Request
from fastapi.responses import JSONResponse


class CategoryNotFoundError(Exception):
    """Raised when requested category not found"""


async def category_not_found_handler(request: Request, exc: CategoryNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"message": "Category not found"},
    )
