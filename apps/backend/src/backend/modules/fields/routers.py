from fastapi import APIRouter, Depends, Query, status

from common.models.pagination import PaginatedResponse, PaginationParams

from src.backend.modules.auth.dependencies import (
    CompanyManagerDep,
    CompanyViewerDep,
)
from src.backend.modules.fields.dependencies import (
    FieldOptionsServiceDep,
    FieldsServiceDep,
)
from src.backend.modules.fields.models import FieldLevel
from src.backend.modules.fields.schemas import (
    FieldOptionPatch,
    FieldOptionRequest,
    FieldOptionResponse,
    FieldPatch,
    FieldRequest,
    FieldResponse,
)

router = APIRouter(prefix="/companies/{company_id}/fields", tags=["fields"])


def _serialize_field_option(option) -> FieldOptionResponse:
    return FieldOptionResponse(id=option.id, value=option.value, order=option.order)


def _map_field_to_response(field) -> FieldResponse:
    """Map field to response. Expects category, product, options to be prefetched."""
    return FieldResponse(
        id=field.id,
        name=field.name,
        question=field.question,
        type=field.answer_type.value,
        required=field.required,
        display_name=field.display_name,
        level=field.level,
        is_system=field.is_system,
        category_id=field.category.id if field.category else None,
        product_id=field.product.id if field.product else None,
        options=[_serialize_field_option(opt) for opt in field.options],
    )


@router.get("", response_model=PaginatedResponse[FieldResponse])
async def list_fields(
    company_id: int,
    fields_service: FieldsServiceDep,
    viewer: CompanyViewerDep,
    pagination: PaginationParams = Depends(),
    level: FieldLevel | None = Query(default=None, description="Filter by field level (customer or order)"),
) -> PaginatedResponse[FieldResponse]:
    fields, total = await fields_service.list_fields_paginated(company_id, pagination.limit, pagination.offset, level)
    return PaginatedResponse[FieldResponse](
        items=[_map_field_to_response(f) for f in fields],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=FieldResponse)
async def create_field(
    company_id: int,
    request: FieldRequest,
    fields_service: FieldsServiceDep,
    manager: CompanyManagerDep,
) -> FieldResponse:
    field = await fields_service.create_field(company_id, request)
    await field.fetch_related("category", "product", "options")
    return _map_field_to_response(field)


@router.get("/{field_id}", response_model=FieldResponse)
async def get_field(
    company_id: int,
    field_id: int,
    fields_service: FieldsServiceDep,
    viewer: CompanyViewerDep,
) -> FieldResponse:
    field = await fields_service.get_field(field_id, company_id)
    return _map_field_to_response(field)


@router.patch("/{field_id}", response_model=FieldResponse)
async def update_field(
    company_id: int,
    field_id: int,
    request: FieldPatch,
    fields_service: FieldsServiceDep,
    manager: CompanyManagerDep,
) -> FieldResponse:
    field = await fields_service.update_field(field_id, company_id, request)
    await field.fetch_related("category", "product", "options")
    return _map_field_to_response(field)


@router.delete("/{field_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_field(
    company_id: int,
    field_id: int,
    fields_service: FieldsServiceDep,
    manager: CompanyManagerDep,
):
    await fields_service.delete_field(field_id, company_id)


@router.get("/{field_id}/options", response_model=PaginatedResponse[FieldOptionResponse])
async def list_field_options(
    company_id: int,
    field_id: int,
    field_options_service: FieldOptionsServiceDep,
    fields_service: FieldsServiceDep,
    viewer: CompanyViewerDep,
    pagination: PaginationParams = Depends(),
) -> PaginatedResponse[FieldOptionResponse]:
    await fields_service.get_field(field_id, company_id)
    options, total = await field_options_service.list_options_paginated(field_id, pagination.limit, pagination.offset)
    items = [_serialize_field_option(opt) for opt in options]
    return PaginatedResponse[FieldOptionResponse](
        items=items,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post(
    "/{field_id}/options",
    status_code=status.HTTP_201_CREATED,
    response_model=FieldOptionResponse,
)
async def create_field_option(
    company_id: int,
    field_id: int,
    request: FieldOptionRequest,
    field_options_service: FieldOptionsServiceDep,
    fields_service: FieldsServiceDep,
    manager: CompanyManagerDep,
) -> FieldOptionResponse:
    await fields_service.get_field(field_id, company_id)
    option = await field_options_service.create_option(field_id, request.value, request.order)
    return _serialize_field_option(option)


@router.patch("/{field_id}/options/{option_id}", response_model=FieldOptionResponse)
async def update_field_option(
    company_id: int,
    field_id: int,
    option_id: int,
    request: FieldOptionPatch,
    field_options_service: FieldOptionsServiceDep,
    fields_service: FieldsServiceDep,
    manager: CompanyManagerDep,
) -> FieldOptionResponse:
    await fields_service.get_field(field_id, company_id)
    option = await field_options_service.update_option(option_id, field_id, request.value, request.order)
    return _serialize_field_option(option)


@router.delete("/{field_id}/options/{option_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_field_option(
    company_id: int,
    field_id: int,
    option_id: int,
    field_options_service: FieldOptionsServiceDep,
    fields_service: FieldsServiceDep,
    manager: CompanyManagerDep,
):
    await fields_service.get_field(field_id, company_id)
    await field_options_service.delete_option(option_id, field_id)
