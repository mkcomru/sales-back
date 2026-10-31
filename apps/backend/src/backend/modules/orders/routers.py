"""Order API endpoints."""

from __future__ import annotations

from zoneinfo import ZoneInfo

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, status

from src.backend.modules.auth.dependencies import (
    require_company_manager,
    require_company_viewer,
)
from src.backend.modules.chat.dependencies import ChatServiceDep, WebSocketManagerDep
from src.backend.modules.chat.models import (
    AssistantMode,
    ChatMessageRole,
    ChatMessageStatus,
    ChatMessageType,
    Thread,
    ThreadState,
)
from src.backend.modules.core.dependencies import require_service_api_key
from src.backend.modules.orders.dependencies import OrderServiceDep
from src.backend.modules.orders.hooks import on_order_assigned_outside_working_hours
from src.backend.modules.orders.load_balancing import select_manager
from src.backend.modules.orders.models import Order
from src.backend.modules.orders.schemas import (
    AddCommentRequest,
    AvailabilityInfo,
    HandoffRequest,
    HandoffResult,
    ManagerInfo,
    OrderAssigneeUpdateRequest,
    OrderCloseRequest,
    OrderContext,
    OrderCreateRequest,
    OrderFrozenUpdateRequest,
    OrderLogResponse,
    OrderResponse,
    OrderStageRequirementsResponse,
    OrderStageUpdateRequest,
    OrderUpdateRequest,
)
from src.backend.modules.stages.models import StageTemplate
from src.backend.modules.users.models import CompanyUser
from src.backend.modules.users.schedule_service import schedule_service

log = structlog.get_logger(__name__)

public_router = APIRouter(prefix="/companies/{company_id}/orders", tags=["orders"])
internal_router = APIRouter(prefix="/internal/orders", tags=["orders:internal"])


async def _order_response(order: Order) -> OrderResponse:
    thread = await Thread.get_or_none(active_order_id=order.id)
    return OrderResponse.from_model(
        order,
        thread_id=thread.thread_id if thread else None,
        assistant_mode=thread.assistant_mode.value if thread else None,
    )


async def _order_responses(orders: list[Order]) -> list[OrderResponse]:
    if not orders:
        return []
    order_ids = [o.id for o in orders]
    threads = await Thread.filter(active_order_id__in=order_ids)
    by_order: dict[int, Thread] = {t.active_order_id: t for t in threads if t.active_order_id is not None}
    return [
        OrderResponse.from_model(
            o,
            thread_id=by_order[o.id].thread_id if o.id in by_order else None,
            assistant_mode=by_order[o.id].assistant_mode.value if o.id in by_order else None,
        )
        for o in orders
    ]


@public_router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_company_manager)],
)
async def create_order(
    request: OrderCreateRequest,
    order_service: OrderServiceDep,
    current_user: CompanyUser = Depends(require_company_manager),
    company_id: int = Path(..., description="Company ID"),
) -> OrderResponse:
    """Create a new order."""
    order = await order_service.create_order(
        company_id=company_id,
        customer_id=request.customer_id,
        assignee_id=request.assignee_id,
        author_id=current_user.id,
        initial_channel=request.initial_channel,
    )
    await order.fetch_related("customer", "company", "assignee__user", "stage")
    return await _order_response(order)


@public_router.get(
    "",
    response_model=list[OrderResponse],
    dependencies=[Depends(require_company_viewer)],
)
async def list_orders(
    order_service: OrderServiceDep,
    company_id: int = Path(..., description="Company ID"),
    limit: int = 100,
    offset: int = 0,
) -> list[OrderResponse]:
    """List orders for a company."""
    orders = await order_service.orders_repo.list_by_company(company_id, limit=limit, offset=offset)
    for order in orders:
        await order.fetch_related("customer", "assignee__user", "stage")
    return await _order_responses(orders)


@public_router.get(
    "/{order_id}",
    response_model=OrderResponse,
    dependencies=[Depends(require_company_viewer)],
)
async def get_order(
    order_service: OrderServiceDep,
    company_id: int = Path(..., description="Company ID"),
    order_id: int = Path(..., description="Order ID"),
) -> OrderResponse:
    """Get order by ID."""
    order = await order_service.orders_repo.get_by_id(order_id)
    if not order or order.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    await order.fetch_related("customer", "assignee__user", "stage")
    return await _order_response(order)


