from fastapi import APIRouter, Depends, HTTPException, Path, status

from common.models.pagination import PaginatedResponse, PaginationParams

from src.backend.modules.auth.dependencies import (
    CompanyAdminDep,
    CompanyManagerDep,
    CompanyOwnerDep,
    CompanyViewerDep,
    CurrentUserDep,
    SuperuserDep,
)
from src.backend.modules.companies.dependencies import (
    CompaniesServiceDep,
    FAQsServiceDep,
)
from src.backend.modules.companies.schemas import (
    AddCompanyMemberRequest,
    CompanyConfigResponse,
    CompanyMemberResponse,
    CompanyPatch,
    CompanyRequest,
    CompanyResponse,
    CompanySpecificationResponse,
    FAQPatch,
    FAQRequest,
    FAQResponse,
)
from src.backend.modules.core.dependencies import require_service_api_key
from src.backend.modules.prompt_addon.schemas import ConnectorPromptAddonPatch
from src.backend.modules.transport.dependencies import ConnectorsServiceDep
from src.backend.modules.transport.schemas import ConnectorCreateRequest, ConnectorResponse
from src.backend.modules.users.dependencies import UsersServiceDep
from src.backend.modules.users.models import CompanyUser
from src.backend.modules.users.schemas import AvailableManagerInfo

public_router = APIRouter(prefix="/companies", tags=["companies"])
internal_router = APIRouter(
    prefix="/internal/companies",
    tags=["companies:internal"],
    dependencies=[Depends(require_service_api_key)],
)


@internal_router.get("/{company_id}/specification")
async def get_company_specification(
    company_id: int,
    companies_service: CompaniesServiceDep,
) -> CompanySpecificationResponse:
    """Get complete company specification for Sales Agent.

    Returns all data needed for the agent in one request:
    - Company config (rules, tone, stages, routing)
    - All products with fields, geo, handoff configs
    - Custom fields with options
    - FAQs knowledge base
    """
    spec = await companies_service.get_specification(company_id)
    return CompanySpecificationResponse(**spec)


@public_router.get("", response_model=list[CompanyResponse])
async def list_companies(
    companies_service: CompaniesServiceDep,
    current_user: CurrentUserDep,
) -> list[CompanyResponse]:
    if current_user.is_superuser:
        return await companies_service.list_companies()
    return await companies_service.list_companies_for_user(current_user.id)


@public_router.post("", status_code=status.HTTP_201_CREATED)
async def create_company(
    request: CompanyRequest,
    companies_service: CompaniesServiceDep,
    superuser: SuperuserDep,
) -> CompanyResponse:
    return await companies_service.create_company(creator_id=superuser.id, **request.model_dump())


@public_router.get("/{company_id}")
async def get_company(
    company_id: int,
    companies_service: CompaniesServiceDep,
    viewer: CompanyViewerDep,
) -> CompanyResponse:
    return await companies_service.get_company(company_id)


@public_router.patch("/{company_id}")
async def update_company(
    company_id: int,
    request: CompanyPatch,
    companies_service: CompaniesServiceDep,
    admin: CompanyAdminDep,
) -> CompanyResponse:
    updates = request.model_dump(exclude_unset=True)
    return await companies_service.update_company(company_id, updates)


@public_router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id: int,
    companies_service: CompaniesServiceDep,
    owner: CompanyOwnerDep,
):
    await companies_service.delete_company(company_id)


@public_router.get("/{company_id}/managers", response_model=list[CompanyMemberResponse])
async def get_company_managers(
    company_id: int,
    companies_service: CompaniesServiceDep,
    admin: CompanyAdminDep,
) -> list[CompanyMemberResponse]:
    """Get all managers of the company.

    Returns all users with MANAGER, ADMIN, or OWNER roles.
    Requires ADMIN+ access to the company or superuser access.
    """
    managers = await companies_service.get_company_managers(company_id)
    return [CompanyMemberResponse(**manager) for manager in managers]


