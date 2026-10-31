from fastapi import APIRouter, Depends, HTTPException, status

from common.models.pagination import PaginatedResponse, PaginationParams

from src.backend.modules.auth.dependencies import (
    CompanyViewerDep,
    CompanyViewerQueryDep,
    CurrentUserDep,
    require_company_role,
)
from src.backend.modules.categories.models import Category
from src.backend.modules.companies.dependencies import CompaniesServiceDep
from src.backend.modules.companies.schemas import CompanyProductsResponse
from src.backend.modules.fields.dependencies import FieldsServiceDep
from src.backend.modules.fields.routers import _map_field_to_response
from src.backend.modules.fields.schemas import FieldResponse
from src.backend.modules.products.dependencies import (
    CompanyAdminForNewProductDep,
    ProductsServiceDep,
)
from src.backend.modules.products.schemas import ProductPatch, ProductRequest, ProductResponse
from src.backend.modules.users.models import UserRole

router = APIRouter(prefix="/products", tags=["products:internal"])
public_router = APIRouter(prefix="/companies", tags=["products:public"])


def _product_company_id(product) -> int:
    if not product.category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product must belong to a category",
        )
    return product.category.company_id


@router.post("/")
async def create_product(
    payload: ProductRequest,
    products_service: ProductsServiceDep,
    _admin: CompanyAdminForNewProductDep,
) -> ProductResponse:
    product = await products_service.create_product(payload=payload)
    await product.fetch_related("category")
    return ProductResponse.from_model(product)


@router.get("/")
async def list_products(
    company_user: CompanyViewerQueryDep,
    products_service: ProductsServiceDep,
) -> list[ProductResponse]:
    products = await products_service.list_products_for_company(company_user.company_id)
    return [ProductResponse.from_model(p) for p in products]


@router.get("/{product_id}")
async def get_product(
    product_id: int,
    current_user: CurrentUserDep,
    products_service: ProductsServiceDep,
) -> ProductResponse:
    product = await products_service.get_product_by_id(product_id)
    company_id = _product_company_id(product)
    await require_company_role(
        company_id=company_id,
        current_user=current_user,
        required_role=UserRole.VIEWER,
    )
    return ProductResponse.from_model(product)


@router.delete("/{product_id}")
async def delete_product(
    product_id: int,
    current_user: CurrentUserDep,
    products_service: ProductsServiceDep,
) -> dict:
    product = await products_service.get_product_by_id(product_id)
    company_id = _product_company_id(product)
    await require_company_role(
        company_id=company_id,
        current_user=current_user,
        required_role=UserRole.ADMIN,
    )
    await products_service.delete_product(product_id)
    return {"message": "Product deleted successfully"}


@router.patch("/{product_id}")
async def update_product(
    product_id: int,
    payload: ProductPatch,
    current_user: CurrentUserDep,
    products_service: ProductsServiceDep,
) -> ProductResponse:
    existing = await products_service.get_product_by_id(product_id)
    company_id = _product_company_id(existing)
    await require_company_role(
        company_id=company_id,
        current_user=current_user,
        required_role=UserRole.MANAGER,
    )
    if payload.category_id is not None:
        new_cat = await Category.get_or_none(id=payload.category_id)
        if not new_cat or new_cat.company_id != company_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    product = await products_service.update_product(product_id, payload)
    await product.fetch_related("category")
    return ProductResponse.from_model(product)


@public_router.get("/{company_id}/products")
async def get_company_products(
    company_id: int,
    companies_service: CompaniesServiceDep,
    viewer: CompanyViewerDep,
) -> CompanyProductsResponse:
    return await companies_service.get_company_products(company_id)


@public_router.get(
    "/{company_id}/products/{product_id}/fields",
    response_model=PaginatedResponse[FieldResponse],
)
async def list_product_fields(
    company_id: int,
    product_id: int,
    products_service: ProductsServiceDep,
    fields_service: FieldsServiceDep,
    viewer: CompanyViewerDep,
    pagination: PaginationParams = Depends(),
) -> PaginatedResponse[FieldResponse]:
    product = await products_service.get_product_by_id(product_id)

    if not product.category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product must belong to a category",
        )

    await product.category.fetch_related("company")
    if product.category.company.id != company_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found in this company",
        )

    fields, total = await fields_service.list_fields_by_product_paginated(
        product_id, pagination.limit, pagination.offset
    )
    return PaginatedResponse[FieldResponse](
        items=[_map_field_to_response(f) for f in fields],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )
