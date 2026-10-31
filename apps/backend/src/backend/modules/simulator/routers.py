from fastapi import APIRouter, Path, status

from src.backend.modules.auth.dependencies import CompanyAdminDep
from src.backend.modules.simulator.dependencies import SimulatorServiceDep
from src.backend.modules.simulator.schemas import (
    SimulatorMessageRequest,
    SimulatorMessageResponse,
    SimulatorResetResponse,
)

router = APIRouter(prefix="/companies/{company_id}/simulator", tags=["simulator"])


@router.post(
    "/reset",
    response_model=SimulatorResetResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset simulator session",
    description="Clear test conversation history and start fresh simulation",
)
async def reset_simulator_session(
    admin: CompanyAdminDep,
    service: SimulatorServiceDep,
    company_id: int = Path(..., ge=1, description="Company ID"),
) -> SimulatorResetResponse:
    """Reset simulator session for current company user."""
    return await service.reset_session(
        company_id=company_id,
        user_id=admin.user_id,
    )


@router.post(
    "/message",
    response_model=SimulatorMessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Send message to simulator",
    description="Send test message to AI agent and get response in isolated sandbox",
)
async def send_simulator_message(
    request: SimulatorMessageRequest,
    admin: CompanyAdminDep,
    service: SimulatorServiceDep,
    company_id: int = Path(..., ge=1, description="Company ID"),
) -> SimulatorMessageResponse:
    """Process message in simulator and return AI response."""
    return await service.process_message(
        company_id=company_id,
        user_id=admin.user_id,
        text=request.text,
    )
