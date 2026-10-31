from fastapi import APIRouter, Depends

from common.models.pagination import PaginatedResponse, PaginationParams

from src.backend.modules.auth.dependencies import CompanyManagerDep, CompanyViewerDep
from src.backend.modules.categories.dependencies import CategoriesServiceDep
from src.backend.modules.categories.schemas import (
    CategoryPatch,
    CategoryRequest,
    CategoryResponse,
)
from src.backend.modules.fields.dependencies import FieldsServiceDep
from src.backend.modules.fields.routers import _map_field_to_response
from src.backend.modules.fields.schemas import FieldResponse

router = APIRouter(prefix="/companies/{company_id}/categories", tags=["categories"])


@router.get("/", response_model=PaginatedResponse[CategoryResponse])
async def list_categories(
    company_id: int,
    categories_service: CategoriesServiceDep,
    viewer: CompanyViewerDep,
    pagination: PaginationParams = Depends(),
) -> PaginatedResponse[CategoryResponse]:
    categories, total = await categories_service.get_by_company_paginated(
        company_id, pagination.limit, pagination.offset
    )
    items = [
        CategoryResponse(
            id=c.id,
            company_id=company_id,
            name=c.name,
            description=c.description,
            rules=c.rules,
            examples=c.examples,
            workflow=c.workflow,
            enabled_tools=list(c.enabled_tools) if c.enabled_tools else [],
        )
        for c in categories
    ]
    return PaginatedResponse[CategoryResponse](
        items=items,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post("/")
async def create_category(
    company_id: int,
    request: CategoryRequest,
    categories_service: CategoriesServiceDep,
    manager: CompanyManagerDep,
) -> CategoryResponse:
    category = await categories_service.create(
        company_id=company_id,
        name=request.name,
        description=request.description,
        rules=request.rules,
        examples=request.examples,
        workflow=request.workflow,
        enabled_tools=request.enabled_tools,
    )
    return CategoryResponse(
        id=category.id,
        company_id=company_id,
        name=category.name,
        description=category.description,
        rules=category.rules,
        examples=category.examples,
        workflow=category.workflow,
        enabled_tools=list(category.enabled_tools) if category.enabled_tools else [],
    )


@router.get("/{category_id}")
async def get_category(
    company_id: int,
    category_id: int,
    categories_service: CategoriesServiceDep,
    viewer: CompanyViewerDep,
) -> CategoryResponse:
    category = await categories_service.get_by_id(category_id, company_id)
    return CategoryResponse(
        id=category.id,
        company_id=company_id,
        name=category.name,
        description=category.description,
        rules=category.rules,
        examples=category.examples,
        workflow=category.workflow,
        enabled_tools=list(category.enabled_tools) if category.enabled_tools else [],
    )


@router.patch("/{category_id}")
async def update_category(
    company_id: int,
    category_id: int,
    request: CategoryPatch,
    categories_service: CategoriesServiceDep,
    manager: CompanyManagerDep,
) -> CategoryResponse:
    updates = request.model_dump(exclude_unset=True)
    category = await categories_service.update(category_id, company_id, **updates)
    return CategoryResponse(
        id=category.id,
        company_id=company_id,
        name=category.name,
        description=category.description,
        rules=category.rules,
        examples=category.examples,
        workflow=category.workflow,
        enabled_tools=list(category.enabled_tools) if category.enabled_tools else [],
    )


@router.delete("/{category_id}")
async def delete_category(
    company_id: int,
    category_id: int,
    categories_service: CategoriesServiceDep,
    manager: CompanyManagerDep,
) -> dict:
    await categories_service.delete(category_id, company_id)
    return {"message": "Category deleted successfully"}


@router.get("/{category_id}/fields", response_model=PaginatedResponse[FieldResponse])
async def list_category_fields(
    company_id: int,
    category_id: int,
    categories_service: CategoriesServiceDep,
    fields_service: FieldsServiceDep,
    viewer: CompanyViewerDep,
    pagination: PaginationParams = Depends(),
) -> PaginatedResponse[FieldResponse]:
    await categories_service.get_by_id(category_id, company_id)
    fields, total = await fields_service.list_fields_by_category_paginated(
        category_id, pagination.limit, pagination.offset
    )
    items = [await _map_field_to_response(field) for field in fields]
    return PaginatedResponse[FieldResponse](
        items=items,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )
