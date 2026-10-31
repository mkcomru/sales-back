from fastapi import status
from fastapi.requests import Request
from fastapi.responses import JSONResponse


class IntegrationNotFoundError(Exception):
    """Raised when requested integration not found."""


class IntegrationConflictError(Exception):
    """Raised when multiple integrations override the same service for a company."""


class IntegrationCapabilityConflictError(Exception):
    """Raised when a new/updated integration has overlapping capabilities with an existing one."""


async def integration_not_found_handler(request: Request, exc: IntegrationNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"message": str(exc) or "Integration not found"},
    )


async def integration_conflict_handler(request: Request, exc: IntegrationConflictError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"message": str(exc)},
    )


async def integration_capability_conflict_handler(
    request: Request, exc: IntegrationCapabilityConflictError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"message": str(exc)},
    )
