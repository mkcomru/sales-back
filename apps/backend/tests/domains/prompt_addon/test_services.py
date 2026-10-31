"""Service tests for prompt addons."""

import pytest

from src.backend.modules.companies.exceptions import CompanyNotFoundError
from src.backend.modules.prompt_addon.exceptions import PromptAddonNotFoundError
from src.backend.modules.prompt_addon.models import PromptAddon
from src.backend.modules.prompt_addon.schemas import PromptAddonPatch
from src.backend.modules.prompt_addon.service import PromptAddonsService


async def test_service_list_addons_empty(company_factory):
    service = PromptAddonsService()
    company = await company_factory()
    result = await service.list_addons(company.id)
    assert result == []


async def test_service_list_addons_with_data(company_factory):
    service = PromptAddonsService()
    company = await company_factory()
    await PromptAddon.create(
        company=company,
        name="Addon 1",
        qualification_workflow="Workflow 1",
        qualification_examples="Examples 1",
    )
    await PromptAddon.create(
        company=company,
        name="Addon 2",
        qualification_workflow="Workflow 2",
        qualification_examples="Examples 2",
    )
    result = await service.list_addons(company.id)
    assert len(result) == 2
    names = {addon.name for addon in result}
    assert "Addon 1" in names
    assert "Addon 2" in names


async def test_service_list_addons_company_not_found():
    service = PromptAddonsService()
    with pytest.raises(CompanyNotFoundError):
        await service.list_addons(99999)


async def test_service_get_addon_success(company_factory):
    service = PromptAddonsService()
    company = await company_factory()
    addon = await PromptAddon.create(
        company=company,
        name="Test Addon",
        qualification_workflow="Test workflow",
        qualification_examples="Test examples",
    )
    result = await service.get_addon(company.id, addon.id)
    assert result.id == addon.id
    assert result.company_id == company.id
    assert result.name == "Test Addon"
    assert result.qualification_workflow == "Test workflow"
    assert result.qualification_examples == "Test examples"


async def test_service_get_addon_not_found(company_factory):
    service = PromptAddonsService()
    company = await company_factory()
    with pytest.raises(PromptAddonNotFoundError):
        await service.get_addon(company.id, 99999)


async def test_service_get_addon_wrong_company(company_factory):
    service = PromptAddonsService()
    company1 = await company_factory()
    company2 = await company_factory()
    addon = await PromptAddon.create(
        company=company1,
        name="Test Addon",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
    )
    with pytest.raises(PromptAddonNotFoundError):
        await service.get_addon(company2.id, addon.id)


async def test_service_create_addon_success(company_factory):
    service = PromptAddonsService()
    company = await company_factory()
    result = await service.create_addon(
        company_id=company.id,
        name="New Addon",
        qualification_workflow="New workflow",
        qualification_examples="New examples",
    )
    assert result.id is not None
    assert result.company_id == company.id
    assert result.name == "New Addon"
    assert result.qualification_workflow == "New workflow"
    assert result.qualification_examples == "New examples"

    addon = await PromptAddon.get(id=result.id)
    assert addon.name == "New Addon"


async def test_service_create_addon_company_not_found():
    service = PromptAddonsService()
    with pytest.raises(CompanyNotFoundError):
        await service.create_addon(
            company_id=99999,
            name="New Addon",
            qualification_workflow="Workflow",
            qualification_examples="Examples",
        )


async def test_service_update_addon_success(company_factory):
    service = PromptAddonsService()
    company = await company_factory()
    addon = await PromptAddon.create(
        company=company,
        name="Original",
        qualification_workflow="Original workflow",
        qualification_examples="Original examples",
    )
    result = await service.update_addon(
        company.id,
        addon.id,
        PromptAddonPatch(name="Updated", qualification_workflow="Updated workflow"),
    )
    assert result.name == "Updated"
    assert result.qualification_workflow == "Updated workflow"
    assert result.qualification_examples == "Original examples"

    refreshed = await PromptAddon.get(id=addon.id)
    assert refreshed.name == "Updated"
    assert refreshed.qualification_workflow == "Updated workflow"


async def test_service_update_addon_not_found(company_factory):
    service = PromptAddonsService()
    company = await company_factory()
    with pytest.raises(PromptAddonNotFoundError):
        await service.update_addon(company.id, 99999, PromptAddonPatch(name="Updated"))


async def test_service_update_addon_wrong_company(company_factory):
    service = PromptAddonsService()
    company1 = await company_factory()
    company2 = await company_factory()
    addon = await PromptAddon.create(
        company=company1,
        name="Test",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
    )
    with pytest.raises(PromptAddonNotFoundError):
        await service.update_addon(company2.id, addon.id, PromptAddonPatch(name="Updated"))


async def test_service_delete_addon_success(company_factory):
    service = PromptAddonsService()
    company = await company_factory()
    addon = await PromptAddon.create(
        company=company,
        name="Delete Me",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
    )
    deleted = await service.delete_addon(company.id, addon.id)
    assert deleted is True

    with pytest.raises(PromptAddonNotFoundError):
        await service.get_addon(company.id, addon.id)


async def test_service_delete_addon_not_found(company_factory):
    service = PromptAddonsService()
    company = await company_factory()
    with pytest.raises(PromptAddonNotFoundError):
        await service.delete_addon(company.id, 99999)


async def test_service_delete_addon_wrong_company(company_factory):
    service = PromptAddonsService()
    company1 = await company_factory()
    company2 = await company_factory()
    addon = await PromptAddon.create(
        company=company1,
        name="Test",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
    )
    with pytest.raises(PromptAddonNotFoundError):
        await service.delete_addon(company2.id, addon.id)
