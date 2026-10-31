"""Model tests for field options."""

import pytest
from tortoise.exceptions import IntegrityError, ValidationError

from src.backend.modules.fields.models import AnswerType, Field, FieldOption


async def test_field_option_required_fields():
    with pytest.raises((ValidationError, IntegrityError)):
        await FieldOption.create()


async def test_field_option_field_required(company_factory):
    await company_factory()
    with pytest.raises((ValidationError, IntegrityError)):
        await FieldOption.create(value="Option", order=0)


async def test_field_option_value_required(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Enum Field",
        question="Q?",
        answer_type=AnswerType.ENUM,
    )
    with pytest.raises(ValidationError):
        await FieldOption.create(field=field, order=0)


async def test_field_option_order_default(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Enum Field",
        question="Q?",
        answer_type=AnswerType.ENUM,
    )
    option = await FieldOption.create(field=field, value="Option")
    assert option.order == 0


async def test_field_option_unique_value_per_field(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Enum Field",
        question="Q?",
        answer_type=AnswerType.ENUM,
    )
    await FieldOption.create(field=field, value="Option 1", order=0)
    with pytest.raises(IntegrityError):
        await FieldOption.create(field=field, value="Option 1", order=1)


async def test_field_option_unique_order_per_field(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Enum Field",
        question="Q?",
        answer_type=AnswerType.ENUM,
    )
    await FieldOption.create(field=field, value="Option 1", order=0)
    with pytest.raises(IntegrityError):
        await FieldOption.create(field=field, value="Option 2", order=0)


async def test_field_option_cascade_delete(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Enum Field",
        question="Q?",
        answer_type=AnswerType.ENUM,
    )
    option = await FieldOption.create(field=field, value="Option", order=0)
    option_id = option.id
    await field.delete()
    found = await FieldOption.get_or_none(id=option_id)
    assert found is None


async def test_field_option_value_max_length(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Enum Field",
        question="Q?",
        answer_type=AnswerType.ENUM,
    )
    long_value = "a" * 256
    with pytest.raises(ValidationError):
        await FieldOption.create(field=field, value=long_value, order=0)
