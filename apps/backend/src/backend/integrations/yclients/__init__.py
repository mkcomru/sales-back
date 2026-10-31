"""YClients integration provider — online booking for beauty salons.

Registers the provider in the catalog and exposes a factory
to build a YClientsClient from a decrypted Integration record.
"""

from __future__ import annotations

from typing import Any

from src.backend.integrations.yclients.client import YClientsClient
from src.backend.integrations.yclients.config import (
    CONFIG_FIELDS,
    CREDENTIAL_FIELDS,
    YClientsConfig,
    YClientsCredentials,
)
from src.backend.integrations.yclients.services.products import YClientsProductsService
from src.backend.modules.integrations.registry import register_client_builder, register_override, register_provider
from src.backend.modules.integrations.schemas import ProviderCatalogEntry
from src.backend.modules.products.service import ProductsService

PROVIDER_TYPE = "yclients"

register_override(PROVIDER_TYPE, ProductsService, YClientsProductsService)

register_provider(
    ProviderCatalogEntry(
        provider_type=PROVIDER_TYPE,
        display_name="YClients",
        description="Онлайн-запись через YClients — услуги, мастера, слоты, бронирование",
        supported_capabilities=["scheduling", "staff"],
        credential_fields=CREDENTIAL_FIELDS,
        config_fields=CONFIG_FIELDS,
    )
)


def build_client(credentials: dict[str, Any], config: dict[str, Any]) -> YClientsClient:
    return YClientsClient(
        credentials=YClientsCredentials.model_validate(credentials),
        config=YClientsConfig.model_validate(config),
    )


register_client_builder(PROVIDER_TYPE, build_client)
