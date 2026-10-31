"""Message routing endpoints for Backend as central router."""

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from common.models import (
    ConnectorContext,
    InboundEnvelope,
    InternalInboundRequest,
    MessageRole,
    OutboundDeliveryRequest,
)

from src.backend.modules.billing.dependencies import BillingServiceDep
from src.backend.modules.billing.models import BillingStatus
from src.backend.modules.chat.dependencies import ChatServiceDep, WebSocketManagerDep
from src.backend.modules.chat.models import AssistantMode, ChatMessageRole, ChatMessageStatus, Thread
from src.backend.modules.core.dependencies import SalesAgentClientDep, SettingsDep, require_service_api_key
from src.backend.modules.messages.auth import get_managed_connector, validate_bearer_token
from src.backend.modules.messages.dependencies import AgentContextAssemblerDep, OutboundServiceDep
from src.backend.modules.messages.sales_agent_client import SalesAgentClientError
from src.backend.modules.messages.transport_client import TransportClientError
from src.backend.modules.orders.dependencies import OrderServiceDep
from src.backend.modules.pings.dependencies import PingServiceDep
from src.backend.modules.transport.dependencies import ConnectorsServiceDep
from src.backend.modules.transport.exceptions import ConnectorNotFoundError
from src.backend.modules.transport.models import SyncStatus

ROLE_MAP = {
    MessageRole.USER: ChatMessageRole.USER,
    MessageRole.MANAGER: ChatMessageRole.MANAGER,
}

log = structlog.get_logger(__name__)


router = APIRouter(prefix="/messages", tags=["messages"])
internal_router = APIRouter(prefix="/internal/messages", tags=["messages:internal"])


