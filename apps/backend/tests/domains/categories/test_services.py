"""Service tests for categories."""

import pytest

from src.backend.modules.categories.exceptions import CategoryNotFoundError
from src.backend.modules.categories.models import Category
from src.backend.modules.categories.service import CategoriesService


async def test_service_get_by_company_empty(company_factory):
    company = await company_factory()
    service = CategoriesService()
    categories = await service.get_by_company(company.id)
    assert categories == []


async def test_service_get_by_company_with_data(company_factory):
    company = await company_factory()
    await Category.create(
        company=company,
        name="Category 1",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )
    await Category.create(
        company=company,
        name="Category 2",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )

    service = CategoriesService()
    categories = await service.get_by_company(company.id)
    assert len(categories) == 2


async def test_service_get_by_id_success(company_factory):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Test Category",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )

    service = CategoriesService()
    found = await service.get_by_id(category.id, company.id)
    assert found.id == category.id
    assert found.name == "Test Category"


async def test_service_get_by_id_not_found(company_factory):
    company = await company_factory()
    service = CategoriesService()
    with pytest.raises(CategoryNotFoundError):
        await service.get_by_id(99999, company.id)


async def test_service_get_by_id_wrong_company(company_factory):
    company1 = await company_factory(name="Company 1")
    company2 = await company_factory(name="Company 2")

    category = await Category.create(
        company=company1,
        name="Test",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )

    service = CategoriesService()
    with pytest.raises(CategoryNotFoundError):
        await service.get_by_id(category.id, company2.id)


async def test_service_create_success(company_factory):
    company = await company_factory()
    service = CategoriesService()

    category = await service.create(
        company_id=company.id,
        name="New Category",
        description="Description",
        rules="Rules",
        examples="Examples",
        workflow="Workflow",
    )

    assert category.name == "New Category"
    assert category.company_id == company.id
    assert isinstance(category.id, int)


async def test_service_create_with_tools(company_factory):
    company = await company_factory()
    service = CategoriesService()
    category = await service.create(
        company_id=company.id,
        name="Category",
        description="Desc",
        rules="Rules",
        examples="",
        workflow="Workflow",
        enabled_tools=["search_kb", "handoff"],
    )
    assert len(category.enabled_tools) == 2
    assert "search_kb" in category.enabled_tools
    assert "handoff" in category.enabled_tools


async def test_service_update_success(company_factory):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Original",
        description="Original",
        rules="Rules",
        workflow="Workflow",
    )

    service = CategoriesService()
    updated = await service.update(
        category.id,
        company.id,
        name="Updated",
        description="Updated",
    )

    assert updated.name == "Updated"
    assert updated.description == "Updated"
    assert updated.rules == "Rules"


async def test_service_update_tools(company_factory):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Category",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
        enabled_tools=["search_kb"],
    )

    service = CategoriesService()
    updated = await service.update(
        category.id,
        company.id,
        enabled_tools=["handoff", "geo_metrics"],
    )
    assert len(updated.enabled_tools) == 2
    assert "handoff" in updated.enabled_tools
    assert "geo_metrics" in updated.enabled_tools


async def test_service_update_not_found(company_factory):
    company = await company_factory()
    service = CategoriesService()
    with pytest.raises(CategoryNotFoundError):
        await service.update(99999, company.id, name="Updated")


async def test_service_delete_success(company_factory):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Delete Me",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )

    service = CategoriesService()
    deleted = await service.delete(category.id, company.id)
    assert deleted is True

    with pytest.raises(CategoryNotFoundError):
        await service.get_by_id(category.id, company.id)


async def test_service_delete_not_found(company_factory):
    company = await company_factory()
    service = CategoriesService()
    with pytest.raises(CategoryNotFoundError):
        await service.delete(99999, company.id)
