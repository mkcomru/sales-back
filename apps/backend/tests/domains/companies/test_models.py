"""Model tests for companies."""

import pytest
from tortoise.exceptions import ValidationError

from src.backend.modules.companies.models import Company


@pytest.mark.asyncio
async def test_company_default_stage_id():
    company = Company(
        name="Test Company",
        description="Test",
        rules="Rules",
        tone_of_voice="Friendly",
        assistant_name="Assistant",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
        collection_name="test_collection",
    )
    await company.save()
    assert company.crm_default_stage_id == "PROCESSED"
    assert company.crm_manager_attention_stage_id is None


@pytest.mark.asyncio
async def test_company_default_json_fields():
    company = Company(
        name="Test Company",
        description="Test",
        rules="Rules",
        tone_of_voice="Friendly",
        assistant_name="Assistant",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
        collection_name="test_collection",
    )
    await company.save()
    assert company.stages_config == []
    assert company.category_rules == []
    assert company.crm_forward_metadata_keys == []


@pytest.mark.asyncio
async def test_company_json_fields_persist():
    company = Company(
        name="Test Company",
        description="Test",
        rules="Rules",
        tone_of_voice="Friendly",
        assistant_name="Assistant",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
        collection_name="test_collection",
        stages_config=[{"stage": "initial"}],
        category_rules=[{"rule": "test"}],
        crm_forward_metadata_keys=["key1", "key2"],
    )
    await company.save()
    assert company.stages_config == [{"stage": "initial"}]
    assert company.category_rules == [{"rule": "test"}]
    assert company.crm_forward_metadata_keys == ["key1", "key2"]


@pytest.mark.asyncio
async def test_company_required_fields():
    with pytest.raises(ValidationError):
        company = Company()
        await company.save()


@pytest.mark.asyncio
async def test_company_name_max_length():
    long_name = "a" * 256
    company = Company(
        name=long_name,
        description="Test",
        rules="Rules",
        tone_of_voice="Friendly",
        assistant_name="Assistant",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
        collection_name="test_collection",
    )
    with pytest.raises(ValidationError):
        await company.save()


@pytest.mark.asyncio
async def test_company_crm_manager_attention_stage_id_nullable():
    company = Company(
        name="Test Company",
        description="Test",
        rules="Rules",
        tone_of_voice="Friendly",
        assistant_name="Assistant",
        qualification_workflow="Workflow",
        qualification_examples="Examples",
        collection_name="test_collection",
        crm_manager_attention_stage_id=None,
    )
    await company.save()
    assert company.crm_manager_attention_stage_id is None

    company.crm_manager_attention_stage_id = "ATTENTION"
    await company.save()
    assert company.crm_manager_attention_stage_id == "ATTENTION"
