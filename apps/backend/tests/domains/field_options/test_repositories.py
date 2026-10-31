"""Repository tests for field options."""

from src.backend.modules.fields.models import AnswerType, Field, FieldOption
from src.backend.modules.fields.repository import FieldOptionsRepository


async def test_repository_list_by_field_empty(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Enum Field",
        question="Q?",
        answer_type=AnswerType.ENUM,
    )

    repo = FieldOptionsRepository()
    options = await repo.list_by_field(field.id)
    assert options == []


async def test_repository_list_by_field_with_data(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Enum Field",
        question="Q?",
        answer_type=AnswerType.ENUM,
    )
    await FieldOption.create(field=field, value="Option 1", order=0)
    await FieldOption.create(field=field, value="Option 2", order=1)

    repo = FieldOptionsRepository()
    options = await repo.list_by_field(field.id)
    assert len(options) == 2
    values = {opt.value for opt in options}
    assert "Option 1" in values
    assert "Option 2" in values


async def test_repository_get_by_id_success(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Enum Field",
        question="Q?",
        answer_type=AnswerType.ENUM,
    )
    option = await FieldOption.create(field=field, value="Test Option", order=0)

    repo = FieldOptionsRepository()
    found = await repo.get_by_id(option.id)
    assert found is not None
    assert found.id == option.id
    assert found.value == "Test Option"


async def test_repository_get_by_id_not_found():
    repo = FieldOptionsRepository()
    found = await repo.get_by_id(99999)
    assert found is None


async def test_repository_create_success(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Enum Field",
        question="Q?",
        answer_type=AnswerType.ENUM,
    )

    repo = FieldOptionsRepository()
    option = await repo.create(field.id, "New Option", 1)
    assert option.id is not None
    assert option.value == "New Option"
    assert option.order == 1
    assert option.field_id == field.id


async def test_repository_update_success(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Enum Field",
        question="Q?",
        answer_type=AnswerType.ENUM,
    )
    option = await FieldOption.create(field=field, value="Original", order=0)

    repo = FieldOptionsRepository()
    updated = await repo.update(option.id, {"value": "Updated", "order": 1})
    assert updated is not None
    assert updated.value == "Updated"
    assert updated.order == 1


async def test_repository_update_not_found():
    repo = FieldOptionsRepository()
    updated = await repo.update(99999, {"value": "Updated"})
    assert updated is None


async def test_repository_delete_success(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Enum Field",
        question="Q?",
        answer_type=AnswerType.ENUM,
    )
    option = await FieldOption.create(field=field, value="Delete Option", order=0)

    repo = FieldOptionsRepository()
    deleted = await repo.delete(option.id)
    assert deleted is True
    found = await FieldOption.get_or_none(id=option.id)
    assert found is None


async def test_repository_delete_not_found():
    repo = FieldOptionsRepository()
    deleted = await repo.delete(99999)
    assert deleted is False
