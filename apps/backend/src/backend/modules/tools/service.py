from common.tools import CAPABILITY_GATED_GROUPS, LEGACY_TOOLS, TOOL_CATALOG, TOOL_DESCRIPTIONS_BY_NAME

from src.backend.modules.integrations.repository import IntegrationRepository
from src.backend.modules.tools.schemas import ToolGroupResponse, ToolItemResponse


class ToolsService:
    def __init__(self) -> None:
        self._integration_repo = IntegrationRepository()

    async def list_available(self, company_id: int) -> list[ToolGroupResponse]:
        active_capabilities = await self._get_active_capabilities(company_id)
        result: list[ToolGroupResponse] = []
        for group, tools in TOOL_CATALOG.items():
            if not self._is_group_visible(group, active_capabilities):
                continue
            active_tools = [t for t in tools if t not in LEGACY_TOOLS]
            if not active_tools:
                continue
            items = [
                ToolItemResponse(name=t.value, description=TOOL_DESCRIPTIONS_BY_NAME[t.value]) for t in active_tools
            ]
            result.append(ToolGroupResponse(group=group.value, tools=items))
        return result

    async def _get_active_capabilities(self, company_id: int) -> set[str]:
        integrations = await self._integration_repo.get_for_company(company_id)
        caps: set[str] = set()
        for integration in integrations:
            caps.update(integration.enabled_capabilities)
        return caps

    @staticmethod
    def _is_group_visible(group: str, active_capabilities: set[str]) -> bool:
        required = CAPABILITY_GATED_GROUPS.get(group)
        if required is None:
            return True
        return required in active_capabilities
