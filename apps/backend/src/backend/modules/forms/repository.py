"""Repository for forms module."""

from src.backend.modules.core.base_repo import BaseRepository
from src.backend.modules.forms.models import FormSubmission, FormTemplate


class FormsRepository(BaseRepository[FormTemplate]):
    """Repository for FormTemplate operations."""

    def __init__(self):
        super().__init__(FormTemplate)

    async def get_by_id_and_company(self, form_id: int, company_id: int) -> FormTemplate | None:
        """Get form template by ID and company ID."""
        return await FormTemplate.get_or_none(id=form_id, company_id=company_id).prefetch_related(
            "company", "contact_field", "template_fields__field"
        )

    async def get_by_public_id(self, public_id: str) -> FormTemplate | None:
        """Get form template by public_id (for public access)."""
        return await FormTemplate.get_or_none(public_id=public_id).prefetch_related(
            "company", "contact_field", "template_fields__field"
        )

    async def get_by_key_hash(self, key_hash: str) -> FormTemplate | None:
        """Get form template by API key hash."""
        return await FormTemplate.get_or_none(api_key_hash=key_hash).prefetch_related(
            "company", "contact_field", "template_fields__field"
        )

    async def list_by_company(self, company_id: int) -> list[FormTemplate]:
        """List all form templates for a company."""
        return (
            await FormTemplate.filter(company_id=company_id)
            .prefetch_related("contact_field", "template_fields__field")
            .order_by("-created_at")
            .all()
        )

    async def list_by_company_paginated(
        self, company_id: int, limit: int, offset: int
    ) -> tuple[list[FormTemplate], int]:
        """List form templates with pagination."""
        total = await FormTemplate.filter(company_id=company_id).count()
        items = (
            await FormTemplate.filter(company_id=company_id)
            .prefetch_related("contact_field", "template_fields__field")
            .order_by("-created_at")
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total

    async def update_key_hash(self, form_id: int, key_hash: str) -> None:
        """Update API key hash for a form template."""
        await FormTemplate.filter(id=form_id).update(api_key_hash=key_hash)


class FormSubmissionsRepository(BaseRepository[FormSubmission]):
    """Repository for FormSubmission operations."""

    def __init__(self):
        super().__init__(FormSubmission)

    async def list_by_form_paginated(
        self, form_template_id: int, limit: int, offset: int
    ) -> tuple[list[FormSubmission], int]:
        """List submissions for a form template with pagination."""
        total = await FormSubmission.filter(form_template_id=form_template_id).count()
        items = (
            await FormSubmission.filter(form_template_id=form_template_id)
            .prefetch_related("customer", "order")
            .order_by("-created_at")
            .offset(offset)
            .limit(limit)
            .all()
        )
        return items, total
