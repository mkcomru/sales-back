"""Pydantic schemas for forms module."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.backend.modules.chat.models import Customer
from src.backend.modules.fields.models import AnswerType, FieldLevel
from src.backend.modules.forms.models import FormSubmission, FormTemplate, FormTemplateField
from src.backend.modules.orders.models import Order


class FormTemplateFieldCreate(BaseModel):
    """Schema for creating a form template field."""

    field_id: int
    position: int = 0


class FormTemplateCreate(BaseModel):
    """Schema for creating a form template."""

    name: str
    contact_field_id: int
    template_fields: list[FormTemplateFieldCreate] = Field(default_factory=list)


class FormTemplateFieldResponse(BaseModel):
    """Schema for form template field response."""

    id: int
    field_id: int
    field_level: FieldLevel
    position: int

    @classmethod
    def from_model(cls, tf: FormTemplateField) -> "FormTemplateFieldResponse":
        """Convert FormTemplateField model to FormTemplateFieldResponse schema."""
        return cls(
            id=tf.id,
            field_id=tf.field.id,
            field_level=tf.field.level,
            position=tf.position,
        )


class FormTemplateResponse(BaseModel):
    """Schema for form template response."""

    id: int
    public_id: str
    name: str
    enabled: bool
    has_api_key: bool
    contact_field_id: int
    template_fields: list[FormTemplateFieldResponse]
    created_at: datetime
    updated_at: datetime

    @classmethod
    async def from_model(cls, form: FormTemplate) -> "FormTemplateResponse":
        """Convert FormTemplate model to FormTemplateResponse schema."""
        template_fields = list(form.template_fields)

        return cls(
            id=form.id,
            public_id=form.public_id,
            name=form.name,
            enabled=form.enabled,
            has_api_key=form.api_key_hash is not None,
            contact_field_id=form.contact_field.id,
            template_fields=[FormTemplateFieldResponse.from_model(tf) for tf in template_fields],
            created_at=form.created_at,
            updated_at=form.updated_at,
        )


class FormTemplatePatch(BaseModel):
    """Schema for updating a form template."""

    name: str | None = None
    enabled: bool | None = None
    contact_field_id: int | None = None
    template_fields: list[FormTemplateFieldCreate] | None = None


class RegenerateKeyResponse(BaseModel):
    """Schema for regenerate key response."""

    api_key: str


class CaptureRequest(BaseModel):
    """Schema for form capture request."""

    fields: dict[str, Any] = Field(description="Field values keyed by field name")
    utm: dict[str, str] | None = Field(default=None, description="UTM parameters")


class CaptureCustomerResponse(BaseModel):
    """Schema for capture customer response."""

    id: int
    user_id: str
    name: str | None
    customer_fields: dict[str, Any]

    @classmethod
    def from_model(cls, customer: Customer) -> "CaptureCustomerResponse":
        """Convert Customer model to CaptureCustomerResponse schema."""
        return cls(
            id=customer.id,
            user_id=customer.user_id,
            name=customer.name,
            customer_fields=customer.customer_fields or {},
        )


class CaptureOrderResponse(BaseModel):
    """Schema for capture order response."""

    id: int
    order_number: int
    order_fields: dict[str, Any]

    @classmethod
    def from_model(cls, order: Order) -> "CaptureOrderResponse":
        """Convert Order model to CaptureOrderResponse schema."""
        return cls(
            id=order.id,
            order_number=order.order_number,
            order_fields=order.order_fields or {},
        )


class CaptureResponse(BaseModel):
    """Schema for full capture response."""

    customer: CaptureCustomerResponse
    order: CaptureOrderResponse

    @classmethod
    def from_models(cls, customer: Customer, order: Order) -> "CaptureResponse":
        """Convert Customer and Order models to CaptureResponse schema."""
        return cls(
            customer=CaptureCustomerResponse.from_model(customer),
            order=CaptureOrderResponse.from_model(order),
        )


class CaptureMinimalResponse(BaseModel):
    """Schema for minimal capture response."""

    customer_id: int
    order_id: int
    order_number: int


class FormSubmissionResponse(BaseModel):
    """Schema for form submission response."""

    id: int
    customer_id: int | None
    order_id: int | None
    raw_fields: dict[str, Any]
    utm_data: dict[str, str] | None
    ip_address: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, submission: FormSubmission) -> "FormSubmissionResponse":
        """Convert FormSubmission model to FormSubmissionResponse schema."""
        return cls(
            id=submission.id,
            customer_id=submission.customer_id,
            order_id=submission.order_id,
            raw_fields=submission.raw_fields,
            utm_data=submission.utm_data,
            ip_address=submission.ip_address,
            created_at=submission.created_at,
        )


class PublicFieldOption(BaseModel):
    """Public schema for field option."""

    id: int
    value: str


class PublicField(BaseModel):
    """Public schema for a form field (for rendering)."""

    id: int
    name: str
    display_name: str | None
    question: str
    answer_type: AnswerType
    required: bool
    options: list[PublicFieldOption]
    is_contact_field: bool


class PublicFormResponse(BaseModel):
    """Public schema for form rendering (no sensitive data)."""

    id: int
    name: str
    company_name: str
    fields: list[PublicField]

    @classmethod
    async def from_model(cls, form: FormTemplate) -> "PublicFormResponse":
        """Convert FormTemplate to PublicFormResponse for public rendering."""
        await form.fetch_related("company", "contact_field", "template_fields__field__options")

        all_fields: list[PublicField] = []

        contact_field = form.contact_field
        await contact_field.fetch_related("options")
        all_fields.append(
            PublicField(
                id=contact_field.id,
                name=contact_field.name,
                display_name=contact_field.display_name,
                question=contact_field.question,
                answer_type=contact_field.answer_type,
                required=True,
                options=[PublicFieldOption(id=o.id, value=o.value) for o in contact_field.options],
                is_contact_field=True,
            )
        )

        template_fields = sorted(form.template_fields, key=lambda tf: tf.position)
        for tf in template_fields:
            field = tf.field
            all_fields.append(
                PublicField(
                    id=field.id,
                    name=field.name,
                    display_name=field.display_name,
                    question=field.question,
                    answer_type=field.answer_type,
                    required=field.required,
                    options=[PublicFieldOption(id=o.id, value=o.value) for o in field.options],
                    is_contact_field=False,
                )
            )

        return cls(
            id=form.id,
            name=form.name,
            company_name=form.company.name,
            fields=all_fields,
        )
