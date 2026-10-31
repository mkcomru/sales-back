from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

import httpx
import structlog
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    HTTPException,
    Path,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from common.models.pagination import PaginatedResponse, PaginationParams

from src.backend.modules.auth.dependencies import (
    CompanyManagerDep,
    CompanyViewerDep,
)
from src.backend.modules.billing.models import BillingStatus
from src.backend.modules.chat.dependencies import (
    ChatServiceDep,
    CustomerManagerDep,
    RedisClientDep,
    ThreadManagerDep,
    WebSocketManagerDep,
)
from src.backend.modules.chat.models import AssistantMode as DBAssistantMode
from src.backend.modules.chat.models import (
    ChatMessageRole as DBChatMessageRole,
)
from src.backend.modules.chat.models import (
    ChatMessageStatus as DBChatMessageStatus,
)
from src.backend.modules.chat.models import (
    ChatMessageType as DBChatMessageType,
)
from src.backend.modules.chat.models import (
    Customer,
    Thread,
)
from src.backend.modules.chat.models import (
    ThreadState as DBThreadState,
)
from src.backend.modules.chat.schemas import (
    ChatMessageCreateRequest,
    ChatMessagePatchRequest,
    ChatMessageResponse,
    ChatMessageRole,
    ChatMessageStatus,
    ChatMessageType,
    ChatParticipant,
    ChatThreadResponse,
    ChatThreadSummary,
    CustomerDetailResponse,
    CustomerGetOrCreateRequest,
    CustomerGetOrCreateResponse,
    CustomerNotesUpdateRequest,
    CustomerNotesUpdateResponse,
    CustomerProfileResponse,
    CustomerQuizAnswersUpdateRequest,
    CustomerQuizAnswersUpdateResponse,
    CustomerRejectRequest,
    CustomerUpdateRequest,
    CustomerUpdateResponse,
    HandoffNotificationRequest,
    HandoffNotificationResponse,
    InternalMessageEnvelope,
    InternalMessageIngestRequest,
    InternalMessageIngestResponse,
    LangfuseSessionRequest,
    LangfuseSessionResponse,
    OrderSummary,
    RealtimeEvent,
    RealtimeEventType,
    ThreadByConversationResponse,
    ThreadControlAction,
    ThreadControlResponse,
    ThreadCustomerDetails,
    ThreadCustomFieldsUpdateRequest,
    ThreadCustomFieldsUpdateResponse,
    ThreadFilter,
    ThreadGetOrCreateRequest,
    ThreadGetOrCreateResponse,
    ThreadHistoryRequest,
    ThreadState,
    ThreadStateUpdateRequest,
    ThreadStateUpdateResponse,
    UpdateFieldsUnifiedRequest,
    UpdateFieldsUnifiedResponse,
    WebSocketContractEventSchema,
    WebSocketContractResponse,
    WsTicketResponse,
    chat_message_preview_text,
)
from src.backend.modules.chat.thread_control import apply_thread_control
from src.backend.modules.core.dependencies import require_service_api_key
from src.backend.modules.core.settings import get_settings
from src.backend.modules.messages.dependencies import OutboundServiceDep
from src.backend.modules.orders.dependencies import OrderServiceDep
from src.backend.modules.transport.dependencies import ConnectorsServiceDep
from src.backend.modules.transport.models import Connector
from src.backend.services.redis import WsTicketPayload

# AICODE-NOTE: API layer for chat messages, threads, and customer management.

log = structlog.get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


public_router = APIRouter(prefix="/companies/{company_id}", tags=["chat"])
internal_router = APIRouter(
    prefix="/internal/chat",
    tags=["chat:internal"],
    dependencies=[Depends(require_service_api_key)],
)
websocket_router = APIRouter(tags=["chat"])


@public_router.post(
    "/ws-ticket",
    response_model=WsTicketResponse,
    summary="Issue a one-time WebSocket connection ticket",
)
async def create_ws_ticket(
    company_user: CompanyViewerDep,
    redis: RedisClientDep,
) -> WsTicketResponse:
    ticket = str(uuid4())
    payload = WsTicketPayload(
        user_id=company_user.user_id,
        company_id=company_user.company_id,
        role=company_user.role.value,
    )
    await redis.set_with_ttl(f"ws:ticket:{ticket}", payload, ttl=30)
    log.info("ws_ticket.created", user_id=company_user.user_id, company_id=company_user.company_id)
    return WsTicketResponse(ticket=ticket, expires_in=30)