@public_router.patch(
    "/{order_id}",
    response_model=OrderResponse,
    dependencies=[Depends(require_company_manager)],
)
async def update_order(
    request: OrderUpdateRequest,
    order_service: OrderServiceDep,
    chat_service: ChatServiceDep,
    ws_manager: WebSocketManagerDep,
    current_user: CompanyUser = Depends(require_company_manager),
    order_id: int = Path(..., description="Order ID"),
    company_id: int = Path(..., description="Company ID"),
) -> OrderResponse:
    """Update order."""
    order = await order_service.orders_repo.get_by_id(order_id)
    if not order or order.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if request.name is not None:
        order.name = request.name
        await order.save(update_fields=["name"])

    stage_changed = False
    old_stage_name: str | None = None
    new_stage_name: str | None = None

    if request.stage_id is not None:
        await order.fetch_related("stage")
        old_stage_name = order.stage.name if order.stage else "Без стадии"
        order, _ = await order_service.orders_repo.update_stage_by_id(
            order, request.stage_id, author_id=current_user.id
        )
        await order.fetch_related("stage")
        new_stage_name = order.stage.name if order.stage else "Без стадии"
        stage_changed = old_stage_name != new_stage_name
    elif "stage_id" in request.model_fields_set and request.stage_id is None:
        await order.fetch_related("stage")
        old_stage_name = order.stage.name if order.stage else "Без стадии"
        order, _ = await order_service.orders_repo.update_stage_by_id(order, None, author_id=current_user.id)
        new_stage_name = "Без стадии"
        stage_changed = old_stage_name != new_stage_name

    if request.order_fields is not None:
        order = await order_service.update_order_fields(order.id, request.order_fields, author_id=current_user.id)

    if request.extra_fields is not None:
        order, _ = await order_service.orders_repo.update_extra_fields(order, request.extra_fields)

    if stage_changed:
        await current_user.fetch_related("user")
        updated_by = f"{current_user.user.first_name} {current_user.user.last_name}".strip()
        thread = await Thread.filter(active_order_id=order_id).first()
        if thread:
            sys_msg = await chat_service.create_message(
                thread_id=thread.thread_id,
                role=ChatMessageRole.SYSTEM,
                content=f"Этап изменен: {old_stage_name} → {new_stage_name}\n\nКто: {updated_by}",
                status=ChatMessageStatus.SENT,
                message_type=ChatMessageType.SYSTEM_EVENT,
                metadata={
                    "event_type": "order_stage_change",
                    "old_stage": old_stage_name,
                    "new_stage": new_stage_name,
                    "updated_by": updated_by,
                },
            )
            await ws_manager.notify_system_message(thread.thread_id, sys_msg)

    if request.order_fields is not None and not stage_changed:
        thread = await Thread.filter(active_order_id=order_id).first()
        if thread:
            await current_user.fetch_related("user")
            updated_by = f"{current_user.user.first_name} {current_user.user.last_name}".strip()
            changes_text = "\n".join([f"• {k}: {v}" for k, v in request.order_fields.items()])
            sys_msg = await chat_service.create_message(
                thread_id=thread.thread_id,
                role=ChatMessageRole.SYSTEM,
                content=f"Обновлены поля заказа\n\nИзменения:\n{changes_text}\n\nКто: {updated_by}",
                status=ChatMessageStatus.SENT,
                message_type=ChatMessageType.SYSTEM_EVENT,
                metadata={
                    "event_type": "order_fields_update",
                    "changed_fields": request.order_fields,
                    "updated_by": updated_by,
                },
            )
            await ws_manager.notify_thread_updated(
                thread.thread_id,
                {
                    "update_type": "order_fields",
                    "order_id": order_id,
                    "changed_fields": request.order_fields,
                    "updated_by": updated_by,
                    "updated_at": order.updated_at.isoformat(),
                },
            )
            await ws_manager.notify_system_message(thread.thread_id, sys_msg)

    await order.fetch_related("customer", "assignee__user", "stage")
    return await _order_response(order)


