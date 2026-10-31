"""Stage template API endpoints."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, status

from src.backend.modules.auth.dependencies import require_company_manager, require_company_viewer
from src.backend.modules.stages.dependencies import StagesServiceDep
from src.backend.modules.stages.schemas import (
    RecalculateCompanyOrdersStagesResponse,
    StageReorderRequest,
    StageTemplateCreateRequest,
    StageTemplateResponse,
    StageTemplateUpdateRequest,
)
from src.backend.modules.users.models import CompanyUser

log = structlog.get_logger(__name__)

public_router = APIRouter(prefix="/companies/{company_id}/stages", tags=["stages"])


@public_router.get(
    "",
    response_model=list[StageTemplateResponse],
    dependencies=[Depends(require_company_viewer)],
)
async def list_stages(
    stages_service: StagesServiceDep,
    company_id: int = Path(..., description="Company ID"),
) -> list[StageTemplateResponse]:
    """List all stages for a company, sorted by position."""
    stages = await stages_service.list_stages(company_id)
    return [StageTemplateResponse.from_model(stage) for stage in stages]


@public_router.post(
    "",
    response_model=StageTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_company_manager)],
)
async def create_stage(
    request: StageTemplateCreateRequest,
    stages_service: StagesServiceDep,
    current_user: CompanyUser = Depends(require_company_manager),
    company_id: int = Path(..., description="Company ID"),
) -> StageTemplateResponse:
    """Create a new stage template."""
    try:
        stage = await stages_service.create_stage(
            company_id=company_id,
            name=request.name,
            position=request.position,
            color=request.color,
            is_final=request.is_final,
            auto_close=request.auto_close,
            transition_condition=request.transition_condition,
        )
        return StageTemplateResponse.from_model(stage)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@public_router.get(
    "/{stage_id}",
    response_model=StageTemplateResponse,
    dependencies=[Depends(require_company_viewer)],
)
async def get_stage(
    stages_service: StagesServiceDep,
    company_id: int = Path(..., description="Company ID"),
    stage_id: int = Path(..., description="Stage ID"),
) -> StageTemplateResponse:
    """Get stage by ID."""
    stage = await stages_service.get_stage(company_id, stage_id)
    if not stage:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")
    return StageTemplateResponse.from_model(stage)


@public_router.patch(
    "/{stage_id}",
    response_model=StageTemplateResponse,
    dependencies=[Depends(require_company_manager)],
)
async def update_stage(
    request: StageTemplateUpdateRequest,
    stages_service: StagesServiceDep,
    current_user: CompanyUser = Depends(require_company_manager),
    company_id: int = Path(..., description="Company ID"),
    stage_id: int = Path(..., description="Stage ID"),
) -> StageTemplateResponse:
    """Update stage template."""
    stage = await stages_service.get_stage(company_id, stage_id)
    if not stage:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")

    try:
        updated_stage = await stages_service.update_stage(
            stage=stage,
            name=request.name,
            color=request.color,
            is_final=request.is_final,
            auto_close=request.auto_close,
            transition_condition=request.transition_condition,
        )
        return StageTemplateResponse.from_model(updated_stage)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@public_router.delete(
    "/{stage_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_company_manager)],
)
async def delete_stage(
    stages_service: StagesServiceDep,
    current_user: CompanyUser = Depends(require_company_manager),
    company_id: int = Path(..., description="Company ID"),
    stage_id: int = Path(..., description="Stage ID"),
) -> None:
    """Delete stage template."""
    stage = await stages_service.get_stage(company_id, stage_id)
    if not stage:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")

    try:
        await stages_service.delete_stage(stage)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@public_router.put(
    "/reorder",
    response_model=list[StageTemplateResponse],
    dependencies=[Depends(require_company_manager)],
)
async def reorder_stages(
    request: StageReorderRequest,
    stages_service: StagesServiceDep,
    current_user: CompanyUser = Depends(require_company_manager),
    company_id: int = Path(..., description="Company ID"),
) -> list[StageTemplateResponse]:
    """Reorder stages by assigning new positions based on stage_ids order."""
    try:
        stages = await stages_service.reorder_stages(company_id, request.stage_ids)
        return [StageTemplateResponse.from_model(stage) for stage in stages]
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@public_router.post(
    "/recalculate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RecalculateCompanyOrdersStagesResponse,
    dependencies=[Depends(require_company_manager)],
)
async def recalculate_company_orders_stages(
    stages_service: StagesServiceDep,
    company_id: int = Path(..., description="Company ID"),
) -> RecalculateCompanyOrdersStagesResponse:
    """Recalculate stages for all active orders in a company."""
    return await stages_service.recalculate_company_orders_stages(company_id)