@public_router.post(
    "/{company_id}/members",
    status_code=status.HTTP_201_CREATED,
    response_model=CompanyMemberResponse,
)
async def add_company_member(
    company_id: int,
    request: AddCompanyMemberRequest,
    companies_service: CompaniesServiceDep,
    admin: CompanyAdminDep,
) -> CompanyMemberResponse:
    """Add a new member to the company. Creates user if new, or links existing user by email."""
    try:
        return await companies_service.add_company_member(
            company_id=company_id,
            first_name=request.first_name,
            last_name=request.last_name,
            email=request.email,
            password=request.password,
            role=request.role,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@public_router.get("/{company_id}/config")
async def get_company_config(
    company_id: int,
    companies_service: CompaniesServiceDep,
    viewer: CompanyViewerDep,
) -> CompanyConfigResponse:
    return await companies_service.get_config(company_id)


@public_router.get("/{company_id}/faqs", response_model=PaginatedResponse[FAQResponse])
async def list_company_faqs(
    company_id: int,
    faqs_service: FAQsServiceDep,
    viewer: CompanyViewerDep,
    pagination: PaginationParams = Depends(),
) -> PaginatedResponse[FAQResponse]:
    items, total = await faqs_service.list_faqs_paginated(company_id, pagination.limit, pagination.offset)
    return PaginatedResponse[FAQResponse](
        items=items,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@public_router.post(
    "/{company_id}/faqs",
    status_code=status.HTTP_201_CREATED,
    response_model=FAQResponse,
)
async def create_company_faq(
    company_id: int,
    request: FAQRequest,
    faqs_service: FAQsServiceDep,
    manager: CompanyManagerDep,
) -> FAQResponse:
    return await faqs_service.create_faq(company_id, request)


@public_router.get("/{company_id}/faqs/search", response_model=list[FAQResponse])
async def search_company_faqs(
    company_id: int,
    q: str,
    faqs_service: FAQsServiceDep,
    viewer: CompanyViewerDep,
) -> list[FAQResponse]:
    return await faqs_service.search_faqs(company_id, q)


@public_router.get("/{company_id}/faqs/{faq_id}", response_model=FAQResponse)
async def get_company_faq(
    company_id: int,
    faq_id: int,
    faqs_service: FAQsServiceDep,
    viewer: CompanyViewerDep,
) -> FAQResponse:
    return await faqs_service.get_faq(faq_id, company_id)


@public_router.patch("/{company_id}/faqs/{faq_id}", response_model=FAQResponse)
async def update_company_faq(
    company_id: int,
    faq_id: int,
    request: FAQPatch,
    faqs_service: FAQsServiceDep,
    manager: CompanyManagerDep,
) -> FAQResponse:
    return await faqs_service.update_faq(faq_id, company_id, request)


@public_router.delete("/{company_id}/faqs/{faq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company_faq(
    company_id: int,
    faq_id: int,
    faqs_service: FAQsServiceDep,
    manager: CompanyManagerDep,
):
    await faqs_service.delete_faq(faq_id, company_id)


@public_router.get("/{company_id}/members", response_model=PaginatedResponse[CompanyMemberResponse])
async def list_company_members(
    company_id: int,
    viewer: CompanyViewerDep,
    pagination: PaginationParams = Depends(),
) -> PaginatedResponse[CompanyMemberResponse]:
    """List all members of a company for assignee selection dropdowns."""
    total = await CompanyUser.filter(company_id=company_id).count()
    company_users = (
        await CompanyUser.filter(company_id=company_id)
        .prefetch_related("user")
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )
    items = [
        CompanyMemberResponse(
            id=cu.id,
            user_id=cu.user.id,
            first_name=cu.user.first_name,
            last_name=cu.user.last_name,
            email=cu.user.email,
            role=cu.role.value,
            is_available=cu.is_available,
        )
        for cu in company_users
    ]
    return PaginatedResponse[CompanyMemberResponse](
        items=items,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@public_router.post(
    "/{company_id}/connectors",
    status_code=status.HTTP_201_CREATED,
    response_model=ConnectorResponse,
)
async def create_company_connector(
    company_id: int,
    request: ConnectorCreateRequest,
    connectors_service: ConnectorsServiceDep,
    admin: CompanyAdminDep,  # noqa: ARG001
) -> ConnectorResponse:
    """Create connector for company. Requires ADMIN+ in company."""
    if request.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="company_id must match path",
        )
    return await connectors_service.create_connector(request)


@public_router.get(
    "/{company_id}/connectors",
    response_model=list[ConnectorResponse],
)
async def list_company_connectors(
    company_id: int,
    connectors_service: ConnectorsServiceDep,
    viewer: CompanyViewerDep,  # noqa: ARG001
) -> list[ConnectorResponse]:
    """List connectors configured for a company."""
    return await connectors_service.list_by_company(company_id)


@public_router.patch(
    "/{company_id}/connectors/{connector_id}",
    response_model=ConnectorResponse,
)
async def update_connector_prompt_addon(
    company_id: int,
    connector_id: str,
    request: ConnectorPromptAddonPatch,
    connectors_service: ConnectorsServiceDep,
    admin: CompanyAdminDep,
) -> ConnectorResponse:
    """Assign or remove prompt addon for a connector."""
    return await connectors_service.update_connector_prompt_addon(
        company_id=company_id,
        connector_id=connector_id,
        prompt_addon_id=request.prompt_addon_id,
    )


@public_router.get(
    "/{company_id}/available-managers",
    response_model=list[AvailableManagerInfo],
)
async def get_available_managers(
    users_service: UsersServiceDep,
    viewer: CompanyViewerDep,
    company_id: int = Path(..., description="Company ID"),
) -> list[AvailableManagerInfo]:
    """Get list of available managers for a company."""
    return await users_service.get_available_managers(company_id)
