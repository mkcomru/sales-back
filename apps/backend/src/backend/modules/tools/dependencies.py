from typing import Annotated

from fastapi import Depends

from src.backend.modules.tools.service import ToolsService


def _tools_service() -> ToolsService:
    return ToolsService()


ToolsServiceDep = Annotated[ToolsService, Depends(_tools_service)]
