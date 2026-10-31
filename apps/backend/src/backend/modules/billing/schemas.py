"""Billing request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field

from src.backend.modules.billing.models import BillingStatus, InitiatedBy, OperationType


class TopUpRequest(BaseModel):
    """Request to top up company balance."""

    amount: int = Field(..., gt=0, description="Amount to add (must be > 0)")
    comment: str | None = Field(None, description="Optional comment")
    operator_id: int | None = Field(None, description="Operator ID (for manual operations)")


class TopUpResponse(BaseModel):
    """Response after top-up."""

    balance_id: int
    ledger_entry_id: int
    new_balance: int
    amount_added: int


class BalanceResponse(BaseModel):
    """Company balance response."""

    company_id: int
    balance: int
    balance_warning: bool
    updated_at: datetime


class LedgerEntryResponse(BaseModel):
    """Ledger entry response."""

    id: int
    company_id: int
    operation_type: OperationType
    amount: int
    timestamp: datetime
    initiated_by: InitiatedBy
    operator_id: int | None
    comment: str | None
    order_id: int | None
    channel_type: str | None
    conversation_id: str | None


class LedgerListResponse(BaseModel):
    """Paginated ledger list response."""

    entries: list[LedgerEntryResponse]
    total: int
    limit: int
    offset: int


class ChargeResult(BaseModel):
    """Result of charge operation."""

    success: bool
    new_balance: int
    ledger_entry_id: int | None
    already_charged: bool
    billing_status: BillingStatus


class ReactivateThreadsRequest(BaseModel):
    """Request to reactivate threads."""

    thread_ids: list[str] = Field(..., min_length=1, description="List of thread_id strings to reactivate")


class ReactivateThreadsResponse(BaseModel):
    """Response after reactivating threads."""

    results: dict[str, ChargeResult] = Field(description="Mapping of thread_id (string) to ChargeResult")
    new_balance: int = Field(description="Current balance after reactivation attempts")
