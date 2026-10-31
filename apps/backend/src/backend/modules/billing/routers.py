"""Billing API routes."""

from __future__ import annotations

from datetime import datetime

import structlog
from fastapi import APIRouter, HTTPException, Query, status

from common.models.pagination import PaginatedResponse

from src.backend.modules.auth.dependencies import CompanyAdminDep, SuperuserDep
from src.backend.modules.billing.dependencies import BillingServiceDep
from src.backend.modules.billing.models import BillingStatus, OperationType
from src.backend.modules.billing.schemas import (
    BalanceResponse,
    ChargeResult,
    LedgerEntryResponse,
    LedgerListResponse,
    ReactivateThreadsRequest,
    ReactivateThreadsResponse,
    TopUpRequest,
    TopUpResponse,
)
from src.backend.modules.chat.dependencies import ChatServiceDep
from src.backend.modules.chat.models import Thread
from src.backend.modules.chat.schemas import ChatThreadSummary, OrderSummary, ThreadState
from src.backend.modules.transport.models import Connector

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/companies/{company_id}/billing", tags=["billing"])


@router.post(
    "/top-up",
    status_code=status.HTTP_200_OK,
    response_model=TopUpResponse,
    responses={
        400: {"description": "Invalid request"},
        403: {"description": "Superuser access required"},
        404: {"description": "Company not found"},
    },
)
async def top_up_balance(
    company_id: int,
    superuser: SuperuserDep,
    billing_service: BillingServiceDep,
    request: TopUpRequest,
) -> TopUpResponse:
    """Top up company balance (superuser only)."""
    if request.amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Amount must be greater than 0",
        )

    try:
        balance_id, ledger_entry_id = await billing_service.top_up(
            company_id=company_id,
            amount=request.amount,
            operator_id=request.operator_id,
            comment=request.comment,
        )
        balance, _ = await billing_service.get_balance(company_id)

        return TopUpResponse(
            balance_id=balance_id,
            ledger_entry_id=ledger_entry_id,
            new_balance=balance,
            amount_added=request.amount,
        )
    except Exception as exc:
        log.error("billing.top_up.error", company_id=company_id, error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to top up balance",
        ) from exc


@router.get(
    "/balance",
    status_code=status.HTTP_200_OK,
    response_model=BalanceResponse,
    responses={
        403: {"description": "Access denied"},
        404: {"description": "Company not found"},
    },
)
async def get_balance(
    admin: CompanyAdminDep,
    billing_service: BillingServiceDep,
) -> BalanceResponse:
    """Get company balance."""
    balance, balance_warning = await billing_service.get_balance(admin.company_id)
    balance_obj = await billing_service.billing_repo.get_or_create_balance(admin.company_id)

    return BalanceResponse(
        company_id=admin.company_id,
        balance=balance,
        balance_warning=balance_warning,
        updated_at=balance_obj.updated_at,
    )


