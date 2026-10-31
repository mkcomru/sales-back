from tortoise.exceptions import DoesNotExist

from src.backend.modules.categories.models import Category
from src.backend.modules.core.base_repo import BaseRepository


class CategoriesRepository(BaseRepository[Category]):
    def __init__(self):
        super().__init__(Category)

    async def get_by_company_id(self, company_id: int) -> list[Category]:
        return await Category.filter(company_id=company_id).all()

    async def get_by_company_id_paginated(self, company_id: int, limit: int, offset: int) -> tuple[list[Category], int]:
        total = await Category.filter(company_id=company_id).count()
        items = await Category.filter(company_id=company_id).offset(offset).limit(limit).all()
        return items, total

    async def get_by_id_and_company(self, category_id: int, company_id: int) -> Category | None:
        return await Category.get_or_none(id=category_id, company_id=company_id)

    async def delete_by_id_and_company(self, category_id: int, company_id: int) -> bool:
        try:
            category = await Category.get(id=category_id, company_id=company_id)
            await category.delete()
            return True
        except DoesNotExist:
            return False
