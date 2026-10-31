"""Tests for system customer fields."""

import pytest

from src.backend.modules.companies.service import CompaniesService
from src.backend.modules.fields.models import AnswerType, Field, FieldLevel
from src.backend.modules.fields.repository import FieldsRepository


@pytest.mark.asyncio
async def test_create_company_does_not_create_system_fields(company_factory, user_factory):
    """Test that creating a company does not automatically create system customer fields."""
    from src.backend.modules.companies.models import Company

    service = CompaniesService()
    user = await user_factory()

    # Create company
    company_data = {
        "name": "Test Company",
        "description": "Test Description",
        "rules": "Test rules",
        "tone_of_voice": "Professional",
        "assistant_name": "Test Assistant",
        "collection_name": "test_collection",
        "qualification_workflow": "Standard",
        "qualification_examples": "Example 1",
    }
    company_response = await service.create_company(creator_id=user.id, **company_data)
    company = await Company.get(id=company_response.id)

    # Check that no system fields were created automatically
    fields_repo = FieldsRepository()
    fields = await fields_repo.list_by_company(company.id)

    # Should have no system fields
    system_fields = [f for f in fields if f.is_system]
    assert len(system_fields) == 0


@pytest.mark.asyncio
async def test_system_fields_cannot_be_deleted(company_factory):
    """Test that system fields cannot be deleted."""
    from src.backend.modules.fields.exceptions import SystemFieldError
    from src.backend.modules.fields.service import FieldsService

    company = await company_factory()
    service = FieldsService()

    # Get system field (should exist if company was created via CompaniesService.create_company)
    # For this test, we'll create a system field manually
    system_field = await Field.create(
        company=company,
        name="phone",
        question="Phone number",
        answer_type=AnswerType.STRING,
        required=False,
        display_name="Phone",
        level=FieldLevel.CUSTOMER,
        is_system=True,
    )

    # Try to delete - should fail
    with pytest.raises(SystemFieldError, match="Cannot delete system field"):
        await service.delete_field(field_id=system_field.id, company_id=company.id)

    # Verify field still exists
    retrieved = await service.get_field(field_id=system_field.id, company_id=company.id)
    assert retrieved.id == system_field.id


@pytest.mark.asyncio
async def test_system_fields_have_correct_level(company_factory):
    """Test that all system fields have level=CUSTOMER."""
    company = await company_factory()

    # Create system field with CUSTOMER level - should succeed
    field = await Field.create(
        company=company,
        name="test_system",
        question="Test?",
        answer_type=AnswerType.STRING,
        level=FieldLevel.CUSTOMER,
        is_system=True,
    )

    assert field.level == FieldLevel.CUSTOMER
    assert field.is_system is True


@pytest.mark.asyncio
async def test_system_fields_cannot_have_order_level(company_factory):
    """Test that system fields cannot have level=ORDER."""
    from src.backend.modules.fields.service import FieldsService

    company = await company_factory()
    service = FieldsService()

    # Try to create system field with ORDER level - should fail
    from src.backend.modules.fields.schemas import FieldRequest

    with pytest.raises(ValueError, match="is_system=True is only allowed for level=CUSTOMER"):
        await service.create_field(
            company_id=company.id,
            payload=FieldRequest(
                name="order_system",
                question="Order system?",
                type="string",
                level=FieldLevel.ORDER,
                is_system=True,
            ),
        )
