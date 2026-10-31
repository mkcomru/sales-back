from fastapi import status
from fastapi.requests import Request
from fastapi.responses import JSONResponse


class SimulatorSessionNotFoundError(Exception):
    """Raised when requested simulator session not found"""


async def simulator_session_not_found_handler(request: Request, exc: SimulatorSessionNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"message": "The requested simulator session not found"},
    )
