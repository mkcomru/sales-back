"""Products test fixtures. Override ProductsServiceDep to bypass integration_aware (company_id) requirement."""

from __future__ import annotations

from typing import get_args

import pytest

from src.backend.modules.products.dependencies import ProductsServiceDep
from src.backend.modules.products.service import ProductsService


def _get_products_service_resolver():
    dep = get_args(ProductsServiceDep)[1]
    return dep.dependency


@pytest.fixture(autouse=True)
def override_products_service(fastapi_app):
    """Bypass integration_aware for /products routes that lack company_id in path."""
    resolver = _get_products_service_resolver()

    async def _override():
        return ProductsService()

    fastapi_app.dependency_overrides[resolver] = _override
    yield
    fastapi_app.dependency_overrides.pop(resolver, None)
