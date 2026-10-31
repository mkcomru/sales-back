"""Internal API endpoints for Backend → Sales Agent communication."""

import secrets

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel

from common import SalesAgentSettings
from common.models import InternalInboundRequest, TaskAutoAction, TaskExecutionRequest

from src.sales_agent.api.internal_utils import map_to_incoming_message
from src.sales_agent.handlers.dependencies import get_debouncer
from src.sales_agent.services.backend_client import BackendClient
from src.sales_agent.services.debounce import DebounceManager
from src.sales_agent.services.transcription import OpenAITranscriptionService, TranscriptionError

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/internal/messages", tags=["internal"])
tasks_router = APIRouter(prefix="/api/v1/internal/tasks", tags=["internal-tasks"])
debounce_router = APIRouter(prefix="/api/v1/internal/debounce", tags=["internal-debounce"])
transcription_router = APIRouter(prefix="/api/v1/internal/transcription", tags=["internal-transcription"])


def _require_service_api_key(request: Request) -> None:
    settings: SalesAgentSettings = request.app.state.settings
    service_key = settings.service.api_key
    if not service_key or not service_key.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service API key not configured",
        )
    header = settings.service.resolved_header()
    provided = request.headers.get(header)
    if not provided or not secrets.compare_digest(provided, service_key.get_secret_value()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service API key",
        )


@router.post(
    "/inbound",
    status_code=status.HTTP_202_ACCEPTED,
)
async def internal_inbound_message(
    request: InternalInboundRequest,
    debouncer: DebounceManager = Depends(get_debouncer),
) -> dict[str, str]:
    """Receive internal inbound message from Backend.

    This endpoint is called by Backend after it validates the connector.
    """
    message = map_to_incoming_message(request)
    await debouncer.add_message(message)

    log.info(
        "internal.inbound.processed",
        connector_id=request.context.connector_id,
        company_id=request.context.company_id,
        conversation_id=request.envelope.conversation_id,
    )

    return {"status": "accepted"}


@tasks_router.post("/execute", status_code=status.HTTP_202_ACCEPTED)
async def execute_task(
    request: TaskExecutionRequest,
    app: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    """Accept a scheduled task for async execution.

    Returns 202 immediately; LLM generation + outbound delivery happen
    in the background, matching the fire-and-forget inbound pattern.
    """
    match request.auto_action:
        case TaskAutoAction.SEND_FOLLOWUP_MESSAGE:
            background_tasks.add_task(_process_reminder_task, app.app, request)
        case _:
            raise HTTPException(400, f"Unknown auto_action: {request.auto_action}")

    return {"status": "accepted", "task_id": request.task_id}


_TOOLS_BLOCKED_IN_REMINDERS = frozenset({"schedule_reminder"})


async def _process_reminder_task(app, request: TaskExecutionRequest) -> None:
    from src.sales_agent.agents.prompts.reminder_formatter import format_reminder_prompt
    from src.sales_agent.services.message_processor import process_reminder

    try:
        instructions = format_reminder_prompt(
            title=request.title,
            description=request.description,
        )
        agent_ctx = request.agent_context.model_dump(mode="json")
        agent_ctx["enabled_tools"] = [
            t for t in (agent_ctx.get("enabled_tools") or []) if t not in _TOOLS_BLOCKED_IN_REMINDERS
        ]
        await process_reminder(
            app=app,
            context=request.context,
            thread_id=request.thread_id,
            order_id=request.order_id,
            agent_context=agent_ctx,
            reminder_instructions=instructions,
        )
    except Exception:
        log.exception(
            "task.background.failed",
            task_id=request.task_id,
            thread_id=request.thread_id,
        )


class DebounceCancelRequest(BaseModel):
    thread_id: str


class TranscriptionRequest(BaseModel):
    artifact_id: str
    mime: str | None = None


class TranscriptionResponse(BaseModel):
    text: str


@transcription_router.post(
    "/transcribe",
    response_model=TranscriptionResponse,
    dependencies=[Depends(_require_service_api_key)],
)
async def transcribe_artifact(request: Request, body: TranscriptionRequest) -> TranscriptionResponse:
    settings: SalesAgentSettings = request.app.state.settings
    backend_client: BackendClient = request.app.state.backend_client
    audio_bytes = await backend_client.download_artifact(body.artifact_id)
    stt = OpenAITranscriptionService(settings)
    try:
        text = await stt.transcribe(
            audio_bytes=audio_bytes,
            filename=body.artifact_id.split("/")[-1],
            mime=body.mime,
        )
    except TranscriptionError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
    return TranscriptionResponse(text=text)


@debounce_router.post(
    "/cancel",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(_require_service_api_key)],
)
async def debounce_cancel(
    body: DebounceCancelRequest,
    debouncer: DebounceManager = Depends(get_debouncer),
) -> dict[str, str | bool]:
    """Cancel debounce bucket for thread. Called by Backend when assistant is deactivated."""
    cancelled = await debouncer.cancel_bucket_for_thread(body.thread_id)
    return {"status": "ok", "cancelled": cancelled}
