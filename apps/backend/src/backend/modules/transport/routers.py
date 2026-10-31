from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from common.transport.registry import CONNECTOR_TYPE_CATALOG

from src.backend.modules.auth.dependencies import CurrentUserDep
from src.backend.modules.core.dependencies import require_service_api_key
from src.backend.modules.transport.dependencies import ConnectorAdminDep, ConnectorsServiceDep
from src.backend.modules.transport.exceptions import ConnectorNotFoundError
from src.backend.modules.transport.schemas import (
    ConnectorApiKeyListItem,
    ConnectorApiKeyResponse,
    ConnectorCatalogListResponse,
    ConnectorListResponse,
    ConnectorResponse,
    ConnectorTypeCatalogResponse,
    ConnectorUpdateRequest,
    SyncJobResponse,
    SyncStatusEnum,
    SyncStatusResponse,
    SyncTypeEnum,
)

router = APIRouter()
connectors_router = APIRouter(prefix="/transport/connectors", tags=["transport-connectors"])
catalog_router = APIRouter(prefix="/transport/catalog", tags=["transport-catalog"])


@connectors_router.get(
    "",
    response_model=ConnectorListResponse,
    dependencies=[Depends(require_service_api_key)],
)
async def list_connectors(
    service: ConnectorsServiceDep,
    type: str | None = None,
    enabled: bool | None = None,
) -> ConnectorListResponse:
    connectors = await service.list_connectors_decrypted(type_filter=type, enabled_filter=enabled)
    return ConnectorListResponse(connectors=connectors)


@connectors_router.get(
    "/{connector_db_id}",
    response_model=ConnectorResponse,
    dependencies=[Depends(require_service_api_key)],
)
async def get_connector(
    connector_db_id: int,
    service: ConnectorsServiceDep,
) -> ConnectorResponse:
    return await service.get_connector_decrypted(connector_db_id)


@connectors_router.patch(
    "/{connector_db_id}",
    response_model=ConnectorResponse,
)
async def update_connector(
    connector_db_id: int,
    request: ConnectorUpdateRequest,
    service: ConnectorsServiceDep,
    _connector: ConnectorAdminDep,  # noqa: ARG001
) -> ConnectorResponse:
    return await service.update_connector(connector_db_id, request)


@connectors_router.delete(
    "/{connector_db_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_connector(
    connector_db_id: int,
    service: ConnectorsServiceDep,
    _connector: ConnectorAdminDep,  # noqa: ARG001
) -> None:
    await service.delete_connector(connector_db_id)


@connectors_router.post(
    "/{connector_db_id}/api-keys",
    status_code=status.HTTP_201_CREATED,
    response_model=ConnectorApiKeyResponse,
)
async def create_api_key(
    connector_db_id: int,
    service: ConnectorsServiceDep,
    _connector: ConnectorAdminDep,  # noqa: ARG001
) -> ConnectorApiKeyResponse:
    return await service.create_api_key(connector_db_id)


@connectors_router.get(
    "/{connector_db_id}/api-keys",
    response_model=list[ConnectorApiKeyListItem],
)
async def list_api_keys(
    connector_db_id: int,
    service: ConnectorsServiceDep,
    _connector: ConnectorAdminDep,  # noqa: ARG001
) -> list[ConnectorApiKeyListItem]:
    return await service.list_api_keys(connector_db_id)


@connectors_router.delete(
    "/{connector_db_id}/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_api_key(
    connector_db_id: int,  # noqa: ARG001
    key_id: int,
    service: ConnectorsServiceDep,
    _connector: ConnectorAdminDep,  # noqa: ARG001
) -> None:
    await service.delete_api_key(key_id)