@public_router.put(
    "/{order_id}/assignee",
    response_model=OrderResponse,
    dependencies=[Depends(require_company_manager)],
)
async def update_order_assignee(
    request: OrderAssigneeUpdateRequest,
    order_service: OrderServiceDep,
    chat_service: ChatServiceDep,
    ws_manager: WebSocketManagerDep,
    current_user: CompanyUser = Depends(require_company_manager),
    company_id: int = Path(..., description="Company ID"),
    order_id: int = Path(..., description="Order ID"),
) -> OrderResponse:
    """Update order assignee."""
    order = await order_service.orders_repo.get_by_id(order_id)
    if not order or order.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    new_assignee: CompanyUser | None = None
    if request.assignee_id is not None:
        new_assignee = await CompanyUser.get_or_none(id=request.assignee_id, company_id=company_id)
        if not new_assignee:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignee not found")

    order, _ = await order_service.orders_repo.update_assignee(order, request.assignee_id, author_id=current_user.id)

    thread = await Thread.filter(active_order_id=order_id).first()
    if thread and request.assignee_id is None:
        thread = await chat_service.update_thread_state(
            thread_id=thread.thread_id,
            state=ThreadState.ACTIVE,
            reason="Returned to assistant from assignee unassign",
        )
        await chat_service.control_thread_mode(
            thread_id=thread.thread_id,
            mode=AssistantMode.ACTIVE,
            reason="Returned to assistant from assignee unassign",
        )
        await ws_manager.notify_control(
            thread.company_id,
            thread.thread_id,
            {"action": "return_to_assistant", "issued_by": "manager-ui"},
            assistant_mode=AssistantMode.ACTIVE.value,
            thread_state=ThreadState.ACTIVE.value,
            list_extra={"assignee": None},
        )
    if thread:
        if new_assignee:
            await new_assignee.fetch_related("user")
            assignee_name = f"{new_assignee.user.first_name} {new_assignee.user.last_name}".strip()
        else:
            assignee_name = "AI Agent"

        await current_user.fetch_related("user")
        updated_by = f"{current_user.user.first_name} {current_user.user.last_name}".strip()

        sys_msg = await chat_service.create_message(
            thread_id=thread.thread_id,
            role=ChatMessageRole.SYSTEM,
            content=f"Ответственный изменен: {assignee_name}\n\nКто: {updated_by}",
            status=ChatMessageStatus.SENT,
            message_type=ChatMessageType.SYSTEM_EVENT,
            metadata={"event_type": "order_assignee_change", "assignee": assignee_name, "updated_by": updated_by},
        )
        await ws_manager.notify_system_message(thread.thread_id, sys_msg)

    if thread and request.assignee_id is not None:
        fresh_thread = await Thread.get(thread_id=thread.thread_id)
        assignee_payload = await chat_service.active_order_assignee_ws_payload(fresh_thread)
        await ws_manager.notify_thread_list_update(
            fresh_thread.company_id,
            fresh_thread.thread_id,
            thread_state=fresh_thread.state.value,
            assistant_mode=fresh_thread.assistant_mode.value,
            extra={"assignee": assignee_payload},
        )

    await order.fetch_related("customer", "assignee__user", "stage")
    return await _order_response(order)


@public_router.post(
    "/{order_id}/close",
    response_model=OrderResponse,
    dependencies=[Depends(require_company_manager)],
)
async def close_order(
    request: OrderCloseRequest,
    order_service: OrderServiceDep,
    current_user: CompanyUser = Depends(require_company_manager),
    company_id: int = Path(..., description="Company ID"),
    order_id: int = Path(..., description="Order ID"),
) -> OrderResponse:
    """Close order with result."""
    order = await order_service.orders_repo.get_by_id(order_id)
    if not order or order.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order.closed_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order already closed")

    order = await order_service.orders_repo.close_order(order, request.result, author_id=current_user.id)
    await order.fetch_related("customer", "assignee__user", "stage")
    return await _order_response(order)


@public_router.get(
    "/customers/{customer_id}/orders",
    response_model=list[OrderResponse],
    dependencies=[Depends(require_company_viewer)],
)
async def list_customer_orders(
    order_service: OrderServiceDep,
    company_id: int = Path(..., description="Company ID"),
    customer_id: int = Path(..., description="Customer ID"),
) -> list[OrderResponse]:
    """List orders for a customer."""
    orders = await order_service.orders_repo.list_by_customer(customer_id)
    scoped = [o for o in orders if o.company_id == company_id]
    for order in scoped:
        await order.fetch_related("customer", "assignee__user", "stage")
    return await _order_responses(scoped)


