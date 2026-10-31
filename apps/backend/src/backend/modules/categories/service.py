from src.backend.modules.categories.exceptions import CategoryNotFoundError
from src.backend.modules.categories.models import Category
from src.backend.modules.categories.repository import CategoriesRepository


class CategoriesService:
    repository: CategoriesRepository = CategoriesRepository()

    async def get_by_company(self, company_id: int) -> list[Category]:
        return await self.repository.get_by_company_id(company_id)

    async def get_by_company_paginated(self, company_id: int, limit: int, offset: int) -> tuple[list[Category], int]:
        return await self.repository.get_by_company_id_paginated(company_id, limit, offset)

    async def get_by_id(self, category_id: int, company_id: int) -> Category:
        category = await self.repository.get_by_id_and_company(category_id, company_id)

        if not category:
            raise CategoryNotFoundError()

        return category

    async def create(
        self,
        company_id: int,
        name: str,
        description: str,
        rules: str,
        examples: str,
        workflow: str,
        enabled_tools: list[str] | None = None,
    ) -> Category:
        return await Category.create(
            company_id=company_id,
            name=name,
            description=description,
            rules=rules,
            examples=examples,
            workflow=workflow,
            enabled_tools=enabled_tools or [],
        )

    async def update(
        self,
        category_id: int,
        company_id: int,
        **updates,
    ) -> Category:
        category = await self.get_by_id(category_id, company_id)

        for key, value in updates.items():
            if value is not None and hasattr(category, key):
                setattr(category, key, value)

        await category.save()
        return category

    async def delete(self, category_id: int, company_id: int) -> bool:
        deleted = await self.repository.delete_by_id_and_company(category_id, company_id)

        if not deleted:
            raise CategoryNotFoundError()

        return True
