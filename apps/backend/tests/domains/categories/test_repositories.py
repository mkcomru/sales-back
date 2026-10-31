"""Repository tests for categories."""

from src.backend.modules.categories.models import Category
from src.backend.modules.categories.repository import CategoriesRepository


async def test_repository_get_by_company_id_empty(company_factory):
    company = await company_factory()
    repo = CategoriesRepository()
    categories = await repo.get_by_company_id(company.id)
    assert categories == []


async def test_repository_get_by_company_id_with_data(company_factory):
    company1 = await company_factory(name="Company 1")
    company2 = await company_factory(name="Company 2")

    await Category.create(
        company=company1,
        name="Category 1",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )
    await Category.create(
        company=company1,
        name="Category 2",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )
    await Category.create(
        company=company2,
        name="Category 3",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )

    repo = CategoriesRepository()
    company1_categories = await repo.get_by_company_id(company1.id)
    assert len(company1_categories) == 2
    names = {c.name for c in company1_categories}
    assert "Category 1" in names
    assert "Category 2" in names

    company2_categories = await repo.get_by_company_id(company2.id)
    assert len(company2_categories) == 1
    assert company2_categories[0].name == "Category 3"


async def test_repository_get_by_id_and_company_success(company_factory):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Test Category",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )

    repo = CategoriesRepository()
    found = await repo.get_by_id_and_company(category.id, company.id)
    assert found is not None
    assert found.id == category.id
    assert found.name == "Test Category"


async def test_repository_get_by_id_and_company_not_found(company_factory):
    company = await company_factory()
    repo = CategoriesRepository()
    found = await repo.get_by_id_and_company(99999, company.id)
    assert found is None


async def test_repository_get_by_id_and_company_wrong_company(company_factory):
    company1 = await company_factory(name="Company 1")
    company2 = await company_factory(name="Company 2")

    category = await Category.create(
        company=company1,
        name="Test",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )

    repo = CategoriesRepository()
    found = await repo.get_by_id_and_company(category.id, company2.id)
    assert found is None


async def test_repository_delete_by_id_and_company_success(company_factory):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Test",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )

    repo = CategoriesRepository()
    deleted = await repo.delete_by_id_and_company(category.id, company.id)
    assert deleted is True

    found = await Category.get_or_none(id=category.id)
    assert found is None


async def test_repository_delete_by_id_and_company_not_found(company_factory):
    company = await company_factory()
    repo = CategoriesRepository()
    deleted = await repo.delete_by_id_and_company(99999, company.id)
    assert deleted is False


async def test_repository_delete_by_id_and_company_wrong_company(company_factory):
    company1 = await company_factory(name="Company 1")
    company2 = await company_factory(name="Company 2")

    category = await Category.create(
        company=company1,
        name="Test",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )

    repo = CategoriesRepository()
    deleted = await repo.delete_by_id_and_company(category.id, company2.id)
    assert deleted is False

    found = await Category.get_or_none(id=category.id)
    assert found is not None
