from src.backend.modules.core.base_repo import BaseRepository
from src.backend.modules.fields.models import AnswerType, Field, FieldLevel, FieldOption


class FieldsRepository(BaseRepository[Field]):
    def __init__(self):
        super().__init__(Field)

    async def get_by_id(self, field_id: int) -> Field | None:
        return await Field.get_or_none(id=field_id).prefetch_related("company", "category", "product", "options")

    async def list_by_company(self, company_id: int) -> list[Field]:
        return await Field.filter(company_id=company_id).prefetch_related("category", "product", "options").all()

    async def list_by_company_paginated(self, company_id: int, limit: int, offset: int) -> tuple[list[Field], int]:
        total = await Field.filter(company_id=company_id).count()
        items = (
            await Field.filter(company_id=company_id)
            .prefetch_related("category", "product", "options")
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total

    async def list_by_category(self, category_id: int) -> list[Field]:
        return await Field.filter(category_id=category_id).prefetch_related("company", "product", "options").all()

    async def list_by_category_paginated(self, category_id: int, limit: int, offset: int) -> tuple[list[Field], int]:
        total = await Field.filter(category_id=category_id).count()
        items = (
            await Field.filter(category_id=category_id)
            .prefetch_related("company", "product", "options")
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total

    async def list_by_product(self, product_id: int) -> list[Field]:
        return await Field.filter(product_id=product_id).prefetch_related("company", "category", "options").all()

    async def list_by_product_paginated(self, product_id: int, limit: int, offset: int) -> tuple[list[Field], int]:
        total = await Field.filter(product_id=product_id).count()
        items = (
            await Field.filter(product_id=product_id)
            .prefetch_related("company", "category", "options")
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total

    async def create(
        self,
        company_id: int,
        name: str,
        question: str,
        answer_type: AnswerType,
        required: bool = False,
        display_name: str | None = None,
        category_id: int | None = None,
        product_id: int | None = None,
        level: FieldLevel = FieldLevel.CUSTOMER,
        is_system: bool = False,
    ) -> Field:
        return await Field.create(
            company_id=company_id,
            name=name,
            question=question,
            answer_type=answer_type,
            required=required,
            display_name=display_name,
            category_id=category_id,
            product_id=product_id,
            level=level,
            is_system=is_system,
        )

    async def update(self, field_id: int, updates: dict) -> Field | None:
        return await self._update(id=field_id, updates=updates)

    async def delete(self, field_id: int) -> bool:
        return await self._delete(id=field_id)

    async def list_by_company_and_level(self, company_id: int, level: FieldLevel) -> list[Field]:
        """List fields filtered by level."""
        return (
            await Field.filter(company_id=company_id, level=level)
            .prefetch_related("category", "product", "options")
            .all()
        )

    async def list_customer_fields(self, company_id: int) -> list[Field]:
        """List customer-level fields."""
        return await self.list_by_company_and_level(company_id, FieldLevel.CUSTOMER)

    async def list_order_fields(self, company_id: int) -> list[Field]:
        """List order-level fields."""
        return await self.list_by_company_and_level(company_id, FieldLevel.ORDER)

    async def get_system_fields(self, company_id: int) -> list[Field]:
        """Get system customer fields."""
        return await Field.filter(company_id=company_id, level=FieldLevel.CUSTOMER, is_system=True).all()


class FieldOptionsRepository(BaseRepository[FieldOption]):
    def __init__(self):
        super().__init__(FieldOption)

    async def get_by_id(self, option_id: int) -> FieldOption | None:
        return await FieldOption.get_or_none(id=option_id).prefetch_related("field")

    async def list_by_field(self, field_id: int) -> list[FieldOption]:
        return await FieldOption.filter(field_id=field_id).order_by("order").all()

    async def list_by_field_paginated(self, field_id: int, limit: int, offset: int) -> tuple[list[FieldOption], int]:
        total = await FieldOption.filter(field_id=field_id).count()
        items = await FieldOption.filter(field_id=field_id).order_by("order").offset(offset).limit(limit).all()
        return items, total

    async def create(self, field_id: int, value: str, order: int = 0) -> FieldOption:
        return await FieldOption.create(field_id=field_id, value=value, order=order)

    async def update(self, option_id: int, updates: dict) -> FieldOption | None:
        return await self._update(id=option_id, updates=updates)

    async def delete(self, option_id: int) -> bool:
        return await self._delete(id=option_id)
