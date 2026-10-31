"""Service tests for fields."""

import asyncio

import pytest

from src.backend.modules.categories.models import Category
from src.backend.modules.fields.exceptions import FieldNotFoundError
from src.backend.modules.fields.models import AnswerType, Field, FieldLevel
from src.backend.modules.fields.schemas import FieldPatch, FieldRequest
from src.backend.modules.fields.service import FieldsService


async def test_service_list_fields_empty(company_factory):
    company = await company_factory()
    service = FieldsService()
    fields = await service.list_fields(company.id)
    assert fields == []


async def test_service_list_fields_with_data(company_factory):
    company = await company_factory()
    await Field.create(
        company=company,
        name="Field 1",
        question="Q1?",
        answer_type=AnswerType.STRING,
    )
    await Field.create(
        company=company,
        name="Field 2",
        question="Q2?",
        answer_type=AnswerType.NUMBER,
    )

    service = FieldsService()
    fields = await service.list_fields(company.id)
    assert len(fields) == 2


async def test_service_get_field_success(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Test Field",
        question="Question?",
        answer_type=AnswerType.STRING,
    )

    service = FieldsService()
    found = await service.get_field(field.id, company.id)
    assert found.id == field.id
    assert found.name == "Test Field"


async def test_service_get_field_not_found(company_factory):
    company = await company_factory()
    service = FieldsService()
    with pytest.raises(FieldNotFoundError):
        await service.get_field(99999, company.id)


async def test_service_get_field_wrong_company(company_factory):
    company1 = await company_factory(name="Company 1")
    company2 = await company_factory(name="Company 2")

    field = await Field.create(
        company=company1,
        name="Test",
        question="Q?",
        answer_type=AnswerType.STRING,
    )

    service = FieldsService()
    with pytest.raises(FieldNotFoundError):
        await service.get_field(field.id, company2.id)


async def test_service_create_field_success(company_factory):
    company = await company_factory()
    service = FieldsService()

    payload = FieldRequest(
        name="New Field",
        question="Question?",
        type="string",
        required=True,
    )
    field = await service.create_field(company.id, payload)

    assert field.name == "New Field"
    assert field.company_id == company.id
    assert field.answer_type == AnswerType.STRING
    assert field.required is True


async def test_service_create_field_with_category(company_factory, category_payload):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Category",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )

    service = FieldsService()
    payload = FieldRequest(
        name="Field",
        question="Q?",
        type="string",
        category_id=category.id,
    )
    field = await service.create_field(company.id, payload)
    assert field.category_id == category.id


async def test_service_update_field_success(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Original",
        question="Original?",
        answer_type=AnswerType.STRING,
    )

    service = FieldsService()
    payload = FieldPatch(name="Updated", question="Updated?")
    updated = await service.update_field(field.id, company.id, payload)

    assert updated.name == "Updated"
    assert updated.question == "Updated?"


async def test_service_update_field_change_type(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Field",
        question="Q?",
        answer_type=AnswerType.STRING,
    )

    service = FieldsService()
    payload = FieldPatch(type="number")
    updated = await service.update_field(field.id, company.id, payload)
    assert updated.answer_type == AnswerType.NUMBER


async def test_service_update_field_not_found(company_factory):
    company = await company_factory()
    service = FieldsService()
    payload = FieldPatch(name="Updated")
    with pytest.raises(FieldNotFoundError):
        await service.update_field(99999, company.id, payload)


async def test_service_delete_field_success(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Delete Me",
        question="Q?",
        answer_type=AnswerType.STRING,
    )

    service = FieldsService()
    deleted = await service.delete_field(field.id, company.id)
    assert deleted is True

    with pytest.raises(FieldNotFoundError):
        await service.get_field(field.id, company.id)


async def test_service_delete_field_not_found(company_factory):
    company = await company_factory()
    service = FieldsService()
    with pytest.raises(FieldNotFoundError):
        await service.delete_field(99999, company.id)


