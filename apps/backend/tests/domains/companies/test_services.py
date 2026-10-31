"""Service-layer tests for companies."""

import pytest

from src.backend.modules.companies.exceptions import CompanyNotFoundError
from src.backend.modules.companies.models import Company
from src.backend.modules.companies.service import CompaniesService


@pytest.mark.asyncio
async def test_list_companies_empty():
    service = CompaniesService()
    result = await service.list_companies()
    assert result == []


@pytest.mark.asyncio
async def test_list_companies_with_data(company_factory):
    await company_factory(name="Company 1")
    await company_factory(name="Company 2")
    service = CompaniesService()
    result = await service.list_companies()
    assert len(result) == 2
    names = {c.name for c in result}
    assert "Company 1" in names
    assert "Company 2" in names


@pytest.mark.asyncio
async def test_get_company_success(company_factory):
    company = await company_factory(
        name="Test Company",
        description="Test Description",
        rules="Test Rules",
    )
    service = CompaniesService()
    result = await service.get_company(company.id)
    assert result.id == company.id
    assert result.name == "Test Company"
    assert result.description == "Test Description"
    assert result.enabled_tools == []


@pytest.mark.asyncio
async def test_get_company_not_found():
    service = CompaniesService()
    with pytest.raises(CompanyNotFoundError):
        await service.get_company(99999)


@pytest.mark.asyncio
async def test_create_company_success(test_superuser):
    service = CompaniesService()
    result = await service.create_company(
        creator_id=test_superuser.id,
        name="New Company",
        description="New Description",
        rules="New Rules",
        tone_of_voice="Professional",
        assistant_name="Assistant",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
        collection_name="new_collection",
    )
    assert result.id is not None
    assert result.name == "New Company"
    assert result.description == "New Description"
    assert result.enabled_tools == []


@pytest.mark.asyncio
async def test_create_company_with_tools(test_superuser):
    service = CompaniesService()
    result = await service.create_company(
        creator_id=test_superuser.id,
        name="Company with Tools",
        description="Description",
        rules="Rules",
        tone_of_voice="Friendly",
        assistant_name="Assistant",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
        collection_name="collection",
        enabled_tools=["search_kb", "handoff"],
    )
    assert len(result.enabled_tools) == 2
    assert "search_kb" in result.enabled_tools
    assert "handoff" in result.enabled_tools


@pytest.mark.asyncio
async def test_update_company_success(company_factory):
    company = await company_factory(
        name="Original Name",
        description="Original Description",
        rules="Rules",
    )
    service = CompaniesService()
    result = await service.update_company(company.id, {"name": "Updated Name", "description": "Updated Description"})
    assert result.name == "Updated Name"
    assert result.description == "Updated Description"
    assert result.rules == "Rules"


@pytest.mark.asyncio
async def test_update_company_not_found():
    service = CompaniesService()
    with pytest.raises(CompanyNotFoundError):
        await service.update_company(99999, {"name": "Updated"})


@pytest.mark.asyncio
async def test_update_company_tools(company_factory):
    company = await company_factory(name="Company")
    service = CompaniesService()
    result = await service.update_company(company.id, {"enabled_tools": ["search_kb", "geo_metrics"]})
    assert len(result.enabled_tools) == 2
    assert "search_kb" in result.enabled_tools
    assert "geo_metrics" in result.enabled_tools


@pytest.mark.asyncio
async def test_delete_company_success(company_factory):
    company = await company_factory(name="To Delete")
    service = CompaniesService()
    result = await service.delete_company(company.id)
    assert result is True
    found = await Company.get_or_none(id=company.id)
    assert found is None


@pytest.mark.asyncio
async def test_delete_company_not_found():
    service = CompaniesService()
    with pytest.raises(CompanyNotFoundError):
        await service.delete_company(99999)


@pytest.mark.asyncio
async def test_get_config_success(company_factory):
    company = await company_factory(
        name="Test Company",
        description="Description",
        rules="Test Rules",
        assistant_name="Test Assistant",
    )
    service = CompaniesService()
    result = await service.get_config(company.id)
    assert result.id == company.id
    assert result.rules == "Test Rules"
    assert result.assistant_name == "Test Assistant"
    assert isinstance(result.enabled_tools, list)


@pytest.mark.asyncio
async def test_get_config_not_found():
    service = CompaniesService()
    with pytest.raises(CompanyNotFoundError):
        await service.get_config(99999)


@pytest.mark.asyncio
async def test_get_company_products_empty(company_factory):
    company = await company_factory(name="Company")
    service = CompaniesService()
    result = await service.get_company_products(company.id)
    assert result.categories == []
    assert result.products == []
    assert result.fields == []


@pytest.mark.asyncio
async def test_get_company_products_not_found():
    service = CompaniesService()
    with pytest.raises(CompanyNotFoundError):
        await service.get_company_products(99999)
