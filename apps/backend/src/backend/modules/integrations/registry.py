"""Service override registry and integration-aware DI resolution.

SERVICE_OVERRIDES maps (provider_type, base_service_class) → override_class.
PROVIDER_CATALOG maps provider_type → ProviderCatalogEntry (frontend metadata).
CLIENT_BUILDERS maps provider_type → factory(credentials, config) → client instance.

Provider packages register at import time via register_override(), register_provider(),
and register_client_builder().
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.backend.modules.integrations.exceptions import IntegrationConflictError
from src.backend.modules.integrations.schemas import ProviderCatalogEntry

SERVICE_OVERRIDES: dict[tuple[str, type], type] = {}
PROVIDER_CATALOG: dict[str, ProviderCatalogEntry] = {}
CLIENT_BUILDERS: dict[str, Callable[[dict[str, Any], dict[str, Any]], Any]] = {}


def register_provider(entry: ProviderCatalogEntry) -> None:
    PROVIDER_CATALOG[entry.provider_type] = entry


def register_override(provider_type: str, base_cls: type, override_cls: type) -> None:
    SERVICE_OVERRIDES[(provider_type, base_cls)] = override_cls


def register_client_builder(
    provider_type: str,
    builder: Callable[[dict[str, Any], dict[str, Any]], Any],
) -> None:
    CLIENT_BUILDERS[provider_type] = builder


async def _resolve[T](base_cls: type[T], company_id: int) -> T:
    from src.backend.modules.integrations.repository import IntegrationRepository

    repo = IntegrationRepository()
    integrations = await repo.get_for_company(company_id)
    matches: list[tuple[Any, type]] = []
    for integration in integrations:
        override = SERVICE_OVERRIDES.get((integration.provider_type, base_cls))
        if override:
            matches.append((integration, override))
    if len(matches) > 1:
        providers = [m[0].provider_type for m in matches]
        raise IntegrationConflictError(f"Multiple integrations override {base_cls.__name__}: {providers}")
    if matches:
        return matches[0][1](integration=matches[0][0])
    return base_cls()


def integration_aware[T](base_cls: type[T]) -> Callable[..., T]:
    """Public routes — company_id from CompanyViewerDep auth."""
    from src.backend.modules.auth.dependencies import CompanyViewerDep

    async def resolver(company_user: CompanyViewerDep) -> T:
        return await _resolve(base_cls, company_user.company_id)

    return resolver


def integration_aware_by_id[T](base_cls: type[T]) -> Callable[..., T]:
    """Internal routes — company_id as path/query parameter."""

    async def resolver(company_id: int) -> T:
        return await _resolve(base_cls, company_id)

    return resolver
