"""Model tests for products."""

import pytest
from tortoise.exceptions import IntegrityError, ValidationError

from src.backend.modules.categories.models import Category
from src.backend.modules.products.models import Product


async def test_product_required_fields():
    with pytest.raises(ValidationError):
        await Product.create()


async def test_product_name_required(company_factory, category_payload):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Category",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )
    with pytest.raises(ValidationError):
        await Product.create(description="Test", category=category)


async def test_product_description_required(company_factory, category_payload):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Category",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )
    with pytest.raises(IntegrityError):
        await Product.create(name="Test", category=category)


async def test_product_category_nullable(company_factory):
    product = await Product.create(name="Test", description="Description", category=None)
    assert product.category is None


async def test_product_category_cascade_delete(company_factory, category_payload):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Category",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )
    product = await Product.create(name="Test", description="Desc", category=category)
    product_id = product.id
    await category.delete()
    found = await Product.get_or_none(id=product_id)
    assert found is None


async def test_product_name_max_length(company_factory, category_payload):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Category",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )
    long_name = "a" * 256
    with pytest.raises(ValidationError):
        await Product.create(name=long_name, description="Desc", category=category)
