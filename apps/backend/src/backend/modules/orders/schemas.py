"""Pydantic schemas for Order API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.backend.core.conditions.report import ConditionReport
from src.backend.modules.billing.models import BillingStatus
from src.backend.modules.orders.models import Order, OrderLog, OrderResult
from src.backend.modules.stages.schemas import StageInfo


class OrderBase(BaseModel):
    """Base order schema."""

    name: str | None = None
    stage_id: int | None = Field(None, description="Stage template ID")
    order_fields: dict[str, Any] = Field(default_factory=dict)


class OrderCreateRequest(OrderBase):
    """Request to create a new order."""

    customer_id: int = Field(description="Customer ID")
    assignee_id: int | None = None
    initial_channel: str | None = None


class OrderUpdateRequest(BaseModel):
    """Request to update order."""

    name: str | None = None
    stage_id: int | None = Field(None, description="Stage template ID (null to unset)")
    order_fields: dict[str, Any] | None = None
    extra_fields: dict[str, Any] | None = None


class OrderCloseRequest(BaseModel):
    """Request to close order."""

    result: OrderResult = Field(description="Order result (won/lost)")


class AssigneeInfo(BaseModel):
    """Assignee information."""

    id: int
    user_id: int
    first_name: str
    last_name: str
    email: str
    role: str


class CustomerInfo(BaseModel):
    """Customer information."""

    id: int
    user_id: str
    name: str | None


class OrderResponse(BaseModel):
    """Order response schema."""

    id: int
    order_number: int
    name: str | None
    customer: CustomerInfo
    assignee: AssigneeInfo | None
    stage: StageInfo | None
    order_fields: dict[str, Any]
    extra_fields: dict[str, Any]
    initial_channel: str | None
    result: OrderResult | None
    billing_status: BillingStatus
    charged_at: datetime | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    frozen: bool
    thread_id: str | None = Field(None, description="Thread that currently owns this order as active_order")
    assistant_mode: str | None = Field(
        None,
        description="AI assistant mode for the linked thread (active/shadowing/inactive); null if no linked thread",
    )

    @classmethod
    def from_model(
        cls,
        order: Order,
        *,
        thread_id: str | None = None,
        assistant_mode: str | None = None,
    ) -> OrderResponse:
        """Convert Order model to OrderResponse schema."""
        customer_info = CustomerInfo(
            id=order.customer.id,
            user_id=order.customer.user_id,
            name=order.customer.name,
        )
        assignee_info = None
        if order.assignee:
            assignee_info = AssigneeInfo(
                id=order.assignee.id,
                user_id=order.assignee.user.id,
                first_name=order.assignee.user.first_name,
                last_name=order.assignee.user.last_name,
                email=order.assignee.user.email,
                role=order.assignee.role.value,
            )
        stage_info = None
        if order.stage:
            stage_info = StageInfo.from_model(order.stage)
        return cls(
            id=order.id,
            order_number=order.order_number,
            name=order.name,
            customer=customer_info,
            assignee=assignee_info,
            stage=stage_info,
            order_fields=order.order_fields or {},
            extra_fields=order.extra_fields or {},
            initial_channel=order.initial_channel,
            result=order.result,
            billing_status=order.billing_status,
            charged_at=order.charged_at,
            created_at=order.created_at,
            updated_at=order.updated_at,
            closed_at=order.closed_at,
            frozen=order.frozen,
            thread_id=thread_id,
            assistant_mode=assistant_mode,
        )


class OrderContext(BaseModel):
    """Order context for Sales-Agent."""

    order_id: int
    order_stage: str
    order_fields: dict[str, Any]


class OrderStageUpdateRequest(BaseModel):
    """Request to update order stage."""

    stage_id: int | None = Field(None, description="Stage template ID (null to unset)")


class OrderFieldsUpdateRequest(BaseModel):
    """Request to update order fields."""

    fields: dict[str, Any] = Field(description="Fields to update")


class OrderAssigneeUpdateRequest(BaseModel):
    """Request to update order assignee."""

    assignee_id: int | None = Field(description="Assignee ID (null to unassign)")


class OrderLogResponse(BaseModel):
    """Order activity log response."""

    id: int
    type: str
    author: AssigneeInfo | None
    data: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_model(cls, log: OrderLog) -> OrderLogResponse:
        """Convert OrderLog model to response schema."""
        author_info = None
        if log.author:
            author_info = AssigneeInfo(
                id=log.author.id,
                user_id=log.author.user.id,
                first_name=log.author.user.first_name,
                last_name=log.author.user.last_name,
                email=log.author.user.email,
                role=log.author.role.value,
            )
        return cls(
            id=log.id,
            type=log.type.value,
            author=author_info,
            data=log.data,
            created_at=log.created_at,
        )


class AddCommentRequest(BaseModel):
    """Request to add comment to order."""

    text: str = Field(min_length=1, max_length=2000, description="Comment text")


class OrderFrozenUpdateRequest(BaseModel):
    """Request to update order frozen status."""

    frozen: bool = Field(description="Whether to freeze the order (disable auto-transitions)")


class NextStageInfo(BaseModel):
    """Information about next stage requirements."""

    stage: StageInfo
    missing_fields: list[str] = Field(default_factory=list, description="Fields needed for transition")
    condition_status: str = Field(description="Condition status: 'met', 'partial', or 'blocked'")
    condition_report: ConditionReport | None = None


class OrderStageRequirementsResponse(BaseModel):
    """Response for stage requirements endpoint."""

    current_stage: StageInfo | None
    next_stages: list[NextStageInfo] = Field(default_factory=list)


class ManagerInfo(BaseModel):
    """Manager information for handoff."""

    id: int
    name: str
    timezone: str


class AvailabilityInfo(BaseModel):
    """Manager availability information."""

    is_working_now: bool
    next_available_at: datetime | None = Field(None, description="Next available time in UTC")
    next_available_at_local: str | None = Field(
        None, description="Next available time in manager timezone (format: YYYY-MM-DD HH:MM)"
    )
    next_available_timezone: str | None = Field(None, description="Manager timezone")
    schedule_description: str | None = Field(None, description="Human-readable schedule description")


class HandoffRequest(BaseModel):
    """Request for handoff."""

    summary: str = Field(default="Передача менеджеру", description="Brief conversation summary")
    reason: str = Field(default="Требуется участие менеджера", description="Reason for handoff")
    escalate: bool = Field(
        default=False, description="Hard handoff: AI stops immediately. Soft: AI continues in shadowing mode."
    )


class HandoffResult(BaseModel):
    """Result of handoff request."""

    success: bool
    manager: ManagerInfo | None = None
    availability: AvailabilityInfo
    message_hint: str | None = Field(
        None, description="Hint for AI agent message (e.g., 'tomorrow at 09:00 Moscow time')"
    )
