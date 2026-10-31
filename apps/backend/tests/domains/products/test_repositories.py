"""Repository tests for products."""

from src.backend.modules.categories.models import Category
from src.backend.modules.products.models import Product
from src.backend.modules.products.repository import ProductsRepository


async def test_repository_list_all_empty():
    repo = ProductsRepository()
    products = await repo.list_all()
    assert products == []


async def test_repository_list_all_with_data(company_factory, category_payload):
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

    repo = ProductsRepository()
    products = await repo.list_all()
    assert len(products) == 2
    names = {p.name for p in products}
    assert "Product 1" in names
    assert "Product 2" in names


async def test_repository_get_by_id_success(company_factory, category_payload):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Category",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )
    product = await Product.create(name="Test Product", description="Desc", category=category)

    repo = ProductsRepository()
    found = await repo.get_by_id(product.id)
    assert found is not None
    assert found.id == product.id
    assert found.name == "Test Product"


async def test_repository_get_by_id_not_found():
    repo = ProductsRepository()
    found = await repo.get_by_id(99999)
    assert found is None


async def test_repository_get_by_category(company_factory, category_payload):
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

    repo = ProductsRepository()
    cat1_products = await repo.get_by_category(category1.id)
    assert len(cat1_products) == 2
    names = {p.name for p in cat1_products}
    assert "Product 1" in names
    assert "Product 2" in names


async def test_repository_create_success(company_factory, category_payload):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Category",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )

    repo = ProductsRepository()
    product = await repo.create(category_id=category.id, name="New Product", description="Description")
    assert product.id is not None
    assert product.name == "New Product"
    assert product.category_id == category.id


async def test_repository_update_success(company_factory, category_payload):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Category",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )
    product = await Product.create(name="Original", description="Original", category=category)

    repo = ProductsRepository()
    updated = await repo.update(product.id, {"name": "Updated", "description": "Updated"})
    assert updated is not None
    assert updated.name == "Updated"
    assert updated.description == "Updated"


async def test_repository_update_not_found():
    repo = ProductsRepository()
    updated = await repo.update(99999, {"name": "Updated"})
    assert updated is None


async def test_repository_delete_success(company_factory, category_payload):
    company = await company_factory()
    category = await Category.create(
        company=company,
        name="Category",
        description="Desc",
        rules="Rules",
        workflow="Workflow",
    )
    product = await Product.create(name="Delete Product", description="Desc", category=category)

    repo = ProductsRepository()
    deleted = await repo.delete(product.id)
    assert deleted is True
    found = await Product.get_or_none(id=product.id)
    assert found is None


async def test_repository_delete_not_found():
    repo = ProductsRepository()
    deleted = await repo.delete(99999)
    assert deleted is False
