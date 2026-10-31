import asyncio

import structlog

from src.backend.modules.chat.repository import CustomersRepository
from src.backend.modules.fields.exceptions import (
    FieldNotFoundError,
    FieldOptionNotFoundError,
    SystemFieldError,
)
from src.backend.modules.fields.models import AnswerType, Field, FieldLevel, FieldOption
from src.backend.modules.fields.repository import (
    FieldOptionsRepository,
    FieldsRepository,
)
from src.backend.modules.fields.schemas import FieldPatch, FieldRequest

log = structlog.get_logger(__name__)


class FieldsService:
    repository: FieldsRepository = FieldsRepository()
    customers_repo: CustomersRepository = CustomersRepository()

    async def _backfill_customers_fields(self, company_id: int, field_name: str) -> None:
        """Backfill new field for all existing customers (background task)."""
        try:
            total, updated = await self.customers_repo.backfill_fields_for_company(company_id)
            log.info(
                "forms.field_backfill_completed",
                company_id=company_id,
                field_name=field_name,
                total_customers=total,
                updated_customers=updated,
            )
        except Exception as e:
            log.error(
                "forms.field_backfill_failed",
                company_id=company_id,
                field_name=field_name,
                error=str(e),
                exc_info=True,
            )

    async def get_field(self, field_id: int, company_id: int) -> Field:
        field = await self.repository.get_by_id(field_id)

        if not field:
            raise FieldNotFoundError()

        await field.fetch_related("company")
        if field.company.id != company_id:
            raise FieldNotFoundError()

        return field

    async def list_fields(self, company_id: int) -> list[Field]:
        return await self.repository.list_by_company(company_id)

    async def list_fields_paginated(
        self, company_id: int, limit: int, offset: int, level: FieldLevel | None = None
    ) -> tuple[list[Field], int]:
        if level:
            fields = await self.repository.list_by_company_and_level(company_id, level)
            total = len(fields)
            paginated_fields = fields[offset : offset + limit]
            return paginated_fields, total
        return await self.repository.list_by_company_paginated(company_id, limit, offset)

    async def list_fields_by_category(self, category_id: int) -> list[Field]:
        return await self.repository.list_by_category(category_id)

    async def list_fields_by_category_paginated(
        self, category_id: int, limit: int, offset: int
    ) -> tuple[list[Field], int]:
        return await self.repository.list_by_category_paginated(category_id, limit, offset)

    async def list_fields_by_product(self, product_id: int) -> list[Field]:
        return await self.repository.list_by_product(product_id)

    async def list_fields_by_product_paginated(
        self, product_id: int, limit: int, offset: int
    ) -> tuple[list[Field], int]:
        return await self.repository.list_by_product_paginated(product_id, limit, offset)

    async def create_field(self, company_id: int, payload: FieldRequest) -> Field:
        if payload.is_system and payload.level != FieldLevel.CUSTOMER:
            raise ValueError("is_system=True is only allowed for level=CUSTOMER")

        field_data = payload.model_dump(exclude={"category_id", "product_id", "type"})
        answer_type = AnswerType(payload.type)

        field = await self.repository.create(
            company_id=company_id,
            answer_type=answer_type,
            category_id=payload.category_id,
            product_id=payload.product_id,
            **field_data,
        )

        # AICODE-NOTE: Auto-backfill new field to all existing customers in background (only for customer-level fields)
        if field.level == FieldLevel.CUSTOMER:
            asyncio.create_task(self._backfill_customers_fields(company_id, field.name))

        return field

    async def update_field(self, field_id: int, company_id: int, payload: FieldPatch) -> Field:
        field = await self.get_field(field_id, company_id)

        updates = payload.model_dump(exclude_unset=True, exclude_none=True)

        if "type" in updates:
            updates["answer_type"] = AnswerType(updates.pop("type"))

        # Validate is_system constraint
        new_level = updates.get("level", field.level)
        new_is_system = updates.get("is_system", field.is_system)
        if new_is_system and new_level != FieldLevel.CUSTOMER:
            raise ValueError("is_system=True is only allowed for level=CUSTOMER")

        # Warn if changing level (data in old storage will remain)
        if "level" in updates and updates["level"] != field.level:
            log.warning(
                "forms.field_level_changed",
                field_id=field_id,
                company_id=company_id,
                old_level=field.level.value,
                new_level=updates["level"].value,
                message="Changing field level - data in old storage will remain",
            )

        updated_field = await self.repository.update(field_id, updates)

        if not updated_field:
            raise FieldNotFoundError()

        return updated_field

    async def delete_field(self, field_id: int, company_id: int) -> bool:
        field = await self.get_field(field_id, company_id)
        if field.is_system:
            raise SystemFieldError("Cannot delete system field")
        deleted = await self.repository.delete(field_id)
        return deleted


class FieldOptionsService:
    repository: FieldOptionsRepository = FieldOptionsRepository()
    fields_repository: FieldsRepository = FieldsRepository()

    async def get_option(self, option_id: int, field_id: int) -> FieldOption:
        option = await self.repository.get_by_id(option_id)

        if not option:
            raise FieldOptionNotFoundError()

        await option.fetch_related("field")
        if option.field.id != field_id:
            raise FieldOptionNotFoundError()

        return option

    async def list_options(self, field_id: int) -> list[FieldOption]:
        field = await self.fields_repository.get_by_id(field_id)
        if not field:
            raise FieldNotFoundError()

        return await self.repository.list_by_field(field_id)

    async def list_options_paginated(self, field_id: int, limit: int, offset: int) -> tuple[list[FieldOption], int]:
        field = await self.fields_repository.get_by_id(field_id)
        if not field:
            raise FieldNotFoundError()

        return await self.repository.list_by_field_paginated(field_id, limit, offset)

    async def create_option(self, field_id: int, value: str, order: int = 0) -> FieldOption:
        field = await self.fields_repository.get_by_id(field_id)
        if not field:
            raise FieldNotFoundError()

        return await self.repository.create(field_id=field_id, value=value, order=order)

    async def update_option(
        self,
        option_id: int,
        field_id: int,
        value: str | None = None,
        order: int | None = None,
    ) -> FieldOption:
        option = await self.get_option(option_id, field_id)

        updates = {}
        if value is not None:
            updates["value"] = value
        if order is not None:
            updates["order"] = order

        if not updates:
            return option

        updated = await self.repository.update(option_id, updates)
        if not updated:
            raise FieldOptionNotFoundError()
        return updated

    async def delete_option(self, option_id: int, field_id: int) -> bool:
        await self.get_option(option_id, field_id)
        return await self.repository.delete(option_id)
