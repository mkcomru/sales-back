"""YClients override for ProductsService.

Replaces the product listing used by AgentContext with YClients booking services.
The AI agent sees YClients services as "products" and can search them via search_product.
"""

from __future__ import annotations

import structlog

from src.backend.modules.integrations.models import Integration
from src.backend.modules.products.service import ProductsService

log = structlog.get_logger(__name__)


class YClientsProductsService(ProductsService):
    def __init__(self, integration: Integration | None = None) -> None:
        super().__init__(integration=integration)
        self._integration = integration

    async def list_for_agent(self, category_ids: list[int]) -> list[dict]:
        if not self._integration:
            return await super().list_for_agent(category_ids)

        from src.backend.modules.integrations.service import IntegrationService

        svc = IntegrationService()
        async with svc.build_client(self._integration) as client:
            from src.backend.integrations.yclients.client import YClientsClient

            assert isinstance(client, YClientsClient)
            data = await client.get_services()

        categories_map = {c.id: c.title for c in data.category}

        return [
            {
                "id": s.id,
                "name": s.title,
                "description": _build_description(s, categories_map),
                "category_id": s.category_id,
                "attributes": {
                    "price_min": s.price_min,
                    "price_max": s.price_max,
                    "duration_seconds": s.seance_length,
                    "source": "yclients",
                },
            }
            for s in data.services
        ]


def _build_description(service, categories_map: dict[int, str]) -> str:
    parts: list[str] = []
    cat = categories_map.get(service.category_id)
    if cat:
        parts.append(cat)
    if service.price_min and service.price_max:
        if service.price_min == service.price_max:
            parts.append(f"{int(service.price_min)}₽")
        else:
            parts.append(f"{int(service.price_min)}–{int(service.price_max)}₽")
    if service.seance_length:
        parts.append(f"{service.seance_length // 60} мин")
    return ", ".join(parts)
