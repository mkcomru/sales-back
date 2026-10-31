"""Repository tests for prompt addons."""

from src.backend.modules.prompt_addon.models import PromptAddon
from src.backend.modules.prompt_addon.repository import PromptAddonsRepository


async def test_repository_get_by_id_success(company_factory):
    repository = PromptAddonsRepository()
    company = await company_factory()
    addon = await PromptAddon.create(
        company=company,
        name="Test Addon",
        qualification_workflow="Test workflow",
        qualification_examples="Test examples",
    )
    result = await repository.get_by_id(addon.id)
    assert result is not None
    assert result.id == addon.id
    assert result.name == "Test Addon"
    assert result.qualification_workflow == "Test workflow"
    assert result.qualification_examples == "Test examples"


async def test_repository_get_by_id_not_found():
    repository = PromptAddonsRepository()
    result = await repository.get_by_id(99999)
    assert result is None


async def test_repository_list_by_company(company_factory):
    repository = PromptAddonsRepository()
    company1 = await company_factory()
    company2 = await company_factory()

    await PromptAddon.create(
        company=company1,
        name="Addon 1",
        qualification_workflow="Workflow 1",
        qualification_examples="Examples 1",
    )
    await PromptAddon.create(
        company=company1,
        name="Addon 2",
        qualification_workflow="Workflow 2",
        qualification_examples="Examples 2",
    )
    await PromptAddon.create(
        company=company2,
        name="Addon 3",
        qualification_workflow="Workflow 3",
        qualification_examples="Examples 3",
    )

    result = await repository.list_by_company(company1.id)
    assert len(result) == 2
    names = {addon.name for addon in result}
    assert "Addon 1" in names
    assert "Addon 2" in names
    assert "Addon 3" not in names


async def test_repository_create(company_factory):
    repository = PromptAddonsRepository()
    company = await company_factory()
    result = await repository.create(
        company_id=company.id,
        name="New Addon",
        qualification_workflow="New workflow",
        qualification_examples="New examples",
    )
    assert result.id is not None
    assert result.name == "New Addon"
    assert result.qualification_workflow == "New workflow"
    assert result.qualification_examples == "New examples"
    assert result.company_id == company.id


async def test_repository_update(company_factory):
    repository = PromptAddonsRepository()
    company = await company_factory()
    addon = await PromptAddon.create(
        company=company,
        name="Original",
        qualification_workflow="Original workflow",
        qualification_examples="Original examples",
    )
    result = await repository.update(
        addon.id,
        {"name": "Updated", "qualification_workflow": "Updated workflow"},
    )
    assert result is not None
    assert result.name == "Updated"
    assert result.qualification_workflow == "Updated workflow"
    assert result.qualification_examples == "Original examples"

    refreshed = await PromptAddon.get(id=addon.id)
    assert refreshed.name == "Updated"
    assert refreshed.qualification_workflow == "Updated workflow"


async def test_repository_update_not_found():
    repository = PromptAddonsRepository()
    result = await repository.update(99999, {"name": "Updated"})
    assert result is None


async def test_repository_delete(company_factory):
    repository = PromptAddonsRepository()
    company = await company_factory()
    addon = await PromptAddon.create(
        company=company,
        name="Delete Me",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
    )
    deleted = await repository.delete(addon.id)
    assert deleted is True

    result = await repository.get_by_id(addon.id)
    assert result is None


async def test_repository_delete_not_found():
    repository = PromptAddonsRepository()
    deleted = await repository.delete(99999)
    assert deleted is False
