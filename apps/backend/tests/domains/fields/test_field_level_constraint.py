"""Tests for field level constraints and validation."""

import pytest

from src.backend.modules.fields.exceptions import FieldNotFoundError, SystemFieldError
from src.backend.modules.fields.models import FieldLevel
from src.backend.modules.fields.schemas import FieldRequest
from src.backend.modules.fields.service import FieldsService


@pytest.mark.asyncio
async def test_is_system_only_allowed_for_customer_level(company_factory):
    """Test that is_system=True is only allowed for level=CUSTOMER."""
    company = await company_factory()
    service = FieldsService()

    # Try to create order-level field with is_system=True - should fail
    with pytest.raises(ValueError, match="is_system=True is only allowed for level=CUSTOMER"):
        await service.create_field(
            company_id=company.id,
            payload=FieldRequest(
                name="order_field",
                question="Order field?",
                type="string",
                level=FieldLevel.ORDER,
                is_system=True,
            ),
        )

    # Create customer-level field with is_system=True - should succeed
    field = await service.create_field(
        company_id=company.id,
        payload=FieldRequest(
            name="customer_field",
            question="Customer field?",
            type="string",
            level=FieldLevel.CUSTOMER,
            is_system=True,
        ),
    )

    assert field.level == FieldLevel.CUSTOMER
    assert field.is_system is True


@pytest.mark.asyncio
async def test_update_field_cannot_set_is_system_for_order_level(company_factory):
    """Test that updating field to order level with is_system=True fails."""
    company = await company_factory()
    service = FieldsService()

    # Create customer-level field
    field = await service.create_field(
        company_id=company.id,
        payload=FieldRequest(
            name="test_field",
            question="Test?",
            type="string",
            level=FieldLevel.CUSTOMER,
            is_system=False,
        ),
    )

    # Try to update to order level with is_system=True - should fail
    from src.backend.modules.fields.schemas import FieldPatch

    with pytest.raises(ValueError, match="is_system=True is only allowed for level=CUSTOMER"):
        await service.update_field(
            field_id=field.id,
            company_id=company.id,
            payload=FieldPatch(
                level=FieldLevel.ORDER,
                is_system=True,
            ),
        )


@pytest.mark.asyncio
async def test_update_field_cannot_change_level_with_is_system_true(company_factory):
    """Test that system field cannot be changed to order level."""
    company = await company_factory()
    service = FieldsService()

    # Create system customer-level field
    field = await service.create_field(
        company_id=company.id,
        payload=FieldRequest(
            name="system_field",
            question="System?",
            type="string",
            level=FieldLevel.CUSTOMER,
            is_system=True,
        ),
    )

    # Try to change level to ORDER (even with is_system=False) - should fail validation
    # Actually, the constraint is: if is_system=True, level must be CUSTOMER
    # So changing level to ORDER while is_system=True should fail
    from src.backend.modules.fields.schemas import FieldPatch

    with pytest.raises(ValueError, match="is_system=True is only allowed for level=CUSTOMER"):
        await service.update_field(
            field_id=field.id,
            company_id=company.id,
            payload=FieldPatch(
                level=FieldLevel.ORDER,
            ),
        )


@pytest.mark.asyncio
async def test_system_field_cannot_be_deleted(company_factory):
    """Test that system fields cannot be deleted."""
    company = await company_factory()
    service = FieldsService()

    # Create system field
    field = await service.create_field(
        company_id=company.id,
        payload=FieldRequest(
            name="system_field",
            question="System?",
            type="string",
            level=FieldLevel.CUSTOMER,
            is_system=True,
        ),
    )

    # Try to delete - should fail
    with pytest.raises(SystemFieldError, match="Cannot delete system field"):
        await service.delete_field(field_id=field.id, company_id=company.id)

    # Verify field still exists
    retrieved = await service.get_field(field_id=field.id, company_id=company.id)
    assert retrieved.id == field.id


@pytest.mark.asyncio
async def test_non_system_field_can_be_deleted(company_factory):
    """Test that non-system fields can be deleted."""
    company = await company_factory()
    service = FieldsService()

    # Create non-system field
    field = await service.create_field(
        company_id=company.id,
        payload=FieldRequest(
            name="regular_field",
            question="Regular?",
            type="string",
            level=FieldLevel.CUSTOMER,
            is_system=False,
        ),
    )

    # Delete should succeed
    deleted = await service.delete_field(field_id=field.id, company_id=company.id)
    assert deleted is True

    # Verify field is deleted
    with pytest.raises(FieldNotFoundError):
        await service.get_field(field_id=field.id, company_id=company.id)
