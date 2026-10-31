"""Authentication helpers for message routing."""

from fastapi import HTTPException, status

from common.models import ConnectorContext

from src.backend.modules.transport.dependencies import ConnectorsServiceDep
from src.backend.modules.transport.exceptions import ConnectorNotFoundError


async def validate_bearer_token(
    service: ConnectorsServiceDep,
    authorization: str,
) -> ConnectorContext:
    """Validate Bearer token via backend for custom connectors."""
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "malformed_token"},
        )

    raw_key = parts[1].strip()
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "malformed_token"},
        )

    try:
        return await service.validate_api_key(raw_key)
    except ConnectorNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "invalid_token"},
        ) from exc


async def get_managed_connector(
    service: ConnectorsServiceDep,
    connector_id: str,
) -> ConnectorContext:
    """Get ConnectorContext by ID for managed connectors."""
    try:
        connector = await service.get_by_connector_id(connector_id)
        if not connector:
            raise ConnectorNotFoundError()
        if not connector.enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "connector_disabled"},
            )
        return await service.get_context_by_connector_id(connector_id)
    except ConnectorNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "connector_disabled"},
        ) from exc
