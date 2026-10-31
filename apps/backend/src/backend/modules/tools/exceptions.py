from fastapi import status
from fastapi.requests import Request
from fastapi.responses import JSONResponse


class ToolNotFoundError(Exception):
    """Raised when requested tool not found"""


async def tool_not_found_handler(request: Request, exc: ToolNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"message": "Tool not found"},
    )
