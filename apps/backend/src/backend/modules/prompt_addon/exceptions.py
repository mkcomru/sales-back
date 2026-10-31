from fastapi import status
from fastapi.requests import Request
from fastapi.responses import JSONResponse


class PromptAddonNotFoundError(Exception):
    """Raised when requested prompt addon not found."""


async def prompt_addon_not_found_handler(request: Request, exc: PromptAddonNotFoundError):  # noqa: ARG001
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"message": "Prompt addon not found"},
    )