@router.post(
    "/inbound",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        401: {"description": "Missing or malformed token"},
        403: {"description": "Invalid or disabled connector"},
        503: {"description": "Service unavailable"},
    },
)
async def inbound_message(
    envelope: InboundEnvelope,
    request: Request,
    service: ConnectorsServiceDep,
    settings: SettingsDep,
    sales_agent_client: SalesAgentClientDep,
    chat_service: ChatServiceDep,
    billing_service: BillingServiceDep,
    order_service: OrderServiceDep,
    context_assembler: AgentContextAssemblerDep,
    ws_manager: WebSocketManagerDep,
    ping_service: PingServiceDep,
    authorization: str | None = Header(default=None),
    x_service_key: str | None = Header(default=None, alias="X-Service-Key"),
    x_connector_id: str | None = Header(default=None, alias="X-Connector-Id"),
) -> dict[str, str]:
    """Receive normalized inbound message from connectors.

    Backend as intelligent router:
    - ALWAYS saves user message to DB immediately
    - Checks assistant_mode, is_historical, role before forwarding
    - Only forwards to Sales Agent when assistant is active
    """
    context: ConnectorContext

    if x_service_key and x_connector_id:
        expected_key = settings.service.api_key
        if not expected_key or x_service_key != expected_key.get_secret_value():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "missing_token"},
            )
        context = await get_managed_connector(service, x_connector_id)

    elif authorization:
        context = await validate_bearer_token(service, authorization)

    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "missing_token"},
        )

    # 1. Get or create thread with normalized metadata
    meta = {
        "name": envelope.sender_name,
        "username": envelope.sender_username,
        "phone": envelope.sender_phone,
    }
    thread, created = await chat_service.get_or_create_thread(
        user_id=envelope.user_id,
        company_id=context.company_id,
        channel_type=context.channel_type,
        connector_id=context.connector_id,
        conversation_id=envelope.conversation_id,
        meta={k: v for k, v in meta.items() if v},
        is_historical=envelope.is_historical,
    )

    # 2. ALWAYS save message (using standardized role field)
    db_role = ROLE_MAP[envelope.role]
    artifact_ids = envelope.artifact_ids or []

    message = await chat_service.create_message(
        thread_id=thread.thread_id,
        role=db_role,
        content=envelope.text or "",
        status=ChatMessageStatus.SENT,
        delivered_at=datetime.fromtimestamp(envelope.ts, tz=UTC),
        provider_message_id=envelope.message_id,
        is_historical=envelope.is_historical,
        artifact_ids=artifact_ids,
        message_type=None,
    )

    # Add backend message_id to envelope.extra for Sales-Agent
    if envelope.extra is None:
        envelope.extra = {}
    envelope.extra["backend_message_id"] = message.message_id

    log.info(
        "ingress.message.saved",
        thread_id=thread.thread_id,
        role=envelope.role.value,
        connector_id=context.connector_id,
        company_id=context.company_id,
        is_historical=envelope.is_historical,
    )

    # Update last_customer_message_at and cancel pending pings on customer reply
    if envelope.role == MessageRole.USER and not envelope.is_historical:
        await Thread.filter(id=thread.id).update(last_customer_message_at=datetime.now(UTC))
        if thread.active_order_id:
            await ping_service.cancel_pending_pings(order_id=thread.active_order_id)

    # Broadcast inbound message to WebSocket subscribers
    if not envelope.is_historical:
        if created:
            await ws_manager.notify_thread_created(
                context.company_id,
                thread.thread_id,
                channel_type=context.channel_type,
                state=thread.state.value,
            )
        await ws_manager.notify_message(
            context.company_id,
            thread.thread_id,
            message,
            thread_state=thread.state.value,
        )

    # 3. ROUTING DECISION (connector-agnostic, based on schema fields)

    # Historical messages: save only, no AI processing
    if envelope.is_historical:
        log.info(
            "ingress.routing.skipped",
            reason="historical",
            thread_id=thread.thread_id,
            assistant_mode=thread.assistant_mode.value,
        )
        return {"status": "accepted"}

    # Manager messages: force INACTIVE, no AI processing
    if envelope.role == MessageRole.MANAGER:
        await chat_service.control_thread_mode(
            thread_id=thread.thread_id,
            mode=AssistantMode.INACTIVE,
            reason="Manager message received",
        )
        log.info("ingress.routing.skipped", reason="manager_message", thread_id=thread.thread_id)
        return {"status": "accepted"}

    # Assistant inactive: save only
    if thread.assistant_mode == AssistantMode.INACTIVE:
        log.info("ingress.routing.skipped", reason="assistant_inactive", thread_id=thread.thread_id)
        return {"status": "accepted"}

    # Billing check: charge for new orders, check status and balance for existing orders
    order = await order_service.ensure_active_order(thread)

    # Charge if order hasn't been charged yet (new order or order without charge)
    if order.charged_at is None:
        charge_result = await billing_service.charge_for_order(
            company_id=context.company_id,
            order_id=order.id,
            channel_type=context.channel_type,
            conversation_id=envelope.conversation_id,
        )
        if not charge_result.success:
            log.info(
                "ingress.routing.skipped",
                reason="billing_hold",
                thread_id=thread.thread_id,
                order_id=order.id,
                company_id=context.company_id,
                balance=charge_result.new_balance,
            )
            return {"status": "accepted"}
    else:
        # Order already charged - check billing status
        if order.billing_status == BillingStatus.BILLING_HOLD:
            log.info(
                "ingress.routing.skipped",
                reason="billing_hold",
                thread_id=thread.thread_id,
                order_id=order.id,
                company_id=context.company_id,
            )
            return {"status": "accepted"}
        # AICODE-NOTE: Check current balance for existing orders - block if balance is 0
        # This ensures zero balance blocks all new messages, even for grandfathered orders
        balance, balance_warning = await billing_service.get_balance(context.company_id)
        if balance_warning:
            log.info(
                "ingress.routing.skipped",
                reason="billing_hold_zero_balance",
                thread_id=thread.thread_id,
                order_id=order.id,
                company_id=context.company_id,
                balance=balance,
            )
            return {"status": "accepted"}

    # AICODE-NOTE: Check connector sync status - AI paused during sync
    connector = await service.get_by_connector_id(context.connector_id)
    if connector:
        if connector.sync_status in (SyncStatus.INITIAL, SyncStatus.BACKFILL, SyncStatus.CATCHUP):
            log.info(
                "ingress.routing.skipped",
                reason="sync_in_progress",
                thread_id=thread.thread_id,
                connector_id=context.connector_id,
                sync_status=connector.sync_status.value,
                message="AI paused due to sync in progress",
            )
            return {"status": "accepted"}

    # 4. Forward to Sales Agent (regular user message, assistant active, sync not in progress)
    # Order already fetched above for billing check

    # AICODE-NOTE: Prepare order stage info for Sales Agent context
    order_stage_data = None
    if order.stage:
        await order.fetch_related("stage")
        order_stage_data = {
            "id": order.stage.id,
            "name": order.stage.name,
            "position": order.stage.position,
            "color": order.stage.color,
        }

    # Get qualification workflow and examples from prompt_addon or company fallback
    qualification_workflow, qualification_examples = await chat_service.get_qualification_config(thread)

    agent_ctx = await context_assembler.build(
        company_id=context.company_id,
        user_id=envelope.user_id,
        thread_id=thread.thread_id,
        conversation_id=envelope.conversation_id,
        order_id=order.id,
    )

    internal_request = InternalInboundRequest(
        envelope=envelope,
        context=context,
        thread_id=thread.thread_id,
        order_id=order.id,
        agent_context=agent_ctx,
        order_stage=order_stage_data,
        qualification_workflow=qualification_workflow,
        qualification_examples=qualification_examples,
    )

    try:
        await sales_agent_client.forward_inbound(internal_request)
    except SalesAgentClientError as exc:
        log.warning("ingress.forward.failed", connector_id=context.connector_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "service_unavailable"},
        ) from exc

    log.info(
        "ingress.routing.forwarded",
        thread_id=thread.thread_id,
        connector_id=context.connector_id,
        company_id=context.company_id,
        conversation_id=envelope.conversation_id,
    )

    return {"status": "accepted"}


