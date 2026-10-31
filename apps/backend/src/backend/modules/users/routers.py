from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from common.models.pagination import PaginatedResponse, PaginationParams

from src.backend.modules.auth.dependencies import (
    CompanyManagerByCompanyUserIdDep,
    CompanyViewerByCompanyUserIdDep,
    CurrentUserDep,
)
from src.backend.modules.users.dependencies import UsersServiceDep
from src.backend.modules.users.models import CompanyUser
from src.backend.modules.users.schemas import (
    CompanyUserScheduleResponse,
    UpdateCompanyUserRequest,
    UpdateCompanyUserResponse,
    UpdateUserRequest,
    UserDetailResponse,
    UserThreadInfo,
)

router = APIRouter(prefix="/users", tags=["users"])
company_users_router = APIRouter(prefix="/company-users", tags=["company-users"])


@router.get("/me", response_model=UserDetailResponse)
async def get_current_user_info(
    current_user: CurrentUserDep,
    users_service: UsersServiceDep,
) -> UserDetailResponse:
    """Get detailed information about the current user including their companies."""
    return await users_service.get_user_detail(current_user)


@router.get("/me/threads", response_model=PaginatedResponse[UserThreadInfo])
async def get_current_user_threads(
    current_user: CurrentUserDep,
    users_service: UsersServiceDep,
    pagination: PaginationParams = Depends(),
) -> PaginatedResponse[UserThreadInfo]:
    """Get paginated list of threads assigned to the current user."""
    return await users_service.get_user_threads(current_user, pagination.limit, pagination.offset)


@router.patch("/me", response_model=UserDetailResponse)
async def update_current_user_info(
    request: UpdateUserRequest,
    current_user: CurrentUserDep,
    users_service: UsersServiceDep,
) -> UserDetailResponse:
    """Update current user's information."""
    return await users_service.update_user(
        current_user, request.first_name, request.last_name, request.email, request.password
    )


@company_users_router.patch(
    "/{company_user_id}",
    response_model=UpdateCompanyUserResponse,
)
async def update_company_user(
    company_user_id: int,
    request: UpdateCompanyUserRequest,
    users_service: UsersServiceDep,
    current_user: CompanyManagerByCompanyUserIdDep,
) -> UpdateCompanyUserResponse:
    """Update company user work schedule and availability."""
    company_user = await CompanyUser.get_or_none(id=company_user_id)
    if not company_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company user not found")

    await company_user.fetch_related("company", "user")

    work_schedule_dict = None
    if request.work_schedule is not None:
        work_schedule_dict = request.work_schedule.model_dump()

    updated_company_user = await users_service.update_company_user(
        company_user=company_user,
        work_schedule=work_schedule_dict,
        is_available=request.is_available,
    )

    return UpdateCompanyUserResponse(
        id=updated_company_user.id,
        work_schedule=updated_company_user.work_schedule,
        is_available=updated_company_user.is_available,
    )


@company_users_router.get(
    "/{company_user_id}/schedule",
    response_model=CompanyUserScheduleResponse,
)
async def get_company_user_schedule(
    company_user_id: int,
    users_service: UsersServiceDep,
    current_user: CompanyViewerByCompanyUserIdDep,
) -> CompanyUserScheduleResponse:
    """Get company user schedule with interpretation."""
    company_user = await CompanyUser.get_or_none(id=company_user_id)
    if not company_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company user not found")

    await company_user.fetch_related("company")

    return await users_service.get_company_user_schedule(company_user)
