from fastapi import APIRouter, status

from src.backend.modules.auth.dependencies import CompanyAdminDep
from src.backend.modules.prompt_addon.dependencies import PromptAddonsServiceDep
from src.backend.modules.prompt_addon.schemas import (
    PromptAddonPatch,
    PromptAddonRequest,
    PromptAddonResponse,
)

router = APIRouter(prefix="/companies/{company_id}/prompt-addons", tags=["prompt-addons"])


@router.get("", response_model=list[PromptAddonResponse])
async def list_prompt_addons(
    company_id: int,
    service: PromptAddonsServiceDep,
    admin: CompanyAdminDep,
) -> list[PromptAddonResponse]:
    """List all prompt addons for a company."""
    return await service.list_addons(company_id)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PromptAddonResponse)
async def create_prompt_addon(
    company_id: int,
    request: PromptAddonRequest,
    service: PromptAddonsServiceDep,
    admin: CompanyAdminDep,
) -> PromptAddonResponse:
    """Create a new prompt addon for a company."""
    return await service.create_addon(
        company_id=company_id,
        name=request.name,
        qualification_workflow=request.qualification_workflow,
        qualification_examples=request.qualification_examples,
    )


@router.get("/{addon_id}", response_model=PromptAddonResponse)
async def get_prompt_addon(
    company_id: int,
    addon_id: int,
    service: PromptAddonsServiceDep,
    admin: CompanyAdminDep,
) -> PromptAddonResponse:
    """Get a specific prompt addon."""
    return await service.get_addon(company_id, addon_id)


@router.put("/{addon_id}", response_model=PromptAddonResponse)
async def update_prompt_addon(
    company_id: int,
    addon_id: int,
    request: PromptAddonPatch,
    service: PromptAddonsServiceDep,
    admin: CompanyAdminDep,
) -> PromptAddonResponse:
    """Update a prompt addon."""
    return await service.update_addon(company_id, addon_id, request)


@router.delete("/{addon_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt_addon(
    company_id: int,
    addon_id: int,
    service: PromptAddonsServiceDep,
    admin: CompanyAdminDep,
):
    """Delete a prompt addon."""
    await service.delete_addon(company_id, addon_id)
