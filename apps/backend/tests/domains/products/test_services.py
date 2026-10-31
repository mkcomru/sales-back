"""Service tests for products."""

import pytest

from src.backend.modules.categories.models import Category
from src.backend.modules.products.exceptions import ProductNotFoundError
from src.backend.modules.products.models import Product
from src.backend.modules.products.schemas import ProductPatch, ProductRequest
from src.backend.modules.products.service import ProductsService


async def test_service_list_available_products_empty():
    service = ProductsService()
    products = await service.list_available_products()
    assert products == []


async def test_service_list_available_products_with_data(company_factory, category_payload):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Category",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )
    await Product.create(name="Product 1", description="Desc", category=category)
    await Product.create(name="Product 2", description="Desc", category=category)

    service = ProductsService()
    products = await service.list_available_products()
    assert len(products) == 2


async def test_service_get_product_by_id_success(company_factory, category_payload):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Category",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )
    product = await Product.create(name="Test Product", description="Desc", category=category)

    service = ProductsService()
    found = await service.get_product_by_id(product.id)
    assert found.id == product.id
    assert found.name == "Test Product"


async def test_service_get_product_by_id_not_found():
    service = ProductsService()
    with pytest.raises(ProductNotFoundError):
        await service.get_product_by_id(99999)


async def test_service_create_product_success(company_factory, category_payload):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Category",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )

    service = ProductsService()
    payload = ProductRequest(name="New Product", description="Description", category_id=category.id)
    product = await service.create_product(payload=payload)

    assert product.name == "New Product"
    assert product.category_id == category.id
    assert isinstance(product.id, int)


async def test_service_update_product_success(company_factory, category_payload):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Category",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )
    product = await Product.create(name="Original", description="Original", category=category)

    service = ProductsService()
    payload = ProductPatch(name="Updated", description="Updated")
    updated = await service.update_product(product.id, payload)

    assert updated.name == "Updated"
    assert updated.description == "Updated"


async def test_service_update_product_not_found():
    service = ProductsService()
    payload = ProductPatch(name="Updated")
    with pytest.raises(ProductNotFoundError):
        await service.update_product(99999, payload)


async def test_service_delete_product_success(company_factory, category_payload):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Category",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )
    product = await Product.create(name="Delete Me", description="Desc", category=category)

    service = ProductsService()
    deleted = await service.delete_product(product.id)
    assert deleted is True

    with pytest.raises(ProductNotFoundError):
        await service.get_product_by_id(product.id)


async def test_service_delete_product_not_found():
    service = ProductsService()
    with pytest.raises(ProductNotFoundError):
        await service.delete_product(99999)


async def test_service_get_products_by_category(company_factory, category_payload):
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
    await Product.create(name="Product 1", description="Desc", category=category1)
    await Product.create(name="Product 2", description="Desc", category=category1)
    await Product.create(name="Product 3", description="Desc", category=category2)

    service = ProductsService()
    cat1_products = await service.get_products_by_category(category1.id)
    assert len(cat1_products) == 2
