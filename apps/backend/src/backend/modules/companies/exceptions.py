from fastapi import status
from fastapi.requests import Request
from fastapi.responses import JSONResponse


class CompanyNotFoundError(Exception):
    """Raised when requested company not found"""


class FAQNotFoundError(Exception):
    """Raised when requested FAQ not found"""


async def company_not_found_handler(request: Request, exc: CompanyNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"message": "Company not found"},
    )


async def faq_not_found_handler(request: Request, exc: FAQNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"message": "FAQ not found"},
    )