@internal_router.post(
    "/outbound",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_service_api_key)],
    responses={
        400: {"description": "Invalid request"},
        404: {"description": "Connector not found"},
    },
)
async def outbound_message(
    request: OutboundDeliveryRequest,
    service: ConnectorsServiceDep,
    outbound: OutboundServiceDep,
    chat_service: ChatServiceDep,
    ws_manager: WebSocketManagerDep,
) -> dict[str, str]:
    """Receive outbound message from Sales Agent and route to transport.

    Backend saves assistant messages before routing to transport.
    Checks if assistant is still active before forwarding to connector.
    If assistant is inactive, message is saved but not forwarded.
    """
    try:
        connector = await service.get_by_connector_id(request.connector_id)
        if not connector:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "connector_not_found"},
            )
    except ConnectorNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "connector_not_found"},
        ) from exc

    # 1. Save each assistant reply using thread_id from request
    thread_id = request.thread_id
    saved_replies = []
    for reply_text in request.replies:
        msg = await chat_service.create_message(
            thread_id=thread_id,
            role=ChatMessageRole.ASSISTANT,
            content=reply_text,
            status=ChatMessageStatus.SENT,
            delivered_at=datetime.now(UTC),
            metadata=request.metadata or {},
        )
        saved_replies.append(msg)

    log.info(
        "egress.assistant.saved",
        thread_id=thread_id,
        replies_count=len(request.replies),
        connector_id=request.connector_id,
    )

    # 2. Check if assistant is still active before forwarding
    thread = await chat_service.get_thread_by_id(thread_id)

    company_id: int | None = getattr(connector, "company_id", None)
    if company_id is not None:
        thread_state = thread.state.value if thread else "active"
        for msg in saved_replies:
            await ws_manager.notify_message(company_id, thread_id, msg, thread_state=thread_state)

    if thread is None:
        log.warning(
            "egress.routing.skipped",
            reason="thread_not_found",
            thread_id=thread_id,
            connector_id=request.connector_id,
        )
        return {"status": "accepted"}

    if thread.assistant_mode == AssistantMode.INACTIVE and not request.handoff:
        log.info(
            "egress.routing.skipped",
            reason="assistant_inactive",
            thread_id=thread_id,
            connector_id=request.connector_id,
        )
        return {"status": "accepted"}

    # 3. Enrich + deliver via OutboundService
    try:
        await outbound.deliver_to_thread(
            connector=connector,
            thread=thread,
            replies=request.replies,
            correlation_id=request.correlation_id,
            metadata=request.metadata,
            stage_id=request.stage_id,
            handoff=request.handoff,
        )
    except TransportClientError as exc:
        log.error(
            "egress.routing.failed",
            connector_id=request.connector_id,
            connector_type=connector.type.value,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "transport_delivery_failed"},
        ) from exc

    return {"status": "accepted"}
