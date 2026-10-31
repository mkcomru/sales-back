"""Model tests for categories."""

import pytest
from tortoise.exceptions import IntegrityError, ValidationError

from src.backend.modules.categories.models import Category


async def test_category_required_fields():
    with pytest.raises(ValidationError):
        await Category.create()


async def test_category_name_required(company_factory):
    company = await company_factory()
    with pytest.raises(ValidationError):
        await Category.create(
            company=company,
            description="Test",
            rules="Rules",
            workflow="Workflow",
        )


async def test_category_description_required(company_factory):
    company = await company_factory()
    with pytest.raises(IntegrityError):
        await Category.create(
            company=company,
            name="Test",
            rules="Rules",
            workflow="Workflow",
        )


async def test_category_rules_required(company_factory):
    company = await company_factory()
    with pytest.raises(IntegrityError):
        await Category.create(
            company=company,
            name="Test",
            description="Desc",
            workflow="Workflow",
        )


async def test_category_workflow_required(company_factory):
    company = await company_factory()
    with pytest.raises(IntegrityError):
        await Category.create(
            company=company,
            name="Test",
            description="Desc",
            rules="Rules",
        )


async def test_category_examples_default(company_factory):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Test",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )
    assert category.examples == ""


async def test_category_company_required():
    with pytest.raises((ValidationError, IntegrityError)):
        await Category.create(
            name="Test",
            description="Desc",
            rules="Rules",
            workflow="Workflow",
        )


async def test_category_cascade_delete(company_factory):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Test",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )
    category_id = category.id
    await company.delete()
    found = await Category.get_or_none(id=category_id)
    assert found is None


async def test_category_name_max_length(company_factory):
    company = await company_factory()
    long_name = "a" * 256
    with pytest.raises(ValidationError):
        await Category.create(
            company=company,
            name=long_name,
            description="Desc",
            rules="Rules",
            workflow="Workflow",
        )
