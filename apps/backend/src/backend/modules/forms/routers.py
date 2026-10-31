"""Routers for forms module."""

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse

from common.models.pagination import PaginatedResponse, PaginationParams

from src.backend.modules.auth.dependencies import CompanyManagerDep, CompanyViewerDep
from src.backend.modules.forms.dependencies import FormByApiKeyDep, FormsServiceDep
from src.backend.modules.forms.rate_limit import limiter
from src.backend.modules.forms.schemas import (
    CaptureMinimalResponse,
    CaptureRequest,
    CaptureResponse,
    FormSubmissionResponse,
    FormTemplateCreate,
    FormTemplatePatch,
    FormTemplateResponse,
    PublicFormResponse,
    RegenerateKeyResponse,
)

router = APIRouter(prefix="/companies/{company_id}/forms", tags=["forms"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=FormTemplateResponse)
async def create_form(
    company_id: int,
    request: FormTemplateCreate,
    forms_service: FormsServiceDep,
    manager: CompanyManagerDep,
) -> FormTemplateResponse:
    """Create a new form template."""
    form = await forms_service.create_form(company_id, request)
    return await FormTemplateResponse.from_model(form)


@router.get("", response_model=PaginatedResponse[FormTemplateResponse])
async def list_forms(
    company_id: int,
    forms_service: FormsServiceDep,
    viewer: CompanyViewerDep,
    pagination: PaginationParams = Depends(),
) -> PaginatedResponse[FormTemplateResponse]:
    """List form templates for a company."""
    forms, total = await forms_service.list_forms_paginated(company_id, pagination.limit, pagination.offset)
    items = [await FormTemplateResponse.from_model(form) for form in forms]
    return PaginatedResponse[FormTemplateResponse](
        items=items,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/{form_id}", response_model=FormTemplateResponse)
async def get_form(
    company_id: int,
    form_id: int,
    forms_service: FormsServiceDep,
    viewer: CompanyViewerDep,
) -> FormTemplateResponse:
    """Get a form template by ID."""
    form = await forms_service.get_form(form_id, company_id)
    return await FormTemplateResponse.from_model(form)


@router.patch("/{form_id}", response_model=FormTemplateResponse)
async def update_form(
    company_id: int,
    form_id: int,
    request: FormTemplatePatch,
    forms_service: FormsServiceDep,
    manager: CompanyManagerDep,
) -> FormTemplateResponse:
    """Update a form template."""
    form = await forms_service.update_form(form_id, company_id, request)
    return await FormTemplateResponse.from_model(form)


@router.delete("/{form_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_form(
    company_id: int,
    form_id: int,
    forms_service: FormsServiceDep,
    manager: CompanyManagerDep,
):
    """Delete a form template."""
    await forms_service.delete_form(form_id, company_id)


@router.post("/{form_id}/regenerate-key", response_model=RegenerateKeyResponse)
async def regenerate_key(
    company_id: int,
    form_id: int,
    forms_service: FormsServiceDep,
    manager: CompanyManagerDep,
) -> RegenerateKeyResponse:
    """Regenerate API key for a form template."""
    api_key = await forms_service.regenerate_api_key(form_id, company_id)
    return RegenerateKeyResponse(api_key=api_key)


@router.get("/{form_id}/submissions", response_model=PaginatedResponse[FormSubmissionResponse])
async def list_submissions(
    company_id: int,
    form_id: int,
    forms_service: FormsServiceDep,
    viewer: CompanyViewerDep,
    pagination: PaginationParams = Depends(),
) -> PaginatedResponse[FormSubmissionResponse]:
    """List form submissions for a form template."""
    submissions, total = await forms_service.list_submissions_paginated(
        form_id, company_id, pagination.limit, pagination.offset
    )
    items = [FormSubmissionResponse.from_model(s) for s in submissions]
    return PaginatedResponse[FormSubmissionResponse](
        items=items,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.post("/{form_id}/submit")
async def submit_form_internal(
    company_id: int,
    form_id: int,
    request: CaptureRequest,
    forms_service: FormsServiceDep,
    viewer: CompanyViewerDep,
    mode: str = Query(default="minimal", description="Response mode: full or minimal"),
) -> CaptureResponse | CaptureMinimalResponse:
    """Internal endpoint for form submission (requires auth)."""
    form = await forms_service.get_form(form_id, company_id)
    result = await forms_service.process_capture(
        form=form,
        fields_data=request.fields,
        utm_data=request.utm,
    )

    if mode == "minimal":
        return CaptureMinimalResponse(
            customer_id=result.customer.id,
            order_id=result.order.id,
            order_number=result.order.order_number,
        )

    return CaptureResponse.from_models(result.customer, result.order)


public_router = APIRouter(prefix="/forms", tags=["forms-public"])


# ============================================================================
# Public form endpoints (no auth) - accessed by public_id (random string)
# ============================================================================


@public_router.get("/{public_id}", response_model=PublicFormResponse)
async def get_public_form(
    public_id: str,
    forms_service: FormsServiceDep,
) -> PublicFormResponse:
    """Get public form schema for rendering. No auth required."""
    form = await forms_service.get_public_form(public_id)
    return await PublicFormResponse.from_model(form)


@public_router.post("/{public_id}/submit")
@limiter.limit("60/minute")
async def submit_public_form(
    public_id: str,
    request: Request,
    capture_request: CaptureRequest,
    forms_service: FormsServiceDep,
) -> CaptureMinimalResponse:
    """Public form submission. No auth required."""
    form = await forms_service.get_public_form(public_id)
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    result = await forms_service.process_capture(
        form=form,
        fields_data=capture_request.fields,
        utm_data=capture_request.utm,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return CaptureMinimalResponse(
        customer_id=result.customer.id,
        order_id=result.order.id,
        order_number=result.order.order_number,
    )


# ============================================================================
# API-key based endpoints (for developers integrating via code)
# ============================================================================


@public_router.get("/key/schema", response_model=PublicFormResponse)
async def get_form_by_api_key(
    form: FormByApiKeyDep,
) -> PublicFormResponse:
    """Get form schema via API key (X-Form-Key header)."""
    return await PublicFormResponse.from_model(form)


@public_router.post("/key/capture")
@limiter.limit("60/minute")
async def capture_form_via_api_key(
    request: Request,
    capture_request: CaptureRequest,
    form: FormByApiKeyDep,
    forms_service: FormsServiceDep,
    mode: str = Query(default="minimal", description="Response mode: full or minimal"),
) -> JSONResponse:
    """Submit form via API key (X-Form-Key header)."""
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    result = await forms_service.process_capture(
        form=form,
        fields_data=capture_request.fields,
        utm_data=capture_request.utm,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    response_data: CaptureResponse | CaptureMinimalResponse
    if mode == "minimal":
        response_data = CaptureMinimalResponse(
            customer_id=result.customer.id,
            order_id=result.order.id,
            order_number=result.order.order_number,
        )
    else:
        response_data = CaptureResponse.from_models(result.customer, result.order)

    response = JSONResponse(content=response_data.model_dump())
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Form-Key"
    return response


@public_router.options("/key/capture")
async def key_capture_options():
    """CORS preflight for key capture endpoint."""
    response = Response()
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Form-Key"
    return response


@public_router.options("/key/schema")
async def key_schema_options():
    """CORS preflight for key schema endpoint."""
    response = Response()
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Form-Key"
    return response
