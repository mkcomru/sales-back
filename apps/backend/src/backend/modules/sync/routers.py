"""API endpoints for sync batch ingestion."""

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from common.contracts.sync import SyncBatchRequest, SyncHeartbeatRequest, SyncStatusUpdate

from src.backend.modules.core.dependencies import require_service_api_key
from src.backend.modules.sync.dependencies import SyncServiceDep
from src.backend.modules.sync.schemas import BatchProcessResponse, CursorResponse

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/internal/sync", tags=["sync:internal"])


@router.post(
    "/batch",
    status_code=status.HTTP_200_OK,
    response_model=BatchProcessResponse,
    dependencies=[Depends(require_service_api_key)],
    summary="Ingest sync batch",
    description="Process a batch of historical messages from connector. Returns 409 if batch already processed.",
)
async def ingest_batch(
    request: SyncBatchRequest,
    sync_service: SyncServiceDep,
) -> BatchProcessResponse:
    """Ingest a batch of messages from connector.

    Checks batch_id for idempotency. If batch already processed, returns duplicate status.
    """
    try:
        result = await sync_service.process_batch(request)
        if result["status"] == "duplicate":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Batch {request.batch_id} already processed",
            )
        return BatchProcessResponse(**result)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("sync.batch.ingest_failed", batch_id=request.batch_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process batch",
        ) from exc


@router.post(
    "/status",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_service_api_key)],
    summary="Update sync status",
    description="Update sync status, progress, and cursor for connector.",
)
async def update_status(
    request: SyncStatusUpdate,
    sync_service: SyncServiceDep,
) -> dict[str, str]:
    """Update sync status and progress."""
    try:
        await sync_service.update_status(request)
        return {"status": "updated"}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("sync.status.update_failed", connector_id=request.connector_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update status",
        ) from exc


@router.post(
    "/heartbeat",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_service_api_key)],
    summary="Send heartbeat",
    description=(
        "Send heartbeat signal to indicate sync is alive. Backend marks sync as FAILED if no heartbeat > 2 minutes."
    ),
)
async def send_heartbeat(
    request: SyncHeartbeatRequest,
    sync_service: SyncServiceDep,
) -> dict[str, str]:
    """Process heartbeat signal from connector."""
    try:
        await sync_service.process_heartbeat(request)
        return {"status": "received"}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("sync.heartbeat.process_failed", connector_id=request.connector_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process heartbeat",
        ) from exc


@router.get(
    "/cursor/{connector_id}",
    response_model=CursorResponse,
    dependencies=[Depends(require_service_api_key)],
    summary="Get sync cursor",
    description="Get last cursor for connector to resume sync after interruption. Returns None if not found.",
)
async def get_cursor(
    connector_id: str,
    sync_service: SyncServiceDep,
) -> CursorResponse:
    """Get last cursor for connector."""
    cursor = await sync_service.get_cursor(connector_id)
    return CursorResponse(cursor=cursor)
