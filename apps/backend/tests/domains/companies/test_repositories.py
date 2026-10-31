"""Repository tests for companies."""

import pytest

from src.backend.modules.companies.models import Company
from src.backend.modules.companies.repository import CompaniesRepository


@pytest.mark.asyncio
async def test_repository_list_empty():
    repository = CompaniesRepository()
    result = await repository.list()
    assert result == []


@pytest.mark.asyncio
async def test_repository_list_with_data(company_factory):
    company1 = await company_factory(name="Company 1", collection_name="collection1")
    company2 = await company_factory(name="Company 2", collection_name="collection2")
    repository = CompaniesRepository()
    result = await repository.list()
    assert len(result) == 2
    ids = {c.id for c in result}
    assert company1.id in ids
    assert company2.id in ids


@pytest.mark.asyncio
async def test_repository_get_by_id_success(company_factory):
    company = await company_factory(
        name="Test Company",
        description="Description",
        rules="Rules",
        collection_name="collection",
    )
    repository = CompaniesRepository()
    result = await repository.get_by_id(company.id)
    assert result is not None
    assert result.id == company.id
    assert result.name == "Test Company"


@pytest.mark.asyncio
async def test_repository_get_by_id_not_found():
    repository = CompaniesRepository()
    result = await repository.get_by_id(99999)
    assert result is None


@pytest.mark.asyncio
async def test_repository_create_success():
    repository = CompaniesRepository()
    result = await repository.create(
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


@pytest.mark.asyncio
async def test_repository_create_with_optional_fields():
    repository = CompaniesRepository()
    result = await repository.create(
        name="Company",
        description="Description",
        rules="Rules",
        tone_of_voice="Friendly",
        assistant_name="Assistant",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
        collection_name="collection",
        crm_default_stage_id="CUSTOM_STAGE",
        crm_manager_attention_stage_id="ATTENTION",
        stages_config=[{"stage": "test"}],
    )
    assert result.crm_default_stage_id == "CUSTOM_STAGE"
    assert result.crm_manager_attention_stage_id == "ATTENTION"
    assert result.stages_config == [{"stage": "test"}]


@pytest.mark.asyncio
async def test_repository_update_success(company_factory):
    company = await company_factory(
        name="Original Name",
        description="Original Description",
        rules="Rules",
    )
    repository = CompaniesRepository()
    result = await repository.update(company.id, {"name": "Updated Name", "description": "Updated Description"})
    assert result is not None
    assert result.name == "Updated Name"
    assert result.description == "Updated Description"
    assert result.rules == "Rules"


@pytest.mark.asyncio
async def test_repository_update_not_found():
    repository = CompaniesRepository()
    result = await repository.update(99999, {"name": "Updated"})
    assert result is None


@pytest.mark.asyncio
async def test_repository_delete_success(company_factory):
    company = await company_factory(name="To Delete")
    repository = CompaniesRepository()
    result = await repository.delete(company.id)
    assert result is True
    found = await Company.get_or_none(id=company.id)
    assert found is None


@pytest.mark.asyncio
async def test_repository_delete_not_found():
    repository = CompaniesRepository()
    result = await repository.delete(99999)
    assert result is False


@pytest.mark.asyncio
async def test_repository_get_config_success(company_factory):
    company = await company_factory(
        name="Test Company",
        description="Description",
        rules="Test Rules",
        assistant_name="Test Assistant",
        stages_config=[{"stage": "initial"}],
        category_rules=[{"rule": "test"}],
    )
    repository = CompaniesRepository()
    result = await repository.get_config(company.id)
    assert result is not None
    assert result["id"] == company.id
    assert result["name"] == "Test Company"
    assert result["rules"] == "Test Rules"
    assert result["assistant_name"] == "Test Assistant"
    assert result["stages_config"] == [{"stage": "initial"}]
    assert result["category_rules"] == [{"rule": "test"}]


@pytest.mark.asyncio
async def test_repository_get_config_not_found():
    repository = CompaniesRepository()
    result = await repository.get_config(99999)
    assert result is None
