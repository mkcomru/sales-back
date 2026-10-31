from fastapi import status
from fastapi.requests import Request
from fastapi.responses import JSONResponse


class PromptNotFoundError(Exception):
    """Raised when requested prompt not found"""


async def prompt_not_found_handler(request: Request, exc: PromptNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"message": "Prompt not found for this agent type"},
    )
