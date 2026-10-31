"""Core dependencies for FastAPI.

Contains common dependencies like settings and service API key authentication.
"""

import secrets
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, Request, status

from src.backend.modules.core.settings import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_sales_agent_client(settings: SettingsDep):
    from src.backend.modules.messages.sales_agent_client import SalesAgentClient

    return SalesAgentClient(settings)


if TYPE_CHECKING:
    from src.backend.modules.messages.sales_agent_client import SalesAgentClient

SalesAgentClientDep = Annotated["SalesAgentClient", Depends(get_sales_agent_client)]


def require_service_api_key(request: Request) -> None:
    """Require valid service API key in request headers."""
    cfg = get_settings()
    service_key = cfg.service.api_key
    if service_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service API key not configured",
        )

    header_name = cfg.service.resolved_header()
    provided = request.headers.get(header_name)
    if not provided or not secrets.compare_digest(provided, service_key.get_secret_value()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service API key",
        )
