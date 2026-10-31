from __future__ import annotations

from common.integrations import Capability

from src.backend.modules.integrations.models import Integration


class IntegrationRepository:
    async def get_for_company(self, company_id: int) -> list[Integration]:
        return await Integration.filter(company_id=company_id, enabled=True)

    async def get_by_capability(self, company_id: int, capability: Capability) -> Integration | None:
        integrations = await self.get_for_company(company_id)
        for integration in integrations:
            if capability.value in integration.enabled_capabilities:
                return integration
        return None

    async def get_by_id(self, integration_id: int) -> Integration | None:
        return await Integration.get_or_none(id=integration_id)

    async def get_by_company_and_provider(self, company_id: int, provider_type: str) -> Integration | None:
        return await Integration.get_or_none(company_id=company_id, provider_type=provider_type)
