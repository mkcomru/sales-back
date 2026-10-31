from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status

from src.backend.modules.auth.dependencies import (
    CurrentUserDep,
    require_company_role,
)
from src.backend.modules.transport.models import Connector
from src.backend.modules.transport.repository import ConnectorsRepository
from src.backend.modules.transport.service import ConnectorsService
from src.backend.modules.users.models import UserRole


@lru_cache
def connectors() -> ConnectorsService:
    return ConnectorsService()


ConnectorsServiceDep = Annotated[ConnectorsService, Depends(connectors)]


async def require_connector_admin(
    connector_db_id: int,
    current_user: CurrentUserDep,
) -> Connector:
    """Require ADMIN+ access to the connector's company."""
    connector = await ConnectorsRepository().get_by_id(connector_db_id)
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found",
        )
    await require_company_role(
        company_id=connector.company.id,
        current_user=current_user,
        required_role=UserRole.ADMIN,
    )
    return connector


ConnectorAdminDep = Annotated[Connector, Depends(require_connector_admin)]
