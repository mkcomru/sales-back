"""Service tests for field options."""

import pytest

from src.backend.modules.fields.exceptions import FieldOptionNotFoundError
from src.backend.modules.fields.models import AnswerType, Field, FieldOption
from src.backend.modules.fields.service import FieldOptionsService


async def test_service_list_options_empty(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Enum Field",
        question="Q?",
        answer_type=AnswerType.ENUM,
    )

    service = FieldOptionsService()
    options = await service.list_options(field.id)
    assert options == []


async def test_service_list_options_with_data(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Enum Field",
        question="Q?",
        answer_type=AnswerType.ENUM,
    )
    await FieldOption.create(field=field, value="Option 1", order=0)
    await FieldOption.create(field=field, value="Option 2", order=1)

    service = FieldOptionsService()
    options = await service.list_options(field.id)
    assert len(options) == 2


async def test_service_get_option_success(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Enum Field",
        question="Q?",
        answer_type=AnswerType.ENUM,
    )
    option = await FieldOption.create(field=field, value="Test Option", order=0)

    service = FieldOptionsService()
    found = await service.get_option(option.id, field.id)
    assert found.id == option.id
    assert found.value == "Test Option"


async def test_service_get_option_not_found(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Enum Field",
        question="Q?",
        answer_type=AnswerType.ENUM,
    )

    service = FieldOptionsService()
    with pytest.raises(FieldOptionNotFoundError):
        await service.get_option(99999, field.id)


async def test_service_create_option_success(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Enum Field",
        question="Q?",
        answer_type=AnswerType.ENUM,
    )

    service = FieldOptionsService()
    option = await service.create_option(field.id, "New Option", 1)
    assert option.value == "New Option"
    assert option.order == 1
    assert option.field_id == field.id


async def test_service_update_option_success(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Enum Field",
        question="Q?",
        answer_type=AnswerType.ENUM,
    )
    option = await FieldOption.create(field=field, value="Original", order=0)

    service = FieldOptionsService()
    updated = await service.update_option(option.id, field.id, "Updated", 1)
    assert updated.value == "Updated"
    assert updated.order == 1


async def test_service_update_option_not_found(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Enum Field",
        question="Q?",
        answer_type=AnswerType.ENUM,
    )

    service = FieldOptionsService()
    with pytest.raises(FieldOptionNotFoundError):
        await service.update_option(99999, field.id, "Updated", 0)


async def test_service_delete_option_success(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Enum Field",
        question="Q?",
        answer_type=AnswerType.ENUM,
    )
    option = await FieldOption.create(field=field, value="Delete Me", order=0)

    service = FieldOptionsService()
    deleted = await service.delete_option(option.id, field.id)
    assert deleted is True

    with pytest.raises(FieldOptionNotFoundError):
        await service.get_option(option.id, field.id)


async def test_service_delete_option_not_found(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Enum Field",
        question="Q?",
        answer_type=AnswerType.ENUM,
    )

    service = FieldOptionsService()
    with pytest.raises(FieldOptionNotFoundError):
        await service.delete_option(99999, field.id)
