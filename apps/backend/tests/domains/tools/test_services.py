"""Service tests for tools."""

from common.tools import TOOL_CATALOG

from src.backend.modules.tools.schemas import ToolGroupResponse, ToolItemResponse
from src.backend.modules.tools.service import ToolsService


async def test_list_available_returns_catalog():
    service = ToolsService()
    result = await service.list_available(company_id=1)
    assert len(result) <= len(TOOL_CATALOG)
    assert len(result) > 0
    for item in result:
        assert isinstance(item, ToolGroupResponse)
        assert item.group
        assert isinstance(item.tools, list)
        for tool in item.tools:
            assert isinstance(tool, ToolItemResponse)
            assert tool.name
            assert tool.description
