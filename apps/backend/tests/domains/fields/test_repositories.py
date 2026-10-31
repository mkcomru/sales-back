"""Repository tests for fields."""

from src.backend.modules.categories.models import Category
from src.backend.modules.fields.models import AnswerType, Field
from src.backend.modules.fields.repository import FieldsRepository


async def test_repository_list_by_company_empty(company_factory):
    company = await company_factory()
    repo = FieldsRepository()
    fields = await repo.list_by_company(company.id)
    assert fields == []


async def test_repository_list_by_company_with_data(company_factory):
    company1 = await company_factory(name="Company 1")
    company2 = await company_factory(name="Company 2")

    await Field.create(
        company=company1,
        name="Field 1",
        question="Q1?",
        answer_type=AnswerType.STRING,
    )
    await Field.create(
        company=company1,
        name="Field 2",
        question="Q2?",
        answer_type=AnswerType.NUMBER,
    )
    await Field.create(
        company=company2,
        name="Field 3",
        question="Q3?",
        answer_type=AnswerType.BOOLEAN,
    )

    repo = FieldsRepository()
    company1_fields = await repo.list_by_company(company1.id)
    assert len(company1_fields) == 2
    names = {f.name for f in company1_fields}
    assert "Field 1" in names
    assert "Field 2" in names


async def test_repository_list_by_category(company_factory, category_payload):
    company = await company_factory()
    category1 = await Category.create(
        company=company,
        name="Category 1",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )
    category2 = await Category.create(
        company=company,
        name="Category 2",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )

    await Field.create(
        company=company,
        name="Field 1",
        question="Q1?",
        answer_type=AnswerType.STRING,
        category=category1,
    )
    await Field.create(
        company=company,
        name="Field 2",
        question="Q2?",
        answer_type=AnswerType.STRING,
        category=category1,
    )
    await Field.create(
        company=company,
        name="Field 3",
        question="Q3?",
        answer_type=AnswerType.STRING,
        category=category2,
    )

    repo = FieldsRepository()
    cat1_fields = await repo.list_by_category(category1.id)
    assert len(cat1_fields) == 2


async def test_repository_get_by_id_success(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Test Field",
        question="Question?",
        answer_type=AnswerType.STRING,
    )

    repo = FieldsRepository()
    found = await repo.get_by_id(field.id)
    assert found is not None
    assert found.id == field.id
    assert found.name == "Test Field"


async def test_repository_get_by_id_not_found():
    repo = FieldsRepository()
    found = await repo.get_by_id(99999)
    assert found is None


async def test_repository_create_success(company_factory):
    company = await company_factory()
    repo = FieldsRepository()

    field = await repo.create(
        company_id=company.id,
        name="New Field",
        question="Question?",
        answer_type=AnswerType.STRING,
        required=True,
    )

    assert field.id is not None
    assert field.name == "New Field"
    assert field.company_id == company.id
    assert field.required is True


async def test_repository_update_success(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Original",
        question="Original?",
        answer_type=AnswerType.STRING,
    )

    repo = FieldsRepository()
    updated = await repo.update(field.id, {"name": "Updated", "question": "Updated?"})
    assert updated is not None
    assert updated.name == "Updated"
    assert updated.question == "Updated?"


async def test_repository_update_not_found():
    repo = FieldsRepository()
    updated = await repo.update(99999, {"name": "Updated"})
    assert updated is None


async def test_repository_delete_success(company_factory):
    company = await company_factory()
    field = await Field.create(
        company=company,
        name="Delete Field",
        question="Q?",
        answer_type=AnswerType.STRING,
    )

    repo = FieldsRepository()
    deleted = await repo.delete(field.id)
    assert deleted is True
    found = await Field.get_or_none(id=field.id)
    assert found is None


async def test_repository_delete_not_found():
    repo = FieldsRepository()
    deleted = await repo.delete(99999)
    assert deleted is False