@public_router.get(
    "/{order_id}/logs",
    response_model=list[OrderLogResponse],
    dependencies=[Depends(require_company_viewer)],
)
async def get_order_logs(
    order_service: OrderServiceDep,
    company_id: int = Path(..., description="Company ID"),
    order_id: int = Path(..., description="Order ID"),
) -> list[OrderLogResponse]:
    """Get order activity history."""
    order = await order_service.orders_repo.get_by_id(order_id)
    if not order or order.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    logs = await order_service.orders_repo.get_logs(order_id)
    return [OrderLogResponse.from_model(log) for log in logs]


@public_router.post(
    "/{order_id}/logs",
    response_model=OrderLogResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_company_manager)],
)
async def add_order_comment(
    request: AddCommentRequest,
    order_service: OrderServiceDep,
    current_user: CompanyUser = Depends(require_company_manager),
    company_id: int = Path(..., description="Company ID"),
    order_id: int = Path(..., description="Order ID"),
) -> OrderLogResponse:
    """Add comment to order."""
    order = await order_service.orders_repo.get_by_id(order_id)
    if not order or order.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    log = await order_service.orders_repo.add_comment(order, request.text, author_id=current_user.id)
    await log.fetch_related("author__user")
    return OrderLogResponse.from_model(log)


@internal_router.get(
    "/by-thread/{thread_id}",
    response_model=OrderContext,
    dependencies=[Depends(require_service_api_key)],
)
async def get_order_by_thread(
    thread_id: str = Path(..., description="Thread ID"),
) -> OrderContext:
    """Get order context for a thread."""
    thread = await Thread.get_or_none(thread_id=thread_id).select_related("active_order__stage")
    if not thread or not thread.active_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active order for thread")

    order = thread.active_order
    stage_name = order.stage.name if order.stage else "Без стадии"
    return OrderContext(
        order_id=order.id,
        order_stage=stage_name,
        order_fields=order.order_fields or {},
    )


