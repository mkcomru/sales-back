from typing import Annotated

from fastapi import Depends

from src.backend.modules.integrations.service import IntegrationService


def _integration_service() -> IntegrationService:
    return IntegrationService()


IntegrationServiceDep = Annotated[IntegrationService, Depends(_integration_service)]
