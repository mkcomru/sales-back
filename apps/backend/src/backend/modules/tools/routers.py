from fastapi import APIRouter

from src.backend.modules.auth.dependencies import CompanyViewerDep
from src.backend.modules.tools.dependencies import ToolsServiceDep
from src.backend.modules.tools.schemas import ToolGroupResponse

router = APIRouter(prefix="/companies/{company_id}/tools", tags=["tools"])


@router.get("/available", response_model=list[ToolGroupResponse])
async def list_available_tools(
    company_id: int,
    tools_service: ToolsServiceDep,
    user: CompanyViewerDep,
) -> list[ToolGroupResponse]:
    """Get catalog of available tools grouped by ToolGroup, filtered by active integrations."""
    return await tools_service.list_available(company_id)
