from __future__ import annotations

from fastapi import APIRouter

from src.backend.modules.auth.dependencies import CompanyAdminDep
from src.backend.modules.integrations.dependencies import IntegrationServiceDep
from src.backend.modules.integrations.registry import PROVIDER_CATALOG
from src.backend.modules.integrations.schemas import (
    IntegrationCreate,
    IntegrationResponse,
    IntegrationUpdate,
    ProviderCatalogEntry,
)

router = APIRouter(
    prefix="/companies/{company_id}/integrations",
    tags=["integrations"],
)


@router.get("/catalog", response_model=list[ProviderCatalogEntry])
async def list_available_providers(
    company_id: int,
    user: CompanyAdminDep,
) -> list[ProviderCatalogEntry]:
    """Return all registered integration providers the frontend can offer to connect."""
    return list(PROVIDER_CATALOG.values())


@router.get("", response_model=list[IntegrationResponse])
async def list_integrations(
    company_id: int,
    service: IntegrationServiceDep,
    user: CompanyAdminDep,
) -> list[IntegrationResponse]:
    integrations = await service.list_for_company(company_id)
    return [
        IntegrationResponse(
            id=i.id,
            company_id=i.company_id,
            provider_type=i.provider_type,
            config=i.config,
            enabled_capabilities=i.enabled_capabilities,
            enabled=i.enabled,
        )
        for i in integrations
    ]


@router.post("", response_model=IntegrationResponse, status_code=201)
async def create_integration(
    company_id: int,
    body: IntegrationCreate,
    service: IntegrationServiceDep,
    user: CompanyAdminDep,
) -> IntegrationResponse:
    integration = await service.create(
        company_id=company_id,
        provider_type=body.provider_type,
        credentials=body.credentials,
        config=body.config,
        enabled_capabilities=body.enabled_capabilities,
        enabled=body.enabled,
    )
    return IntegrationResponse(
        id=integration.id,
        company_id=integration.company_id,
        provider_type=integration.provider_type,
        config=integration.config,
        enabled_capabilities=integration.enabled_capabilities,
        enabled=integration.enabled,
    )


@router.get("/{integration_id}", response_model=IntegrationResponse)
async def get_integration(
    company_id: int,
    integration_id: int,
    service: IntegrationServiceDep,
    user: CompanyAdminDep,
) -> IntegrationResponse:
    integration = await service.get(integration_id)
    return IntegrationResponse(
        id=integration.id,
        company_id=integration.company_id,
        provider_type=integration.provider_type,
        config=integration.config,
        enabled_capabilities=integration.enabled_capabilities,
        enabled=integration.enabled,
    )


@router.patch("/{integration_id}", response_model=IntegrationResponse)
async def update_integration(
    company_id: int,
    integration_id: int,
    body: IntegrationUpdate,
    service: IntegrationServiceDep,
    user: CompanyAdminDep,
) -> IntegrationResponse:
    integration = await service.update(
        integration_id,
        credentials=body.credentials,
        config=body.config,
        enabled_capabilities=body.enabled_capabilities,
        enabled=body.enabled,
    )
    return IntegrationResponse(
        id=integration.id,
        company_id=integration.company_id,
        provider_type=integration.provider_type,
        config=integration.config,
        enabled_capabilities=integration.enabled_capabilities,
        enabled=integration.enabled,
    )


@router.delete("/{integration_id}", status_code=204)
async def delete_integration(
    company_id: int,
    integration_id: int,
    service: IntegrationServiceDep,
    user: CompanyAdminDep,
) -> None:
    await service.delete(integration_id)