@router.get(
    "/ledger",
    status_code=status.HTTP_200_OK,
    response_model=LedgerListResponse,
    responses={
        403: {"description": "Access denied"},
        404: {"description": "Company not found"},
    },
)
async def get_ledger(
    admin: CompanyAdminDep,
    billing_service: BillingServiceDep,
    operation_type: OperationType | None = Query(None, description="Filter by operation type"),
    from_date: datetime | None = Query(None, description="Filter from date"),
    to_date: datetime | None = Query(None, description="Filter to date"),
    order_id: int | None = Query(None, description="Filter by order ID"),
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> LedgerListResponse:
    """Get paginated ledger entries for company."""
    entries, total = await billing_service.ledger_repo.list_by_company(
        company_id=admin.company_id,
        operation_type=operation_type,
        from_date=from_date,
        to_date=to_date,
        order_id=order_id,
        limit=limit,
        offset=offset,
    )

    return LedgerListResponse(
        entries=[
            LedgerEntryResponse(
                id=entry.id,
                company_id=entry.company_id,
                operation_type=entry.operation_type,
                amount=entry.amount,
                timestamp=entry.timestamp,
                initiated_by=entry.initiated_by,
                operator_id=entry.operator_id,
                comment=entry.comment,
                order_id=entry.order_id,
                channel_type=entry.channel_type,
                conversation_id=entry.conversation_id,
            )
            for entry in entries
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/threads/billing-hold",
    status_code=status.HTTP_200_OK,
    response_model=PaginatedResponse[ChatThreadSummary],
    responses={
        403: {"description": "Access denied"},
        404: {"description": "Company not found"},
    },
)
async def list_billing_hold_threads(
    company_id: int,
    admin: CompanyAdminDep,
    chat_service: ChatServiceDep,
    limit: int = Query(50, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> PaginatedResponse[ChatThreadSummary]:
    """List threads with billing_hold status for the company."""
    threads = (
        await Thread.filter(
            company_id=admin.company_id,
            active_order__billing_status=BillingStatus.BILLING_HOLD,
        )
        .prefetch_related("customer", "active_order")
        .limit(limit)
        .offset(offset)
        .all()
    )

    total = await Thread.filter(
        company_id=admin.company_id,
        active_order__billing_status=BillingStatus.BILLING_HOLD,
    ).count()

    thread_ids = [t.thread_id for t in threads]
    last_messages_map = await chat_service.get_last_messages_batch(thread_ids)

    connector_ids = list({t.connector_id for t in threads if t.connector_id})
    connector_by_id: dict[str, Connector] = {}
    if connector_ids:
        connectors = await Connector.filter(connector_id__in=connector_ids).only("connector_id", "type").all()
        connector_by_id = {c.connector_id: c for c in connectors}

    items = []
    for thread in threads:
        if thread.active_order:
            await thread.active_order.fetch_related("stage", "assignee__user")
        order_summary = OrderSummary.from_model(thread.active_order) if thread.active_order else None

        last_message = last_messages_map.get(thread.thread_id)
        billing_status = thread.active_order.billing_status if thread.active_order else BillingStatus.ACTIVE
        conn = connector_by_id.get(thread.connector_id) if thread.connector_id else None
        transport = conn.type.value if conn is not None else None
        items.append(
            ChatThreadSummary(
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
            )
        )

    return PaginatedResponse[ChatThreadSummary](
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/threads/{thread_id}/reactivate",
    status_code=status.HTTP_200_OK,
    response_model=ReactivateThreadsResponse,
    responses={
        403: {"description": "Access denied"},
        404: {"description": "Thread not found"},
    },
)
async def reactivate_thread(
    company_id: int,
    thread_id: str,
    admin: CompanyAdminDep,
    billing_service: BillingServiceDep,
) -> ReactivateThreadsResponse:
    """Reactivate a single thread that was on billing hold."""
    thread = await Thread.filter(thread_id=thread_id, company_id=admin.company_id).first()
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found",
        )

    result = await billing_service.reactivate_thread(admin.company_id, thread.id)
    balance, _ = await billing_service.get_balance(admin.company_id)

    return ReactivateThreadsResponse(
        results={thread.id: result},
        new_balance=balance,
    )


@router.post(
    "/threads/reactivate",
    status_code=status.HTTP_200_OK,
    response_model=ReactivateThreadsResponse,
    responses={
        400: {"description": "Invalid request"},
        403: {"description": "Access denied"},
    },
)
async def reactivate_threads(
    admin: CompanyAdminDep,
    billing_service: BillingServiceDep,
    request: ReactivateThreadsRequest,
) -> ReactivateThreadsResponse:
    """Reactivate multiple threads that were on billing hold."""
    threads = await Thread.filter(
        thread_id__in=request.thread_ids,
        company_id=admin.company_id,
    ).all()

    if len(threads) != len(request.thread_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Some threads not found or belong to different company",
        )

    thread_db_ids = [t.id for t in threads]
    results = await billing_service.reactivate_threads(admin.company_id, thread_db_ids)
    balance, _ = await billing_service.get_balance(admin.company_id)

    thread_id_map = {t.id: t.thread_id for t in threads}
    results_by_thread_id: dict[str, ChargeResult] = {}
    for db_id, result in results.items():
        thread_id = thread_id_map.get(db_id)
        if thread_id:
            results_by_thread_id[thread_id] = result

    return ReactivateThreadsResponse(
        results=results_by_thread_id,
        new_balance=balance,
    )
