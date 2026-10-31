"""Exceptions for forms module."""

from fastapi import status
from fastapi.requests import Request
from fastapi.responses import JSONResponse


class FormNotFoundError(Exception):
    """Form template not found."""


class InvalidFormKeyError(Exception):
    """Invalid or disabled form API key."""


class FormValidationError(Exception):
    """Form validation error."""


async def form_not_found_handler(request: Request, exc: FormNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"message": "Form not found"},
    )


async def form_validation_error_handler(request: Request, exc: FormValidationError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"message": str(exc)},
    )