# Sync endpoints - use connector_id (public identifier) instead of connector_db_id
@connectors_router.post(
    "/{connector_id}/sync/start",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SyncJobResponse,
    dependencies=[Depends(require_service_api_key)],
    summary="Start history synchronization",
    description="Start initial, backfill, or catchup sync for a connector",
)
async def start_sync(
    connector_id: str,
    connectors_service: ConnectorsServiceDep,
    sync_type: SyncTypeEnum = Query(..., description="Type of sync: initial, backfill, or catchup"),
    since: datetime | None = Query(None, description="Start date for catchup sync (required for catchup type)"),
) -> SyncJobResponse:
    """Start history synchronization for a connector.

    Args:
        connector_id: Public connector identifier
        sync_type: Type of synchronization (initial, backfill, catchup)
        since: Start date for catchup sync (required if sync_type=catchup)

    Returns:
        SyncJobResponse with job details

    Raises:
        HTTPException: If connector not found, invalid parameters, or sync already running
    """
    if sync_type == SyncTypeEnum.CATCHUP and not since:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parameter 'since' is required for catchup sync",
        )

    try:
        await connectors_service.start_sync(
            connector_id=connector_id,
            sync_type=sync_type.value,
            since=since,
        )

        # Map sync_type to status
        status_map = {
            SyncTypeEnum.INITIAL: SyncStatusEnum.INITIAL,
            SyncTypeEnum.BACKFILL: SyncStatusEnum.BACKFILL,
            SyncTypeEnum.CATCHUP: SyncStatusEnum.CATCHUP,
        }

        return SyncJobResponse(
            connector_id=connector_id,
            sync_type=sync_type,
            status=status_map[sync_type],
            message="Sync job started",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@connectors_router.post(
    "/{connector_id}/sync/more-chats",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=dict[str, str],
    dependencies=[Depends(require_service_api_key)],
    summary="Load more chats for connector",
    description="Continue loading chats that weren't loaded during initial sync",
)
async def sync_more_chats(
    connector_id: str,
    connectors_service: ConnectorsServiceDep,
) -> dict[str, str]:
    """Load additional chats for a connector.

    During initial sync, only a limited number of chats are loaded (initial_sync_dialogs_limit).
    This endpoint continues loading more chats that weren't included in the initial sync.

    For each new chat:
    - Parses initial_sync_messages_limit messages
    - Uploads media to S3 with artifact_ids
    - Creates Thread and ChatMessage records

    Args:
        connector_id: Public connector identifier

    Returns:
        Status message

    Raises:
        HTTPException: If connector not found or sync fails
    """
    try:
        await connectors_service.sync_more_chats(connector_id=connector_id)

        return {
            "status": "sync_triggered",
            "connector_id": connector_id,
            "message": "Loading more chats. This may take a few minutes.",
        }
    except ConnectorNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connector not found",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@connectors_router.get(
    "/{connector_id}/sync/status",
    response_model=SyncStatusResponse,
    dependencies=[Depends(require_service_api_key)],
    summary="Get synchronization status",
    description="Get current sync status and progress for a connector",
)
async def get_sync_status(
    connector_id: str,
    connectors_service: ConnectorsServiceDep,
) -> SyncStatusResponse:
    """Get current synchronization status for a connector.

    Args:
        connector_id: Public connector identifier

    Returns:
        SyncStatusResponse with current status and progress

    Raises:
        HTTPException: If connector not found
    """
    connector = await connectors_service.get_by_connector_id(connector_id)
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector {connector_id} not found",
        )

    return SyncStatusResponse(
        connector_id=connector_id,
        status=SyncStatusEnum(connector.sync_status.value),
        started_at=connector.sync_started_at,
        completed_at=connector.sync_completed_at,
        progress=dict(connector.sync_progress or {}),
    )


@connectors_router.post(
    "/{connector_id}/sync/cancel",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_service_api_key)],
    summary="Cancel synchronization",
    description="Cancel active sync job for a connector",
)
async def cancel_sync(
    connector_id: str,
    connectors_service: ConnectorsServiceDep,
) -> dict[str, str]:
    """Cancel active synchronization job.

    Args:
        connector_id: Public connector identifier

    Returns:
        Success message

    Raises:
        HTTPException: If connector not found or no active sync job
    """
    try:
        await connectors_service.cancel_sync(connector_id)
        return {"status": "cancelled", "message": f"Sync job for connector {connector_id} has been cancelled"}
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@catalog_router.get(
    "",
    response_model=ConnectorCatalogListResponse,
    summary="Get connector type catalog",
    description="Returns all registered connector types with their capabilities",
)
async def get_connector_catalog(_user: CurrentUserDep) -> ConnectorCatalogListResponse:
    catalog = [ConnectorTypeCatalogResponse.from_entry(entry) for entry in CONNECTOR_TYPE_CATALOG.values()]
    return ConnectorCatalogListResponse(catalog=catalog)


router.include_router(connectors_router)
router.include_router(catalog_router)
