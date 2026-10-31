"""FastAPI dependencies for products API."""

from typing import Annotated

from fastapi import Depends, HTTPException, status

from src.backend.modules.auth.dependencies import CurrentUserDep, require_company_role
from src.backend.modules.categories.models import Category
from src.backend.modules.products.schemas import ProductRequest
from src.backend.modules.products.service import ProductsService
from src.backend.modules.users.models import CompanyUser, UserRole


def get_products_service() -> ProductsService:
    return ProductsService()


ProductsServiceDep = Annotated[ProductsService, Depends(get_products_service)]


async def require_company_admin_for_new_product(
    payload: ProductRequest,
    current_user: CurrentUserDep,
) -> CompanyUser:
    category = await Category.get_or_none(id=payload.category_id)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return await require_company_role(
        company_id=category.company_id,
        current_user=current_user,
        required_role=UserRole.ADMIN,
    )


CompanyAdminForNewProductDep = Annotated[CompanyUser, Depends(require_company_admin_for_new_product)]
