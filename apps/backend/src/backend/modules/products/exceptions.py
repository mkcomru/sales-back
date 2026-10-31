from fastapi import status
from fastapi.requests import Request
from fastapi.responses import JSONResponse


class ProductNotFoundError(Exception):
    """Raised when requested product not found"""


async def product_not_found_handler(request: Request, exc: ProductNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"message": "The requested product not found in collection"},
    )