@public_router.get(
    "/threads",
    response_model=PaginatedResponse[ChatThreadSummary],
    summary="List chat threads for UI",
    responses={
        status.HTTP_200_OK: {"description": "Threads fetched successfully"},
    },
)
async def list_threads(
    company_user: CompanyViewerDep,
    chat_service: ChatServiceDep,
    channel_type: str | None = Query(default=None, description="Optional filter by channel (telegram, whatsapp, ...)"),
    state: ThreadState | None = Query(default=None, description="Optional lifecycle state filter"),
    filter: ThreadFilter = Query(
        default=ThreadFilter.ALL,
        description="Filter by assignee (all/mine/ai/human)",
    ),
    pagination: PaginationParams = Depends(),
) -> PaginatedResponse[ChatThreadSummary]:
    # AICODE-NOTE: Convert API enum to DB enum if provided
    db_state = DBThreadState(state.value) if state else None

    threads, total = await chat_service.list_threads(
        company_id=company_user.company_id,
        channel_type=channel_type,
        state=db_state,
        assignee_filter=filter,
        current_user_id=company_user.id,
        limit=pagination.limit,
        offset=pagination.offset,
    )

    thread_ids = [t.thread_id for t in threads]
    order_ids = [t.active_order_id for t in threads if t.active_order_id]

    async def fetch_orders() -> dict:
        if not order_ids:
            return {}
        from src.backend.modules.orders.models import Order

        orders = await Order.filter(id__in=order_ids).prefetch_related("assignee__user", "stage").all()
        return {o.id: o for o in orders}

    # AICODE-NOTE: Parallel fetch last messages and orders (avoids sequential N+1)
    last_messages_map, orders_map = await asyncio.gather(
        chat_service.get_last_messages_batch(thread_ids),
        fetch_orders(),
    )

    connector_ids = list({t.connector_id for t in threads if t.connector_id})
    connector_by_id: dict[str, Connector] = {}
    if connector_ids:
        connectors = await Connector.filter(connector_id__in=connector_ids).only("connector_id", "type").all()
        connector_by_id = {c.connector_id: c for c in connectors}

    items = []
    for thread in threads:
        last_message = last_messages_map.get(thread.thread_id)

        # Get active order from batch-fetched map
        order_summary = None
        billing_status = BillingStatus.ACTIVE
        if thread.active_order_id and thread.active_order_id in orders_map:
            order = orders_map[thread.active_order_id]
            order_summary = OrderSummary.from_model(order)
            billing_status = order.billing_status

        meta = thread.customer.meta or {}
        details = ThreadCustomerDetails(
            email=str(meta.get("email", "-") or "-"),
            phone=str(meta.get("phone", "-") or "-"),
            location=str(meta.get("location", "-") or "-"),
            username=str(meta.get("username", "") or ""),
            customer_fields=dict(thread.customer.customer_fields or {}),
        )
        conn = connector_by_id.get(thread.connector_id) if thread.connector_id else None
        transport = conn.type.value if conn is not None else None
        summary = ChatThreadSummary(
            thread_id=thread.thread_id,
            company_id=thread.company_id,
            channel_type=thread.channel_type,
            connector_transport_type=transport,
            conversation_id=thread.conversation_id,
            customer_id=thread.customer.id,
            state=ThreadState(thread.state.value),
            customer_name=thread.customer.name,
            last_message_preview=(last_message.content if last_message else ""),
            last_message_at=(last_message.created_at if last_message else thread.created_at),
            unread_count=thread.unread_count,
            assistant_mode=thread.assistant_mode.value,
            billing_status=billing_status,
            active_order=order_summary,
            details=details,
        )
        items.append(summary)

    return PaginatedResponse[ChatThreadSummary](
        items=items,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@public_router.get(
    "/threads/{thread_id}",
    response_model=ChatThreadResponse,
    summary="Get thread detail with history",
)
async def get_thread(
    company_user: CompanyViewerDep,
    chat_service: ChatServiceDep,
    thread: ThreadManagerDep,
    thread_id: str = Path(..., min_length=1),
) -> ChatThreadResponse:
    messages, _ = await chat_service.get_thread_messages(thread_id=thread_id, limit=100)

    # AICODE-NOTE: Build participants list from customer and metadata
    participants = [
        ChatParticipant(
            participant_id=thread.customer.user_id,
            display_name=thread.metadata.get("customer_name", "Customer"),
            role=ChatMessageRole.USER,
        ),
        ChatParticipant(
            participant_id=f"assistant_{thread.company_id}",
            display_name=thread.metadata.get("assistant_name", "AI Assistant"),
            role=ChatMessageRole.ASSISTANT,
        ),
    ]

    message_responses = [ChatMessageResponse.from_model(msg, thread_id=thread.thread_id) for msg in messages]

    last_message = messages[-1] if messages else None

    # Fetch active order if exists
    order_summary = None
    if thread.active_order_id:
        await thread.fetch_related("active_order__assignee__user")
        if thread.active_order:
            order_summary = OrderSummary.from_model(thread.active_order)

    conn = None
    if thread.connector_id:
        conn = await Connector.filter(connector_id=thread.connector_id).only("type").first()
    transport = conn.type.value if conn is not None else None

    return ChatThreadResponse(
        thread_id=thread.thread_id,
        company_id=thread.company_id,
        channel_type=thread.channel_type,
        connector_transport_type=transport,
        conversation_id=thread.conversation_id,
        customer_id=thread.customer.id,
        state=ThreadState(thread.state.value),
        customer_name=thread.metadata.get("customer_name"),
        last_message_preview=(
            chat_message_preview_text(
                content=last_message.content if last_message else None,
                transcription=last_message.transcription if last_message else None,
            )[:120]
            if last_message
            else ""
        ),
        last_message_at=(last_message.created_at if last_message else thread.created_at),
        unread_count=thread.metadata.get("unread_count", 0),
        assistant_mode=thread.assistant_mode.value,
        active_order=order_summary,
        participants=participants,
        messages=message_responses,
        metadata=thread.metadata,
    )


@public_router.post(
    "/threads/{thread_id}/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Post manual message from manager",
)
async def send_manager_message(
    thread_id: Annotated[str, Path(min_length=1)],
    company_user: CompanyManagerDep,
    chat_service: ChatServiceDep,
    order_service: OrderServiceDep,
    outbound_service: OutboundServiceDep,
    connectors_service: ConnectorsServiceDep,
    thread: ThreadManagerDep,
    ws_manager: WebSocketManagerDep,
    background_tasks: BackgroundTasks,
    request: ChatMessageCreateRequest | None = None,
) -> ChatMessageResponse:
    # thread provided by dependency (access checked)

    payload = request or ChatMessageCreateRequest(role=ChatMessageRole.MANAGER, content="(empty)")

    db_role = DBChatMessageRole(payload.role.value)
    db_status = DBChatMessageStatus.PENDING
    # AICODE-NOTE: Determine message type based on is_note flag
    db_type = DBChatMessageType.INTERNAL_NOTE if payload.is_note else DBChatMessageType.TEXT

    artifact_ids = [a["artifact_id"] for a in payload.attachments if a.get("artifact_id")] or None

    message = await chat_service.create_message(
        thread_id=thread_id,
        role=db_role,
        content=payload.content,
        status=db_status,
        message_type=db_type,
        metadata=payload.metadata,
        attachments=payload.attachments or None,
        reply_to=payload.reply_to,
        author=company_user if db_role == DBChatMessageRole.MANAGER else None,
        artifact_ids=artifact_ids,
    )

    if payload.pause_assistant:
        if thread.active_order_id:
            order = await order_service.orders_repo.get_by_id(thread.active_order_id)
            if order:
                await order_service.orders_repo.update_assignee(order, company_user.id, author_id=company_user.id)
        await chat_service.control_thread_mode(
            thread_id=thread_id,
            mode=DBAssistantMode.INACTIVE,
            reason="Manager took over conversation",
        )
        fresh_thread = await Thread.get(thread_id=thread_id)
        assignee_payload = await chat_service.active_order_assignee_ws_payload(fresh_thread)
        await ws_manager.notify_control(
            fresh_thread.company_id,
            thread_id,
            {"action": "assistant_paused", "assistant_mode": "inactive", "reason": "Manager took over conversation"},
            assistant_mode=DBAssistantMode.INACTIVE.value,
            thread_state=fresh_thread.state.value,
            list_extra={"assignee": assignee_payload},
        )

    if not payload.is_note:
        (
            success,
            delivered_at_or_error,
        ) = await chat_service.deliver_manager_message(
            thread=thread,
            message_id=message.message_id,
            content=message.content,
            outbound_service=outbound_service,
            connectors_service=connectors_service,
            attachments=payload.attachments or None,
        )

        if success:
            await chat_service.update_message_status(
                message_id=message.message_id,
                status=DBChatMessageStatus.DELIVERED,
                delivered_at=datetime.fromisoformat(delivered_at_or_error),
            )
            message.status = DBChatMessageStatus.DELIVERED
            message.delivered_at = datetime.fromisoformat(delivered_at_or_error)
            background_tasks.add_task(
                chat_service.transcribe_voice_message,
                message.message_id,
                list(payload.attachments or []),
            )
        else:
            await chat_service.update_message_status(
                message_id=message.message_id,
                status=DBChatMessageStatus.FAILED,
            )
            message.status = DBChatMessageStatus.FAILED
            log.error(
                "manager_message.delivery_failed",
                message_id=message.message_id,
                thread_id=thread_id,
                error=delivered_at_or_error,
            )

        await ws_manager.notify_message(
            thread.company_id,
            thread_id,
            message,
            unread_delta=0,
            thread_state=thread.state.value,
        )

    else:
        await ws_manager.notify_note(thread_id, message)

    await message.fetch_related("author__user")
    return ChatMessageResponse.from_model(message, thread_id=thread_id)


@public_router.get(
    "/threads/{thread_id}/messages",
    response_model=PaginatedResponse[ChatMessageResponse],
    summary="List messages of a thread",
)
async def list_thread_messages(
    company_user: CompanyViewerDep,
    chat_service: ChatServiceDep,
    thread: ThreadManagerDep,
    thread_id: str = Path(..., min_length=1),
    pagination: PaginationParams = Depends(),
) -> PaginatedResponse[ChatMessageResponse]:
    # thread provided by dependency (company access checked)
    messages, total = await chat_service.get_thread_messages(
        thread_id=thread_id,
        limit=pagination.limit,
        offset=pagination.offset,
    )

    items = [ChatMessageResponse.from_model(msg, thread_id=thread_id) for msg in messages]

    return PaginatedResponse[ChatMessageResponse](
        items=items,
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@public_router.post(
    "/threads/{thread_id}/control/{action}",
    response_model=ThreadControlResponse,
    summary="Control assistant lifecycle for a thread",
)
async def control_thread(
    company_user: CompanyManagerDep,
    chat_service: ChatServiceDep,
    order_service: OrderServiceDep,
    thread: ThreadManagerDep,
    ws_manager: WebSocketManagerDep,
    thread_id: str = Path(..., min_length=1),
    action: ThreadControlAction = Path(..., description="Requested control action"),
) -> ThreadControlResponse:
    updated_by: str | None = None
    if action == ThreadControlAction.STOP_ASSISTANT:
        await company_user.fetch_related("user")
        fn = company_user.user.first_name or ""
        ln = company_user.user.last_name or ""
        updated_by = f"{fn} {ln}".strip() or "Менеджер"

    intercept_actions = (ThreadControlAction.STOP_ASSISTANT, ThreadControlAction.HANDOFF_TO_OPERATOR)
    if action in intercept_actions and thread.active_order_id:
        order = await order_service.orders_repo.get_by_id(thread.active_order_id)
        if order:
            await order_service.orders_repo.update_assignee(order, company_user.id, author_id=company_user.id)

    return await apply_thread_control(thread_id, action, "manager-ui", chat_service, ws_manager, updated_by=updated_by)


@public_router.get(
    "/customers/{customer_id}",
    response_model=CustomerDetailResponse,
    summary="Get full customer information",
    description=("Retrieve complete customer details including name, metadata, quiz answers, and fields schema"),
)
async def get_customer_detail(
    company_user: CompanyViewerDep,
    chat_service: ChatServiceDep,
    customer: CustomerManagerDep,
    customer_id: int = Path(..., ge=1, description="Customer ID"),
) -> CustomerDetailResponse:
    """Get full customer details by ID with fields schema."""
    meta = customer.meta or {}

    # AICODE-NOTE: Load fields schema for typed UI rendering
    fields_schema = await chat_service.get_customer_fields_schema(customer.company_id)

    return CustomerDetailResponse(
        customer_id=customer.id,
        user_id=customer.user_id,
        name=customer.name,
        username=meta.get("username"),
        phone=meta.get("phone"),
        email=meta.get("email"),
        avatar_url=meta.get("avatar_url"),
        customer_fields=customer.customer_fields or {},
        fields_schema=fields_schema,
        rejected=customer.rejected,
        rejection_reason=customer.rejection_reason,
        notes=customer.notes,
        meta=meta,
        created_at=customer.created_at,
        updated_at=customer.updated_at,
    )


@public_router.patch(
    "/customers/{customer_id}",
    response_model=CustomerUpdateResponse,
    summary="Update customer basic fields (Optimistic UI)",
)
async def update_customer(
    company_user: CompanyManagerDep,
    chat_service: ChatServiceDep,
    customer: CustomerManagerDep,
    customer_id: int = Path(..., ge=1, description="Customer ID"),
    request: CustomerUpdateRequest | None = None,
) -> CustomerUpdateResponse:
    """Update customer name and/or phone number."""
    # customer provided by dependency (company access checked)

    payload = request or CustomerUpdateRequest()

    try:
        customer = await chat_service.update_customer_basic_fields(
            customer_id=customer_id,
            name=payload.name,
            phone=payload.phone,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return CustomerUpdateResponse(
        customer_id=customer.id,
        user_id=customer.user_id,
        name=customer.name,
        phone=(customer.meta or {}).get("phone"),
        updated_at=customer.updated_at,
    )


@public_router.patch(
    "/customers/{customer_id}/fields",
    response_model=CustomerQuizAnswersUpdateResponse,
    summary="Update customer profile fields",
    description=("Update specific fields in customer_fields. Fields are merged with existing values."),
)
async def update_customer_profile_fields(
    company_user: CompanyManagerDep,
    chat_service: ChatServiceDep,
    customer: CustomerManagerDep,
    ws_manager: WebSocketManagerDep,
    customer_id: int = Path(..., ge=1, description="Customer ID"),
    request: CustomerQuizAnswersUpdateRequest | None = None,
) -> CustomerQuizAnswersUpdateResponse:
    """Update customer profile fields (merge with existing)."""
    # customer provided by dependency (company access checked)

    if not request:
        raise HTTPException(status_code=400, detail="fields are required")

    try:
        customer, changed_fields = await chat_service.update_customer_profile_fields(
            customer_id=customer_id,
            answers=request.answers,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    # AICODE-NOTE: Broadcast customer_updated event to all customer threads for real-time UI updates
    if changed_fields:
        await company_user.fetch_related("user")
        updated_by = f"{company_user.user.first_name} {company_user.user.last_name}"

        await customer.fetch_related("threads")
        for thread in customer.threads:
            changes_text = "\n".join([f"• {key}: {cf['new']}" for key, cf in changed_fields.items()])
            system_content = f"Обновлены данные клиента\n\nИзменения:\n{changes_text}\n\nКто: {updated_by}"

            sys_msg = await chat_service.create_message(
                thread_id=thread.thread_id,
                role=ChatMessageRole.SYSTEM,
                content=system_content,
                status=ChatMessageStatus.SENT,
                message_type=ChatMessageType.SYSTEM_EVENT,
                metadata={
                    "event_type": "customer_fields_update",
                    "changed_fields": {key: cf["new"] for key, cf in changed_fields.items()},
                    "updated_by": updated_by,
                },
            )

            await ws_manager.notify_thread_updated(
                thread.thread_id,
                {
                    "update_type": "customer_fields",
                    "changed_fields": {key: cf["new"] for key, cf in changed_fields.items()},
                    "updated_by": updated_by,
                    "updated_at": customer.updated_at.isoformat(),
                },
            )
            await ws_manager.notify_system_message(thread.thread_id, sys_msg)

    return CustomerQuizAnswersUpdateResponse(
        customer_id=customer.id,
        updated_answers={key: cf["new"] for key, cf in changed_fields.items()},
        updated_at=customer.updated_at,
    )


@public_router.patch(
    "/customers/{customer_id}/notes",
    response_model=CustomerNotesUpdateResponse,
    summary="Update customer notes",
)
async def update_customer_notes(
    company_user: CompanyManagerDep,
    chat_service: ChatServiceDep,
    customer: CustomerManagerDep,
    ws_manager: WebSocketManagerDep,
    customer_id: int = Path(..., ge=1, description="Customer ID"),
    request: CustomerNotesUpdateRequest | None = None,
) -> CustomerNotesUpdateResponse:
    """Update customer notes (manager manual input only)."""
    if not request:
        raise HTTPException(status_code=400, detail="Request body is required")

    try:
        customer = await chat_service.update_customer_notes(
            customer_id=customer_id,
            notes=request.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    # AICODE-NOTE: Broadcast customer update event for real-time UI updates
    # Find all threads for this customer to broadcast to
    threads, _ = await chat_service.list_threads(
        company_id=customer.company_id,
        limit=1000,
        offset=0,
    )
    customer_threads = [t for t in threads if t.customer_id == customer.id]

    # Fetch related user data for updated_by field
    await company_user.fetch_related("user")
    updated_by = f"{company_user.user.first_name} {company_user.user.last_name}".strip()

    # Create system message and broadcast to all customer threads
    for thread in customer_threads:
        # Create system message about notes update
        if request.notes:
            system_content = f"Обновлены заметки о клиенте\n\nКто: {updated_by}\n\nЗаметки:\n{request.notes}"
        else:
            system_content = f"Заметки о клиенте удалены\n\nКто: {updated_by}"

        sys_msg = await chat_service.create_message(
            thread_id=thread.thread_id,
            role=ChatMessageRole.SYSTEM,
            content=system_content,
            status=ChatMessageStatus.SENT,
            message_type=ChatMessageType.SYSTEM_EVENT,
            metadata={
                "event_type": "customer_notes_update",
                "notes": request.notes,
                "updated_by": updated_by,
            },
        )

        await ws_manager.notify_thread_updated(
            thread.thread_id,
            {
                "update_type": "customer_notes",
                "customer_id": customer.id,
                "notes": request.notes,
                "updated_by": updated_by,
                "updated_at": customer.updated_at.isoformat(),
            },
        )
        await ws_manager.notify_system_message(thread.thread_id, sys_msg)

    return CustomerNotesUpdateResponse(
        customer_id=customer.id,
        user_id=customer.user_id,
        notes=customer.notes,
        updated_at=customer.updated_at,
    )


@public_router.patch(
    "/threads/{thread_id}/fields",
    response_model=ThreadCustomFieldsUpdateResponse,
    summary="Update thread custom fields (Optimistic UI)",
)
async def update_thread_custom_fields(
    company_user: CompanyManagerDep,
    chat_service: ChatServiceDep,
    thread: ThreadManagerDep,
    ws_manager: WebSocketManagerDep,
    thread_id: str = Path(..., min_length=1, description="Thread identifier"),
    request: ThreadCustomFieldsUpdateRequest | None = None,
) -> ThreadCustomFieldsUpdateResponse:
    """Update custom fields like intent, goal, preferences.

    Changes are logged to chat history as system messages.
    """
    payload = request or ThreadCustomFieldsUpdateRequest(fields={})

    await company_user.fetch_related("user")
    updated_by = f"{company_user.user.first_name} {company_user.user.last_name}"

    try:
        thread, changed_fields, system_message = await chat_service.update_thread_custom_fields(
            thread_id=thread_id,
            fields=payload.fields,
            log_to_chat=True,
            updated_by=updated_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    if changed_fields:
        await ws_manager.notify_thread_updated(
            thread_id,
            {
                "update_type": "custom_fields",
                "changed_fields": {key: cf["new"] for key, cf in changed_fields.items()},
                "updated_by": updated_by,
                "updated_at": thread.updated_at.isoformat(),
            },
        )
        if system_message:
            await ws_manager.notify_system_message(thread_id, system_message)

    return ThreadCustomFieldsUpdateResponse(
        thread_id=thread.thread_id,
        updated_fields={key: cf["new"] for key, cf in changed_fields.items()},
        updated_at=thread.updated_at,
    )


# AICODE-NOTE: Thread stage and assignee endpoints removed - use Order endpoints instead
# PATCH /companies/{company_id}/orders/{order_id} for stage updates
# PUT /companies/{company_id}/orders/{order_id}/assignee for assignee updates


@websocket_router.websocket("/ws/companies/{company_id}")
async def listen_company(
    websocket: WebSocket,
    chat_service: ChatServiceDep,
    redis: RedisClientDep,
    ws_manager: WebSocketManagerDep,
    company_id: int = Path(...),
    ticket: str = Query(..., description="One-time WS auth ticket"),
) -> None:
    """Company-level WebSocket endpoint with ticket-based auth.

    Connect: GET /api/v1/ws/companies/{company_id}?ticket=<uuid>
    Ticket obtained via POST /api/v1/companies/{company_id}/ws-ticket (Bearer JWT).

    Inbound message types: subscribe, unsubscribe, message, control.
    """
    ticket_payload = await redis.get_and_delete(f"ws:ticket:{ticket}")

    if ticket_payload is None:
        log.warning("websocket.company_ticket_invalid", company_id=company_id)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if ticket_payload.company_id != company_id:
        log.warning(
            "websocket.company_ticket_mismatch",
            ticket_company_id=ticket_payload.company_id,
            url_company_id=company_id,
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    await ws_manager.connect_company(
        websocket,
        company_id=ticket_payload.company_id,
        user_id=ticket_payload.user_id,
        role=ticket_payload.role,
    )

    ack = RealtimeEvent(
        event_id=str(uuid4()),
        event_type=RealtimeEventType.ACK,
        thread_id="",
        payload={"message": "Connected to company stream"},
        emitted_at=_utcnow(),
    )
    await websocket.send_json(ack.model_dump(mode="json"))

    try:
        while True:
            data = await websocket.receive_json()
            match data.get("type"):
                case "subscribe":
                    thread_id = data.get("thread_id")
                    if not thread_id:
                        continue
                    thread = await chat_service.get_thread_by_id(thread_id)
                    if not thread or thread.company_id != company_id:
                        await websocket.send_json(
                            RealtimeEvent(
                                event_id=str(uuid4()),
                                event_type=RealtimeEventType.ACK,
                                thread_id=thread_id or "",
                                payload={"error": "Thread not found or access denied"},
                                emitted_at=_utcnow(),
                            ).model_dump(mode="json")
                        )
                        continue
                    await ws_manager.subscribe_thread(websocket, thread_id)

                case "unsubscribe":
                    thread_id = data.get("thread_id")
                    if thread_id:
                        await ws_manager.unsubscribe_thread(websocket, thread_id)

                case "message":
                    thread_id = data.get("thread_id")
                    payload = data.get("payload", {})
                    role_str = payload.get("role")
                    content = payload.get("content", "")
                    if not thread_id or not role_str or not content:
                        continue
                    db_role = DBChatMessageRole(role_str)
                    message = await chat_service.create_message(
                        thread_id=thread_id,
                        role=db_role,
                        content=content,
                        status=DBChatMessageStatus.SENT,
                        metadata=payload.get("metadata", {}),
                        attachments=payload.get("attachments", []),
                        reply_to=payload.get("reply_to"),
                    )
                    message_event = RealtimeEvent(
                        event_id=str(uuid4()),
                        event_type=RealtimeEventType.MESSAGE,
                        thread_id=thread_id,
                        payload={
                            "message_id": message.message_id,
                            "content": message.content,
                            "transcription": message.transcription,
                            "role": ChatMessageRole(message.role.value).value,
                            "status": ChatMessageStatus(message.status.value).value,
                            "created_at": message.created_at.isoformat(),
                            "metadata": message.metadata,
                            "attachments": message.attachments,
                            "reply_to": message.reply_to,
                        },
                        emitted_at=_utcnow(),
                    )
                    await ws_manager.broadcast_to_thread(thread_id, message_event)
                    await ws_manager.broadcast_to_company(
                        company_id,
                        RealtimeEvent(
                            event_id=str(uuid4()),
                            event_type=RealtimeEventType.THREAD_LIST_UPDATE,
                            thread_id=thread_id,
                            payload={
                                "last_message_preview": chat_message_preview_text(
                                    content=message.content,
                                    transcription=message.transcription,
                                )[:100],
                                "last_message_at": message.created_at.isoformat(),
                            },
                            emitted_at=_utcnow(),
                        ),
                    )

                case "control":
                    thread_id = data.get("thread_id")
                    raw_payload = data.get("payload")
                    action_str = raw_payload.get("action") if isinstance(raw_payload, dict) else None
                    if not thread_id or not action_str:
                        continue
                    try:
                        action = ThreadControlAction(action_str)
                        await apply_thread_control(thread_id, action, "websocket", chat_service, ws_manager)
                    except ValueError:
                        await websocket.send_json(
                            RealtimeEvent(
                                event_id=str(uuid4()),
                                event_type=RealtimeEventType.ACK,
                                thread_id=thread_id,
                                payload={"error": f"Invalid action: {action_str}"},
                                emitted_at=_utcnow(),
                            ).model_dump(mode="json")
                        )

    except WebSocketDisconnect:
        await ws_manager.disconnect_company(websocket)
    except Exception:
        log.exception("websocket.company_error", company_id=company_id)
        await ws_manager.disconnect_company(websocket)


@public_router.get(
    "/threads/{thread_id}/ws-contract",
    response_model=WebSocketContractResponse,
    summary="Document WebSocket contract for UI clients",
    description=(
        "Возвращает описание WS протокола для live-стрима сообщений: "
        "перечень событий, схемы payload и правила переподключения."
    ),
)
async def describe_ws_contract(
    company_user: CompanyViewerDep,
    company_id: int = Path(...),
    thread_id: str = Path(..., min_length=1),
) -> WebSocketContractResponse:
    outbound_events = [
        WebSocketContractEventSchema(
            event_type=RealtimeEventType.ACK,
            direction="outbound",
            description="Подтверждение подключения к company stream. Первое событие после connect.",
            payload_fields={"message": "Текстовое описание"},
            example={"message": "Connected to company stream"},
        ),
        WebSocketContractEventSchema(
            event_type=RealtimeEventType.MESSAGE,
            direction="outbound",
            description="Новое сообщение в треде (только для подписанных через subscribe).",
            payload_fields={
                "message_id": "Уникальный идентификатор сообщения",
                "content": "Текст сообщения",
                "role": "Автор сообщения (assistant|user|manager)",
                "status": "Статус доставки",
                "created_at": "ISO timestamp",
                "metadata": "Доп. атрибуты",
                "attachments": "Список вложений",
                "reply_to": "ID сообщения-цитаты (null если нет)",
            },
            example={
                "message_id": "msg-123",
                "content": "Привет!",
                "role": ChatMessageRole.ASSISTANT.value,
                "status": "sent",
                "created_at": "2025-01-01T12:00:00Z",
            },
        ),
        WebSocketContractEventSchema(
            event_type=RealtimeEventType.CONTROL,
            direction="outbound",
            description="Сигналы управления ассистентом (только для подписанных).",
            payload_fields={
                "action": "stop_assistant|resume_assistant|handoff_to_operator|return_to_assistant",
                "state": "Текущее состояние треда",
                "assistant_mode": "Режим ассистента (active/shadowing/inactive)",
                "issued_by": "Источник события",
            },
            example={
                "action": ThreadControlAction.STOP_ASSISTANT.value,
                "state": ThreadState.WAITING_MANAGER.value,
                "assistant_mode": "inactive",
                "issued_by": "manager-ui",
            },
        ),
        WebSocketContractEventSchema(
            event_type=RealtimeEventType.THREAD_UPDATED,
            direction="outbound",
            description="Обновление метаданных треда (только для подписанных).",
            payload_fields={
                "update_type": "Тип обновления (handoff|customer_fields|custom_fields|...)",
                "state": "Текущее состояние треда",
                "updated_at": "ISO timestamp",
            },
            example={"update_type": "handoff", "state": ThreadState.WAITING_MANAGER.value},
        ),
        WebSocketContractEventSchema(
            event_type=RealtimeEventType.THREAD_LIST_UPDATE,
            direction="outbound",
            description=(
                "Компактное обновление для списка тредов. Приходит всем подключённым к компании без подписки на тред."
            ),
            payload_fields={
                "last_message_preview": "Превью последнего сообщения (до 100 символов)",
                "last_message_at": "ISO timestamp последнего сообщения",
                "unread_count_delta": "Изменение счётчика непрочитанных (+1 для входящих)",
                "state": "Текущее состояние треда",
                "assistant_mode": "Режим ассистента (active/shadowing/inactive)",
            },
            example={
                "last_message_preview": "Интересует ваш продукт...",
                "last_message_at": "2025-01-01T12:00:00Z",
                "unread_count_delta": 1,
                "state": ThreadState.ACTIVE.value,
            },
        ),
        WebSocketContractEventSchema(
            event_type=RealtimeEventType.THREAD_CREATED,
            direction="outbound",
            description="Новый тред создан в компании. Приходит всем подключённым.",
            payload_fields={
                "thread_id": "Идентификатор треда",
                "company_id": "ID компании",
                "channel_type": "Канал (telegram|wappi|...)",
                "conversation_id": "Внешний ID диалога",
                "state": "Начальное состояние",
                "assistant_mode": "Режим ассистента (active/shadowing/inactive)",
            },
            example={
                "thread_id": "thr-abc123",
                "company_id": 1,
                "channel_type": "telegram",
                "state": ThreadState.ACTIVE.value,
                "assistant_mode": "active",
            },
        ),
        WebSocketContractEventSchema(
            event_type=RealtimeEventType.TYPING,
            direction="outbound",
            description="Typing indicator (только для подписанных на тред).",
            payload_fields={
                "role": "Кто печатает (assistant|manager)",
                "active": "Флаг активности индикатора",
            },
            example={"role": ChatMessageRole.ASSISTANT.value, "active": True},
        ),
    ]

    inbound_events = [
        WebSocketContractEventSchema(
            event_type=RealtimeEventType.ACK,
            direction="inbound",
            description=(
                'Служебный тип subscribe: {"type": "subscribe", "thread_id": "..."}. '
                "Подписывает соединение на полные события конкретного треда."
            ),
            payload_fields={"type": "subscribe", "thread_id": "ID треда"},
            example={"type": "subscribe", "thread_id": thread_id},
        ),
        WebSocketContractEventSchema(
            event_type=RealtimeEventType.ACK,
            direction="inbound",
            description=(
                'Служебный тип unsubscribe: {"type": "unsubscribe", "thread_id": "..."}. Отписывает от событий треда.'
            ),
            payload_fields={"type": "unsubscribe", "thread_id": "ID треда"},
            example={"type": "unsubscribe", "thread_id": thread_id},
        ),
        WebSocketContractEventSchema(
            event_type=RealtimeEventType.MESSAGE,
            direction="inbound",
            description="Отправка сообщения менеджера в тред через WS (альтернатива REST).",
            payload_fields={
                "type": "message",
                "thread_id": "ID треда (обязательно)",
                "payload.role": "manager|user",
                "payload.content": "Тело сообщения",
                "payload.metadata": "Доп. атрибуты",
            },
            example={
                "type": "message",
                "thread_id": thread_id,
                "payload": {"role": ChatMessageRole.MANAGER.value, "content": "Привет!"},
            },
        ),
        WebSocketContractEventSchema(
            event_type=RealtimeEventType.CONTROL,
            direction="inbound",
            description="Команда управления ассистентом через WS (альтернатива REST /control).",
            payload_fields={
                "type": "control",
                "thread_id": "ID треда (обязательно)",
                "payload.action": "stop_assistant|resume_assistant|handoff_to_operator|return_to_assistant",
            },
            example={
                "type": "control",
                "thread_id": thread_id,
                "payload": {"action": ThreadControlAction.STOP_ASSISTANT.value},
            },
        ),
    ]

    return WebSocketContractResponse(
        thread_id=thread_id,
        endpoint=f"wss://backend.example.com/api/v1/ws/companies/{company_id}?ticket=<uuid>",
        auth_header=(
            "1. POST /api/v1/companies/{company_id}/ws-ticket (Bearer JWT) → {ticket, expires_in: 30}. "
            "2. Connect: wss://host/api/v1/ws/companies/{company_id}?ticket=<uuid>. "
            "Ticket одноразовый, TTL 30s."
        ),
        reconnect_strategy="Exponential backoff starting from 1s up to 30s, stop after 5 attempts.",
        outbound_events=outbound_events,
        inbound_events=inbound_events,
    )


@internal_router.post(
    "/threads/{thread_id}/messages",
    response_model=InternalMessageIngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest messages from Sales Agent",
)
async def ingest_messages(
    chat_service: ChatServiceDep,
    ws_manager: WebSocketManagerDep,
    thread_id: str = Path(..., min_length=1),
    request: InternalMessageIngestRequest | None = None,
) -> InternalMessageIngestResponse:
    payload = request or InternalMessageIngestRequest(
        source="sales_agent",
        messages=[InternalMessageEnvelope(role=ChatMessageRole.ASSISTANT, content="demo")],
    )
    trace_id = payload.trace_id or str(uuid4())

    # AICODE-NOTE: Batch create messages from Sales Agent
    created_messages = []
    for msg_envelope in payload.messages:
        db_role = DBChatMessageRole(msg_envelope.role.value)
        db_status = DBChatMessageStatus(msg_envelope.status.value)

        message = await chat_service.create_message(
            thread_id=thread_id,
            role=db_role,
            content=msg_envelope.content,
            message_id=msg_envelope.message_id,
            status=db_status,
            metadata=msg_envelope.metadata,
            attachments=msg_envelope.attachments,
            reply_to=msg_envelope.reply_to,
            delivered_at=msg_envelope.delivered_at,
        )
        created_messages.append(message)

        # AICODE-NOTE: Broadcast new message to WebSocket clients
        message_event = RealtimeEvent(
            event_id=str(uuid4()),
            event_type=RealtimeEventType.MESSAGE,
            thread_id=thread_id,
            payload={
                "message_id": message.message_id,
                "content": message.content,
                "transcription": message.transcription,
                "role": ChatMessageRole(message.role.value).value,
                "status": ChatMessageStatus(message.status.value).value,
                "created_at": message.created_at.isoformat(),
                "metadata": message.metadata,
                "attachments": message.attachments,
                "reply_to": message.reply_to,
            },
            emitted_at=_utcnow(),
        )
        await ws_manager.broadcast_to_thread(thread_id, message_event)

    # AICODE-NOTE: Get updated thread state
    thread = await chat_service.get_thread_by_id(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    for msg in created_messages:
        await ws_manager.broadcast_to_company(
            thread.company_id,
            RealtimeEvent(
                event_id=str(uuid4()),
                event_type=RealtimeEventType.THREAD_LIST_UPDATE,
                thread_id=thread_id,
                payload={
                    "last_message_preview": chat_message_preview_text(
                        content=msg.content,
                        transcription=msg.transcription,
                    )[:100],
                    "last_message_at": msg.created_at.isoformat(),
                    "unread_count_delta": 1,
                    "state": thread.state.value,
                },
                emitted_at=_utcnow(),
            ),
        )

    return InternalMessageIngestResponse(
        thread_id=thread_id,
        accepted=len(created_messages),
        state=ThreadState(thread.state.value),
        trace_id=trace_id,
    )


@internal_router.patch(
    "/messages/{message_id}",
    response_model=ChatMessageResponse,
    summary="Patch message status reported by Sales Agent",
)
async def patch_message_status(
    chat_service: ChatServiceDep,
    message_id: str = Path(..., min_length=1),
    request: ChatMessagePatchRequest | None = None,
) -> ChatMessageResponse:
    patch = request or ChatMessagePatchRequest(status=ChatMessageStatus.SENT)

    # AICODE-NOTE: Convert API enum to DB enum
    db_status = DBChatMessageStatus(patch.status.value)

    message = await chat_service.update_message_status(
        message_id=message_id,
        status=db_status,
        delivered_at=patch.delivered_at or _utcnow(),
        metadata=patch.metadata,
    )

    await message.fetch_related("author__user", "thread")
    return ChatMessageResponse.from_model(message)


@internal_router.get(
    "/messages/{message_id}",
    response_model=ChatMessageResponse,
    summary="Get message by ID (for checking transcription cache)",
)
async def get_message(
    chat_service: ChatServiceDep,
    message_id: str = Path(..., min_length=1),
) -> ChatMessageResponse:
    """Get message by ID for internal services (e.g., Sales-Agent checking transcription cache).

    Args:
        chat_service: Chat service dependency
        message_id: Message identifier

    Returns:
        ChatMessageResponse with content and optional transcription field for STT

    Raises:
        HTTPException: If message not found
    """
    try:
        message = await chat_service.get_message_by_id(message_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    await message.fetch_related("author__user", "thread")
    return ChatMessageResponse.from_model(message)


@internal_router.post(
    "/messages/{message_id}/transcription",
    response_model=ChatMessageResponse,
    summary="Save transcription text for a message",
)
async def save_transcription(
    chat_service: ChatServiceDep,
    ws_manager: WebSocketManagerDep,
    message_id: str = Path(..., min_length=1),
    request: dict[str, str] = Body(...),
) -> ChatMessageResponse:
    """Save transcription text for a message (called by Sales-Agent after STT).

    Args:
        chat_service: Chat service dependency
        message_id: Message identifier
        request: Request body with transcribed_text field

    Returns:
        Updated ChatMessageResponse

    Raises:
        HTTPException: If message not found or transcribed_text missing
    """
    transcribed_text = request.get("transcribed_text", "")
    if not transcribed_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="transcribed_text is required",
        )

    try:
        message = await chat_service.get_message_by_id(message_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    message.transcription = transcribed_text
    await message.save(update_fields=["transcription", "updated_at"])

    log.info(
        "transcription.saved",
        message_id=message_id,
        text_length=len(transcribed_text),
    )

    await message.fetch_related("author__user", "thread")
    await ws_manager.notify_thread_updated(
        message.thread.thread_id,
        {
            "update_type": "message_transcription",
            "message_id": message.message_id,
            "transcription": transcribed_text,
        },
    )
    return ChatMessageResponse.from_model(message)


@internal_router.post(
    "/threads/{thread_id}/state",
    response_model=ThreadStateUpdateResponse,
    summary="Update thread lifecycle from Sales Agent",
)
async def update_thread_state(
    chat_service: ChatServiceDep,
    thread_id: str = Path(..., min_length=1),
    request: ThreadStateUpdateRequest | None = None,
) -> ThreadStateUpdateResponse:
    payload = request or ThreadStateUpdateRequest(state=ThreadState.ACTIVE, reason="demo")

    # AICODE-NOTE: Get previous state before update
    thread = await chat_service.get_thread_by_id(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    previous_state = ThreadState(thread.state.value)

    # AICODE-NOTE: Convert API enum to DB enum and update
    db_state = DBThreadState(payload.state.value)
    updated_thread = await chat_service.update_thread_state(
        thread_id=thread_id,
        state=db_state,
        reason=payload.reason,
        metadata=payload.metadata,
    )

    return ThreadStateUpdateResponse(
        thread_id=thread_id,
        previous_state=previous_state,
        state=ThreadState(updated_thread.state.value),
        updated_at=_utcnow(),
        metadata=updated_thread.metadata,
    )


@internal_router.post(
    "/customers/get-or-create",
    response_model=CustomerGetOrCreateResponse,
    summary="Get or create customer (Sales Agent internal)",
)
async def get_or_create_customer_internal(
    chat_service: ChatServiceDep,
    request: CustomerGetOrCreateRequest,
) -> CustomerGetOrCreateResponse:
    customer, created = await chat_service.get_or_create_customer(
        user_id=request.user_id,
        company_id=request.company_id,
        meta=request.meta,
    )
    return CustomerGetOrCreateResponse(
        customer_id=customer.id,
        user_id=customer.user_id,
        company_id=customer.company_id,
        created=created,
    )


@internal_router.get(
    "/customers/{user_id}/profile",
    response_model=CustomerProfileResponse,
    summary="Get customer profile (Sales Agent internal)",
)
async def get_customer_profile_internal(
    chat_service: ChatServiceDep,
    user_id: str = Path(..., min_length=1),
    company_id: int = Query(..., ge=1),
) -> CustomerProfileResponse:
    return await chat_service.get_customer_profile(
        user_id=user_id,
        company_id=company_id,
    )


@internal_router.get(
    "/customers/{user_id}/answers",
    response_model=dict[str, Any],
    summary="Get customer fields (Sales Agent internal)",
)
async def get_customer_answers_internal(
    chat_service: ChatServiceDep,
    user_id: str = Path(..., min_length=1),
    company_id: int = Query(..., ge=1),
) -> dict[str, Any]:
    profile = await chat_service.get_customer_profile(
        user_id=user_id,
        company_id=company_id,
    )
    return profile.customer_fields


@internal_router.patch(
    "/customers/{user_id}/fields",
    response_model=UpdateFieldsUnifiedResponse,
    summary="Update fields unified (Sales Agent internal)",
)
async def update_fields_unified_internal(
    chat_service: ChatServiceDep,
    ws_manager: WebSocketManagerDep,
    user_id: str = Path(..., min_length=1),
    request: UpdateFieldsUnifiedRequest | None = None,
) -> UpdateFieldsUnifiedResponse:
    if not request:
        return UpdateFieldsUnifiedResponse()
    response = await chat_service.update_fields_unified(
        user_id=user_id,
        company_id=request.company_id,
        updates=request.updates,
        order_id=request.order_id,
    )
    if not any([response.updated_customer, response.updated_order, response.updated_extra]):
        return response

    customer_changed = {k: request.updates[k] for k in response.updated_customer}
    order_changed = {k: request.updates[k] for k in response.updated_order}
    extra_changed = {k: request.updates[k] for k in response.updated_extra}
    all_changed = {**customer_changed, **order_changed, **extra_changed}
    changes_text = "\n".join([f"• {key}: {val}" for key, val in all_changed.items()])
    system_content = f"Обновлены поля\n\nИзменения:\n{changes_text}\n\nКто: AI Agent"

    update_type = "fields"
    payload_base: dict[str, Any] = {
        "update_type": update_type,
        "changed_fields": all_changed,
        "customer_fields": customer_changed,
        "order_fields": order_changed,
        "extra_fields": extra_changed,
        "updated_by": "AI Agent",
    }
    if response.updated_order or response.updated_extra:
        payload_base["order_id"] = request.order_id

    seen_thread_ids: set[str] = set()
    threads_to_notify: list[Thread] = []
    if response.updated_order or response.updated_extra and request.order_id:
        thread = await Thread.filter(active_order_id=request.order_id).first()
        if thread and thread.thread_id not in seen_thread_ids:
            seen_thread_ids.add(thread.thread_id)
            threads_to_notify.append(thread)
    if response.updated_customer:
        customer = (
            await Customer.filter(user_id=user_id, company_id=request.company_id).prefetch_related("threads").first()
        )
        if customer:
            for t in customer.threads:
                if t.thread_id not in seen_thread_ids:
                    seen_thread_ids.add(t.thread_id)
                    threads_to_notify.append(t)

    for thread in threads_to_notify:
        sys_msg = await chat_service.create_message(
            thread_id=thread.thread_id,
            role=DBChatMessageRole.SYSTEM,
            content=system_content,
            status=DBChatMessageStatus.SENT,
            message_type=DBChatMessageType.SYSTEM_EVENT,
            metadata={
                "event_type": "fields_update",
                "changed_fields": all_changed,
                "updated_by": "AI Agent",
            },
        )
        await ws_manager.notify_thread_updated(
            thread.thread_id,
            {**payload_base, "updated_at": datetime.now(UTC).isoformat()},
        )
        await ws_manager.notify_system_message(thread.thread_id, sys_msg)

    return response


@internal_router.post(
    "/customers/{user_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark customer rejected (Sales Agent internal)",
)
async def mark_customer_rejected_internal(
    chat_service: ChatServiceDep,
    user_id: str = Path(..., min_length=1),
    request: CustomerRejectRequest | None = None,
) -> None:
    if not request:
        return
    await chat_service.mark_customer_rejected(
        user_id=user_id,
        company_id=request.company_id,
        reason=request.reason,
    )


@internal_router.delete(
    "/customers/{user_id}/profile",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reset customer profile (Sales Agent internal)",
)
async def reset_customer_profile_internal(
    chat_service: ChatServiceDep,
    user_id: str = Path(..., min_length=1),
    company_id: int = Query(..., ge=1),
) -> None:
    await chat_service.reset_customer_profile(
        user_id=user_id,
        company_id=company_id,
    )


@internal_router.post(
    "/threads/{thread_id}/handoff",
    response_model=HandoffNotificationResponse,
    summary="Notify backend about AI agent handoff (Sales Agent internal)",
)
async def notify_handoff_internal(
    chat_service: ChatServiceDep,
    ws_manager: WebSocketManagerDep,
    thread_id: str = Path(..., min_length=1, description="Thread identifier"),
    request: HandoffNotificationRequest | None = None,
) -> HandoffNotificationResponse:
    """Process AI agent handoff to manager.

    Creates system message, updates thread state, sets assistant mode,
    and broadcasts WebSocket event.
    """
    if not request:
        raise HTTPException(status_code=400, detail="Request body required")

    try:
        thread, system_message = await chat_service.handle_handoff(
            thread_id=thread_id,
            summary=request.summary,
            reason=request.reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    from src.backend.modules.chat.schemas import AssistantMode as SchemaAssistantMode

    handoff_event = RealtimeEvent(
        event_id=str(uuid4()),
        event_type=RealtimeEventType.THREAD_UPDATED,
        thread_id=thread_id,
        payload={
            "update_type": "handoff",
            "summary": request.summary,
            "reason": request.reason,
            "updated_by": "assistant",
            "state": thread.state.value,
            "assistant_mode": thread.assistant_mode.value,
            "updated_at": thread.updated_at.isoformat(),
        },
        emitted_at=_utcnow(),
    )
    await ws_manager.broadcast_to_thread(thread_id, handoff_event)
    await ws_manager.broadcast_to_company(
        thread.company_id,
        RealtimeEvent(
            event_id=str(uuid4()),
            event_type=RealtimeEventType.THREAD_LIST_UPDATE,
            thread_id=thread_id,
            payload={"state": thread.state.value, "assistant_mode": thread.assistant_mode.value},
            emitted_at=_utcnow(),
        ),
    )
    await ws_manager.notify_system_message(thread_id, system_message)

    return HandoffNotificationResponse(
        thread_id=thread.thread_id,
        state=ThreadState(thread.state.value),
        assistant_mode=SchemaAssistantMode(thread.assistant_mode.value),
        message_id=system_message.message_id,
        processed_at=_utcnow(),
    )


@internal_router.get(
    "/customers/{user_id}/langfuse-session",
    response_model=LangfuseSessionResponse,
    summary="Get Langfuse session ID (Sales Agent internal)",
)
async def get_langfuse_session_internal(
    chat_service: ChatServiceDep,
    user_id: str = Path(..., min_length=1),
    company_id: int = Query(..., ge=1),
    conversation_id: str = Query(..., min_length=1),
) -> LangfuseSessionResponse:
    return await chat_service.get_langfuse_session_id(
        user_id=user_id,
        company_id=company_id,
        conversation_id=conversation_id,
    )


@internal_router.post(
    "/customers/{user_id}/langfuse-session",
    response_model=LangfuseSessionResponse,
    summary="Create Langfuse session ID (Sales Agent internal)",
)
async def create_langfuse_session_internal(
    chat_service: ChatServiceDep,
    user_id: str = Path(..., min_length=1),
    request: LangfuseSessionRequest | None = None,
) -> LangfuseSessionResponse:
    if not request:
        raise HTTPException(status_code=400, detail="conversation_id and company_id required")

    session_id = await chat_service.create_langfuse_session(
        user_id=user_id,
        company_id=request.company_id,
        conversation_id=request.conversation_id,
    )
    return LangfuseSessionResponse(session_id=session_id)


@internal_router.post(
    "/threads/get-or-create",
    response_model=ThreadGetOrCreateResponse,
    summary="Get or create thread (Sales Agent internal)",
)
async def get_or_create_thread_internal(
    chat_service: ChatServiceDep,
    order_service: OrderServiceDep,
    ws_manager: WebSocketManagerDep,
    request: ThreadGetOrCreateRequest,
) -> ThreadGetOrCreateResponse:
    thread, created = await chat_service.get_or_create_thread(
        user_id=request.user_id,
        company_id=request.company_id,
        channel_type=request.channel_type,
        connector_id=request.connector_id,
        conversation_id=request.conversation_id,
        thread_id=request.thread_id,
        meta=request.meta,
    )
    # Get stage from active order
    order = await order_service.ensure_active_order(thread)
    await order.fetch_related("stage")

    if created:
        await ws_manager.broadcast_to_company(
            thread.company_id,
            RealtimeEvent(
                event_id=str(uuid4()),
                event_type=RealtimeEventType.THREAD_CREATED,
                thread_id=thread.thread_id,
                payload={
                    "thread_id": thread.thread_id,
                    "company_id": thread.company_id,
                    "channel_type": thread.channel_type,
                    "conversation_id": thread.conversation_id,
                    "state": thread.state.value,
                    "assistant_mode": thread.assistant_mode.value,
                },
                emitted_at=_utcnow(),
            ),
        )

    return ThreadGetOrCreateResponse(
        thread_id=thread.thread_id,
        user_id=thread.customer.user_id,
        company_id=thread.company_id,
        channel_type=thread.channel_type,
        connector_id=thread.connector_id or "default",
        conversation_id=thread.conversation_id,
        stage=order.stage.name if order.stage else None,
        assistant_mode=thread.assistant_mode.value,
        history_synced=thread.history_synced,
        created=created,
    )


@internal_router.post(
    "/threads/{thread_id}/history",
    response_model=list[dict[str, Any]],
    summary="Get thread message history (Sales Agent internal)",
)
async def get_thread_history_internal(
    chat_service: ChatServiceDep,
    thread_id: str = Path(..., min_length=1),
    request: ThreadHistoryRequest | None = None,
) -> list[dict[str, Any]]:
    limit = request.limit if request else None
    return await chat_service.get_recent_history(
        thread_id=thread_id,
        limit=limit,
    )


@internal_router.get(
    "/threads/by-conversation",
    response_model=ThreadByConversationResponse,
    summary="Get thread by conversation ID (internal)",
)
async def get_thread_by_conversation_internal(
    chat_service: ChatServiceDep,
    connector_id: str = Query(..., min_length=1),
    conversation_id: str = Query(..., min_length=1),
) -> ThreadByConversationResponse:
    """Get thread by connector and conversation IDs.

    Used by transport modules to check if history is already synced.
    """
    thread = await Thread.filter(
        connector_id=connector_id,
        conversation_id=conversation_id,
    ).first()

    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    return ThreadByConversationResponse(
        thread_id=thread.thread_id,
        history_synced=thread.history_synced,
    )


@internal_router.patch(
    "/threads/{thread_id}/history-synced",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark thread history as fully synced (internal)",
)
async def mark_thread_history_synced_internal(
    chat_service: ChatServiceDep,
    thread_id: str = Path(..., min_length=1),
) -> None:
    """Mark thread history as fully synced.

    Called by transport modules after successfully syncing full conversation history.
    """
    thread = await chat_service.get_thread_by_id(thread_id)
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    thread.history_synced = True
    await thread.save(update_fields=["history_synced"])


@public_router.post(
    "/threads/{thread_id}/sync-history",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Sync full conversation history for thread",
)
async def sync_thread_history(
    chat_service: ChatServiceDep,
    connectors_service: ConnectorsServiceDep,
    company: CompanyManagerDep,
    thread_id: str = Path(..., min_length=1),
) -> dict[str, str]:
    """Trigger full conversation history sync for a thread.

    Fetches all messages from the external provider (Wappi/Telegram) and syncs them to the database.
    This includes:
    - All historical messages
    - Media files (uploaded to S3 with artifact_ids)
    - Proper message roles and timestamps

    After successful sync, marks thread.history_synced = True to prevent duplicate syncs.

    Args:
        thread_id: Thread identifier
        company: Authenticated company (from auth)

    Returns:
        Status message with sync details

    Raises:
        HTTPException 404: Thread not found
        HTTPException 403: Thread doesn't belong to company
        HTTPException 409: History already synced
        HTTPException 400: Invalid thread state (missing connector/conversation)
        HTTPException 503: Transport module not configured
    """
    settings = get_settings()

    # Get thread
    thread = await chat_service.get_thread_by_id(thread_id)
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    # Check company ownership
    if thread.company_id != company.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Thread does not belong to your company",
        )

    # Check if history already synced
    if thread.history_synced:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Thread history already synced",
        )

    # Check required fields
    if not thread.connector_id or not thread.conversation_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Thread missing connector_id or conversation_id",
        )

    # Get connector to determine transport type
    connector = await connectors_service.get_by_connector_id(thread.connector_id)
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector {thread.connector_id} not found",
        )

    # Determine transport module URL based on connector type
    transport_url: str | None = None
    sync_path: str = ""

    if connector.type == "wappi":
        transport_url = settings.transport.wappi.url
        sync_path = f"wappi/sync/{thread.connector_id}/conversation/{thread.conversation_id}"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"History sync not supported for connector type: {connector.type}",
        )

    if not transport_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Transport module URL not configured for type: {connector.type}",
        )

    # Trigger sync in transport module
    try:
        url = f"{transport_url.rstrip('/')}/{sync_path}"
        headers = {"X-Service-Key": settings.service.api_key.get_secret_value()}

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers)
            response.raise_for_status()

        log.info(
            "thread.history_sync.triggered",
            thread_id=thread_id,
            connector_id=thread.connector_id,
            conversation_id=thread.conversation_id,
            connector_type=connector.type,
            company_id=company.id,
        )

        return {
            "status": "sync_triggered",
            "thread_id": thread_id,
            "message": "Full conversation history sync started. This may take a few minutes.",
        }

    except httpx.HTTPError as e:
        log.error(
            "thread.history_sync.failed",
            thread_id=thread_id,
            connector_id=thread.connector_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to trigger sync in transport module: {e}",
        ) from e


# AICODE-NOTE: Internal thread stage endpoint removed - use Order endpoints instead
# PATCH /internal/orders/{order_id}/stage for stage updates