@internal_router.patch(
    "/{order_id}/stage",
    response_model=OrderResponse,
    dependencies=[Depends(require_service_api_key)],
)
async def update_order_stage(
    request: OrderStageUpdateRequest,
    order_service: OrderServiceDep,
    order_id: int = Path(..., description="Order ID"),
) -> OrderResponse:
    """Update order stage (internal API for Sales-Agent)."""
    order = await order_service.orders_repo.get_by_id(order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order, _ = await order_service.orders_repo.update_stage_by_id(order, request.stage_id, author_id=None)
    await order.fetch_related("customer", "assignee__user", "stage")
    return await _order_response(order)


@internal_router.post(
    "/{order_id}/close",
    response_model=OrderResponse,
    dependencies=[Depends(require_service_api_key)],
)
async def close_order_internal(
    request: OrderCloseRequest,
    order_service: OrderServiceDep,
    order_id: int = Path(..., description="Order ID"),
) -> OrderResponse:
    """Close order with result (internal API for Sales-Agent)."""
    order = await order_service.orders_repo.get_by_id(order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order.closed_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Order already closed")

    final_stage = await StageTemplate.filter(company_id=order.company_id, is_final=True).first()
    if not final_stage:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No final stage configured for this company"
        )

    # Move order to final stage
    order, _ = await order_service.orders_repo.update_stage_by_id(order, final_stage.id, author_id=None)

    # Close order with result
    order = await order_service.orders_repo.close_order(order, request.result, author_id=None)

    await order.fetch_related("customer", "assignee__user", "stage")
    return await _order_response(order)


@public_router.post(
    "/{order_id}/recalculate-stage",
    response_model=OrderResponse,
    dependencies=[Depends(require_company_manager)],
)
async def recalculate_order_stage(
    order_service: OrderServiceDep,
    company_id: int = Path(..., description="Company ID"),
    order_id: int = Path(..., description="Order ID"),
) -> OrderResponse:
    """Recalculate stage for a single order."""
    order = await order_service.orders_repo.get_by_id(order_id)
    if not order or order.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order = await order_service.recalculate_stage(order.id)
    await order.fetch_related("customer", "assignee__user", "stage")
    return await _order_response(order)


@public_router.patch(
    "/{order_id}/frozen",
    response_model=OrderResponse,
    dependencies=[Depends(require_company_manager)],
)
async def update_order_frozen(
    request: OrderFrozenUpdateRequest,
    order_service: OrderServiceDep,
    company_id: int = Path(..., description="Company ID"),
    order_id: int = Path(..., description="Order ID"),
) -> OrderResponse:
    """Update order frozen status."""
    order = await order_service.orders_repo.get_by_id(order_id)
    if not order or order.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order.frozen = request.frozen
    await order.save(update_fields=["frozen"])
    await order.fetch_related("customer", "assignee__user", "stage")
    return await _order_response(order)


@public_router.post(
    "/{order_id}/stage-requirements",
    response_model=OrderStageRequirementsResponse,
    dependencies=[Depends(require_company_manager)],
)
async def get_order_stage_requirements(
    order_service: OrderServiceDep,
    company_id: int = Path(..., description="Company ID"),
    order_id: int = Path(..., description="Order ID"),
) -> OrderStageRequirementsResponse:
    """Get stage requirements for an order (what fields are needed for next stages)."""
    order = await order_service.orders_repo.get_by_id(order_id)
    if not order or order.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    requirements = await order_service.get_order_stage_requirements(order.id)
    return OrderStageRequirementsResponse(**requirements)


@internal_router.post(
    "/{order_id}/handoff",
    response_model=HandoffResult,
    dependencies=[Depends(require_service_api_key)],
)
async def request_handoff(
    request: HandoffRequest,
    order_service: OrderServiceDep,
    chat_service: ChatServiceDep,
    ws_manager: WebSocketManagerDep,
    order_id: int = Path(..., description="Order ID"),
) -> HandoffResult:
    """Request handoff to manager with load balancing.

    Selects manager using load balancing, assigns to order, and deactivates AI in thread.
    """
    order = await order_service.orders_repo.get_by_id(order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    await order.fetch_related("company", "assignee__user")

    manager = await select_manager(order.company)
    if not manager:
        return HandoffResult(
            success=False,
            manager=None,
            availability=AvailabilityInfo(
                is_working_now=False,
                next_available_at=None,
                next_available_at_local=None,
                next_available_timezone=None,
                schedule_description=None,
            ),
            message_hint=None,
        )

    await manager.fetch_related("user")

    await order_service.orders_repo.update_assignee(order, manager.id, author_id=None)

    thread = await Thread.filter(active_order_id=order_id).first()
    if thread:
        updated_thread, _ = await chat_service.handle_handoff(
            thread_id=thread.thread_id,
            summary=request.summary,
            reason=request.reason,
            escalate=request.escalate,
            cancel_debounce_on_deactivate=False,
        )
        assignee_payload = await chat_service.active_order_assignee_ws_payload(updated_thread)
        await ws_manager.notify_control(
            updated_thread.company_id,
            updated_thread.thread_id,
            {
                "action": "ai_handoff",
                "assistant_mode": updated_thread.assistant_mode.value,
                "state": updated_thread.state.value,
            },
            assistant_mode=updated_thread.assistant_mode.value,
            thread_state=updated_thread.state.value,
            list_extra={"assignee": assignee_payload},
        )

    schedule_info = schedule_service.get_manager_schedule_info(manager)

    if not schedule_info.is_working and schedule_info.next_working_time:
        await on_order_assigned_outside_working_hours(order, manager, schedule_info.next_working_time)

    timezone_str = schedule_info.schedule.timezone if schedule_info.schedule else "UTC"
    next_available_at_local = None
    message_hint = None

    if schedule_info.next_working_time:
        tz = ZoneInfo(timezone_str)
        local_time = schedule_info.next_working_time.astimezone(tz)
        next_available_at_local = local_time.strftime("%Y-%m-%d %H:%M")
        message_hint = order_service.build_message_hint(schedule_info, timezone_str)

    manager_name = manager.get_full_name()

    return HandoffResult(
        success=True,
        manager=ManagerInfo(
            id=manager.id,
            name=manager_name,
            timezone=timezone_str,
        ),
        availability=AvailabilityInfo(
            is_working_now=schedule_info.is_working,
            next_available_at=schedule_info.next_working_time,
            next_available_at_local=next_available_at_local,
            next_available_timezone=timezone_str if schedule_info.schedule else None,
            schedule_description=schedule_info.schedule_description,
        ),
        message_hint=message_hint,
    )
