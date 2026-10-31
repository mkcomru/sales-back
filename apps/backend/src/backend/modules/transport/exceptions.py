from fastapi import status
from fastapi.requests import Request
from fastapi.responses import JSONResponse


class ConnectorNotFoundError(Exception):
    """Raised when requested connector not found or auth failed."""


async def connector_not_found_handler(request: Request, exc: ConnectorNotFoundError):  # noqa: ARG001
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": "connector_not_found"},
    )
