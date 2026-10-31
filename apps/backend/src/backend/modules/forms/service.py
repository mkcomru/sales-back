"""Service layer for forms module."""

import asyncio
from typing import Any

import structlog
from pydantic import BaseModel

from src.backend.modules.chat.models import Customer
from src.backend.modules.chat.service import ChatService
from src.backend.modules.fields.models import Field, FieldLevel
from src.backend.modules.forms.exceptions import FormNotFoundError, FormValidationError
from src.backend.modules.forms.models import FormSubmission, FormTemplate, FormTemplateField
from src.backend.modules.forms.repository import FormsRepository, FormSubmissionsRepository
from src.backend.modules.forms.schemas import (
    FormTemplateCreate,
    FormTemplatePatch,
)
from src.backend.modules.forms.utils import generate_form_api_key
from src.backend.modules.orders.models import Order
from src.backend.modules.orders.service import OrderService

log = structlog.get_logger(__name__)


class CaptureResult(BaseModel):
    """Result of form capture operation."""

    customer: Customer
    order: Order

    class Config:
        arbitrary_types_allowed = True


class FormsService:
    """Service for managing form templates and captures."""

    def __init__(self):
        self.repo = FormsRepository()
        self.submissions_repo = FormSubmissionsRepository()
        self.order_service = OrderService()
        self.chat_service = ChatService(order_service=self.order_service)

    async def get_form(self, form_id: int, company_id: int) -> FormTemplate:
        """Get form template by ID and company ID."""
        form = await self.repo.get_by_id_and_company(form_id, company_id)
        if not form:
            raise FormNotFoundError()
        return form

    async def get_public_form(self, public_id: str) -> FormTemplate:
        """Get enabled form template by public_id (for public access)."""
        form = await self.repo.get_by_public_id(public_id)
        if not form or not form.enabled:
            raise FormNotFoundError()
        return form

    async def list_forms(self, company_id: int) -> list[FormTemplate]:
        """List all form templates for a company."""
        return await self.repo.list_by_company(company_id)

    async def list_forms_paginated(self, company_id: int, limit: int, offset: int) -> tuple[list[FormTemplate], int]:
        """List form templates with pagination."""
        return await self.repo.list_by_company_paginated(company_id, limit, offset)

    async def create_form(self, company_id: int, data: FormTemplateCreate) -> FormTemplate:
        """Create a new form template."""
        contact_field = await Field.get_or_none(id=data.contact_field_id, company_id=company_id)
        if not contact_field:
            raise FormValidationError("Contact field not found or doesn't belong to company")

        field_ids = {tf.field_id for tf in data.template_fields}
        field_ids.add(data.contact_field_id)

        fields = await Field.filter(id__in=field_ids, company_id=company_id).all()
        if len(fields) != len(field_ids):
            raise FormValidationError("Some fields not found or don't belong to company")

        form = await FormTemplate.create(
            company_id=company_id,
            name=data.name,
            contact_field_id=data.contact_field_id,
        )

        if data.template_fields:
            await FormTemplateField.bulk_create(
                [
                    FormTemplateField(form_template_id=form.id, field_id=tf_data.field_id, position=tf_data.position)
                    for tf_data in data.template_fields
                ]
            )

        return await self.get_form(form.id, company_id)

    async def update_form(self, form_id: int, company_id: int, data: FormTemplatePatch) -> FormTemplate:
        """Update a form template."""
        await self.get_form(form_id, company_id)

        updates = {}
        if data.name is not None:
            updates["name"] = data.name
        if data.enabled is not None:
            updates["enabled"] = data.enabled
        if data.contact_field_id is not None:
            contact_field = await Field.get_or_none(id=data.contact_field_id, company_id=company_id)
            if not contact_field:
                raise FormValidationError("Contact field not found or doesn't belong to company")
            updates["contact_field_id"] = data.contact_field_id

        if updates:
            await FormTemplate.filter(id=form_id).update(**updates)

        if data.template_fields is not None:
            await FormTemplateField.filter(form_template_id=form_id).delete()
            for tf_data in data.template_fields:
                field = await Field.get_or_none(id=tf_data.field_id, company_id=company_id)
                if not field:
                    raise FormValidationError(f"Field {tf_data.field_id} not found or doesn't belong to company")
                await FormTemplateField.create(
                    form_template_id=form_id, field_id=tf_data.field_id, position=tf_data.position
                )

        return await self.get_form(form_id, company_id)

    async def delete_form(self, form_id: int, company_id: int) -> None:
        """Delete a form template."""
        form = await self.get_form(form_id, company_id)
        await form.delete()

    async def regenerate_api_key(self, form_id: int, company_id: int) -> str:
        """Regenerate API key. Returns raw key (shown once)."""
        await self.get_form(form_id, company_id)
        raw_key, key_hash = generate_form_api_key()
        await self.repo.update_key_hash(form_id, key_hash)
        return raw_key

    async def process_capture(
        self,
        *,
        form: FormTemplate,
        fields_data: dict[str, Any],
        utm_data: dict[str, str] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> CaptureResult:
        """Process form capture - create Customer and Order.

        Args:
            form: FormTemplate instance
            fields_data: Field values keyed by field name
            utm_data: Optional UTM parameters
            ip_address: Optional IP address
            user_agent: Optional user agent

        Returns:
            CaptureResult with customer and order
        """
        await form.fetch_related("company", "contact_field", "template_fields__field")

        template_fields = await form.template_fields.all()
        await asyncio.gather(*[tf.fetch_related("field") for tf in template_fields])

        field_map = {tf.field.name: tf.field for tf in template_fields}
        contact_field_name = form.contact_field.name
        field_map[contact_field_name] = form.contact_field

        required_fields = {f.name for f in field_map.values() if f.required}
        required_fields.add(contact_field_name)
        provided_fields = set(fields_data.keys())

        missing_required = required_fields - provided_fields
        if missing_required:
            raise FormValidationError(f"Missing required fields: {', '.join(sorted(missing_required))}")

        contact_value = fields_data.get(contact_field_name)
        if not contact_value:
            raise FormValidationError(f"Contact field '{contact_field_name}' is required")

        user_id = str(contact_value)

        customer, _ = await self.chat_service.get_or_create_customer(user_id=user_id, company_id=form.company.id)

        customer_fields_updates = {}
        order_fields_updates = {}

        for field_name, value in fields_data.items():
            if field_name == contact_field_name:
                continue

            field = field_map.get(field_name)
            if not field:
                continue

            if field.level == FieldLevel.CUSTOMER:
                customer_fields_updates[field.name] = value
            elif field.level == FieldLevel.ORDER:
                order_fields_updates[field.name] = value

        if customer_fields_updates:
            await self.chat_service.update_customer_fields(
                user_id=user_id, company_id=form.company.id, updates=customer_fields_updates
            )
            await customer.refresh_from_db()

        order = await self.order_service.create_order(
            company_id=form.company.id,
            customer_id=customer.id,
            initial_channel="form",
        )

        if order_fields_updates:
            await self.order_service.update_order_fields(order.id, order_fields_updates)
            await order.refresh_from_db()

        if utm_data:
            order.utm_data = utm_data
            await order.save(update_fields=["utm_data"])
            await order.refresh_from_db()

        submission = await FormSubmission.create(
            form_template_id=form.id,
            customer_id=customer.id,
            order_id=order.id,
            raw_fields=fields_data,
            utm_data=utm_data,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        log.info(
            "forms.capture_processed",
            form_id=form.id,
            customer_id=customer.id,
            order_id=order.id,
            submission_id=submission.id,
        )

        # AICODE-TODO: Implement outbound message sending after Contact Registry
        # This is where we'll initiate first message to the customer

        return CaptureResult(customer=customer, order=order)

    async def list_submissions_paginated(
        self, form_id: int, company_id: int, limit: int, offset: int
    ) -> tuple[list[FormSubmission], int]:
        """List form submissions with pagination."""
        await self.get_form(form_id, company_id)
        return await self.submissions_repo.list_by_form_paginated(form_id, limit, offset)