async def test_service_list_fields_by_category(company_factory, category_payload):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Category",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )

    await Field.create(
        company=company,
        name="Field 1",
        question="Q1?",
        answer_type=AnswerType.STRING,
        category=category,
    )
    await Field.create(
        company=company,
        name="Field 2",
        question="Q2?",
        answer_type=AnswerType.STRING,
        category=category,
    )

    service = FieldsService()
    fields = await service.list_fields_by_category(category.id)
    assert len(fields) == 2


async def test_service_create_field_triggers_backfill(company_factory):
    """Test that creating a field triggers backfill for existing customers."""
    from src.backend.modules.chat.repository import CustomersRepository

    company = await company_factory()
    customers_repo = CustomersRepository()

    # Create existing customers
    customer1, _ = await customers_repo.get_or_create(
        user_id="test_backfill_1",
        company_id=company.id,
    )
    customer2, _ = await customers_repo.get_or_create(
        user_id="test_backfill_2",
        company_id=company.id,
    )

    # Initially customers have system fields in customer_fields
    # Note: backfill_fields_for_company works with customer_fields

    # Create a new customer-level field
    service = FieldsService()
    payload = FieldRequest(
        name="new_field",
        question="New question?",
        type="string",
        required=False,
        level=FieldLevel.CUSTOMER,
    )

    field = await service.create_field(company.id, payload)

    assert field.name == "new_field"

    # Wait a bit for background task to complete
    await asyncio.sleep(0.1)

    # Refresh customers from DB
    await customer1.refresh_from_db()
    await customer2.refresh_from_db()

    # Check that new field was added to both customers in customer_fields
    assert "new_field" in customer1.customer_fields
    assert customer1.customer_fields["new_field"] is None
    assert "new_field" in customer2.customer_fields
    assert customer2.customer_fields["new_field"] is None


async def test_service_create_field_backfill_preserves_existing_values(company_factory):
    """Test that backfill preserves existing quiz_answers values."""
    from src.backend.modules.chat.repository import CustomersRepository

    company = await company_factory()
    customers_repo = CustomersRepository()

    # Create customer with existing field
    customer, _ = await customers_repo.get_or_create(
        user_id="test_preserve_values",
        company_id=company.id,
    )

    # Set some initial values
    # Note: backfill_fields_for_company works with customer_fields
    customer.customer_fields = {"existing_field": "existing_value"}
    await customer.save()

    # Create a new customer-level field
    service = FieldsService()
    payload = FieldRequest(
        name="new_field",
        question="New question?",
        type="string",
        level=FieldLevel.CUSTOMER,
    )

    await service.create_field(company.id, payload)

    # Wait for background task
    await asyncio.sleep(0.1)

    # Refresh from DB
    await customer.refresh_from_db()

    # Existing value should be preserved in customer_fields
    assert customer.customer_fields["existing_field"] == "existing_value"
    # New field should be added to customer_fields
    assert "new_field" in customer.customer_fields
    assert customer.customer_fields["new_field"] is None


async def test_service_create_field_backfill_handles_errors_gracefully(company_factory):
    """Test that backfill errors don't affect field creation."""

    company = await company_factory()
    service = FieldsService()

    # Mock backfill to raise an error
    original_backfill = service.customers_repo.backfill_fields_for_company

    async def failing_backfill(company_id: int):
        raise Exception("Backfill failed")

    service.customers_repo.backfill_fields_for_company = failing_backfill

    # Create field should still succeed
    payload = FieldRequest(
        name="test_field",
        question="Test?",
        type="string",
    )

    field = await service.create_field(company.id, payload)

    # Field should be created successfully
    assert field.name == "test_field"
    assert field.company_id == company.id

    # Wait a bit for background task (it will fail but shouldn't affect field creation)
    await asyncio.sleep(0.1)

    # Restore original method
    service.customers_repo.backfill_fields_for_company = original_backfill
