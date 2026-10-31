"""Repository for Order model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from tortoise.exceptions import IntegrityError

from src.backend.modules.core.base_repo import BaseRepository
from src.backend.modules.fields.models import Field, FieldLevel
from src.backend.modules.orders.models import Order, OrderLog, OrderLogType, OrderResult
from src.backend.modules.stages.models import StageTemplate
from src.backend.modules.tasks.models import Task, TaskSubjectType
from src.backend.modules.users.models import CompanyUser

log = structlog.get_logger(__name__)


class OrdersRepository(BaseRepository[Order]):
    def __init__(self):
        super().__init__(Order)

    async def get_by_id(self, order_id: int) -> Order | None:
        """Get order by ID."""
        order = await self.model.get_or_none(id=order_id)
        if order:
            await order.fetch_related("customer", "company", "assignee", "stage")
        return order

    async def get_by_company_and_number(self, company_id: int, order_number: int) -> Order | None:
        """Get order by company and order number."""
        return await self.model.get_or_none(company_id=company_id, order_number=order_number)

    async def get_active_order(self, customer_id: int) -> Order | None:
        """Get active (non-closed) order for customer."""
        return await self.model.filter(customer_id=customer_id, closed_at__isnull=True).first()

    async def list_by_company(self, company_id: int, limit: int = 100, offset: int = 0) -> list[Order]:
        """List orders for a company."""
        return (
            await self.model.filter(company_id=company_id)
            .order_by("-created_at")
            .limit(limit)
            .offset(offset)
            .select_related("customer", "assignee", "stage")
        )

    async def list_by_customer(self, customer_id: int) -> list[Order]:
        """List all orders for a customer."""
        return (
            await self.model.filter(customer_id=customer_id).order_by("-created_at").select_related("assignee", "stage")
        )

    async def get_next_order_number(self, company_id: int) -> int:
        """Get next order number for company.

        Uses MAX aggregation and handles race conditions by retrying on IntegrityError.
        """
        max_order_obj = await self.model.filter(company_id=company_id).order_by("-order_number").limit(1).first()
        current_max = max_order_obj.order_number if max_order_obj else 0
        return current_max + 1

    async def create_order(
        self,
        company_id: int,
        customer_id: int,
        order_number: int,
        initial_channel: str | None = None,
        assignee_id: int | None = None,
        author_id: int | None = None,
    ) -> Order:
        """Create new order.

        Args:
            company_id: Company ID
            customer_id: Customer ID
            order_number: Order number
            initial_channel: Initial channel (e.g. "telegram", "whatsapp")
            assignee_id: Assignee ID (optional)
            author_id: User who created the order (None for system/AI)

        Returns:
            Created order

        Retries on unique constraint violation (concurrent order_number generation).
        """
        max_retries = 5
        last_error: IntegrityError | None = None
        for attempt in range(max_retries):
            try:
                order = await self.model.create(
                    company_id=company_id,
                    customer_id=customer_id,
                    order_number=order_number,
                    initial_channel=initial_channel,
                    assignee_id=assignee_id,
                )

                if assignee_id:
                    await CompanyUser.filter(id=assignee_id).update(last_assigned_at=datetime.now(tz=UTC))

                await OrderLog.create(
                    order=order,
                    type=OrderLogType.ORDER_CREATED,
                    author_id=author_id,
                    data={
                        "order_number": order_number,
                        "initial_channel": initial_channel,
                        "assignee_id": assignee_id,
                    },
                )

                return order
            except IntegrityError as e:
                last_error = e
                if attempt == max_retries - 1:
                    raise
                order_number = await self.get_next_order_number(company_id)

        if last_error:
            raise last_error
        raise RuntimeError("Failed to create order after retries")

    async def update_stage(
        self, order: Order, stage: StageTemplate | None, author_id: int | None = None
    ) -> tuple[Order, StageTemplate | None]:
        """Update order stage.

        Args:
            order: Order instance
            stage: New stage template (None to unset)
            author_id: User who initiated change (None for system/AI)

        Returns:
            Tuple of (updated_order, previous_stage)
        """
        previous_stage = order.stage
        previous_stage_id = previous_stage.id if previous_stage else None
        order.stage = stage
        await order.save(update_fields=["stage_id"])

        await OrderLog.create(
            order=order,
            type=OrderLogType.STAGE_CHANGE,
            author_id=author_id,
            data={
                "from_stage_id": previous_stage_id,
                "to_stage_id": stage.id if stage else None,
                "trigger": "manual" if author_id else "auto",
            },
        )

        if previous_stage_id:
            from src.backend.modules.pings.models import PingRule

            rule_ids = await PingRule.filter(stage_id=previous_stage_id).values_list("id", flat=True)
            if rule_ids:
                cancelled = await Task.filter(
                    subject_type=TaskSubjectType.ORDER,
                    subject_id=order.id,
                    ping_rule_id__in=rule_ids,
                    completed=False,
                    cancelled_at__isnull=True,
                ).update(cancelled_at=datetime.now(UTC))
                if cancelled:
                    log.info(
                        "pings.cancelled_on_stage_change",
                        order_id=order.id,
                        stage_id=previous_stage_id,
                        count=cancelled,
                    )

        return order, previous_stage

    async def update_stage_by_id(
        self, order: Order, stage_id: int | None, author_id: int | None = None
    ) -> tuple[Order, StageTemplate | None]:
        """Update order stage by stage_id.

        Args:
            order: Order instance
            stage_id: New stage template ID (None to unset)
            author_id: User who initiated change (None for system/AI)

        Returns:
            Tuple of (updated_order, previous_stage)
        """
        stage = None
        if stage_id is not None:
            stage = await StageTemplate.get_or_none(id=stage_id)
            if not stage:
                raise ValueError(f"Stage template {stage_id} not found")

        return await self.update_stage(order, stage, author_id)

    async def update_fields(self, order: Order, fields: dict[str, Any], author_id: int | None = None) -> Order:
        """Update order_fields JSON field.

        Args:
            order: Order instance
            fields: Fields to update
            author_id: User who initiated change (None for system/AI)

        Returns:
            Updated order
        """
        current_fields = order.order_fields or {}
        logs_to_create = []

        for field_name, new_value in fields.items():
            old_value = current_fields.get(field_name)
            if old_value != new_value:
                logs_to_create.append(
                    OrderLog(
                        order=order,
                        type=OrderLogType.FIELD_CHANGE,
                        author_id=author_id,
                        data={
                            "field": field_name,
                            "level": "order",
                            "old": old_value,
                            "new": new_value,
                        },
                    )
                )

        if logs_to_create:
            await OrderLog.bulk_create(logs_to_create)

        current_fields.update(fields)
        order.order_fields = current_fields
        await order.save(update_fields=["order_fields"])
        return order

    async def update_extra_fields(self, order: Order, updates: dict[str, Any]) -> tuple[Order, dict[str, Any]]:
        """Update extra_fields JSON field (AI-discovered non-schema fields).

        Returns:
            Tuple of (updated_order, changed_fields)
        """
        current = order.extra_fields or {}
        changed: dict[str, Any] = {}

        for key, value in updates.items():
            old = current.get(key)
            if old != value:
                changed[key] = {"old": old, "new": value}
                if value is None:
                    current.pop(key, None)
                else:
                    current[key] = value

        if changed:
            order.extra_fields = current
            await order.save(update_fields=["extra_fields"])

        return order, changed

    async def update_assignee(
        self, order: Order, assignee_id: int | None, author_id: int | None = None
    ) -> tuple[Order, int | None]:
        """Update order assignee.

        Args:
            order: Order instance
            assignee_id: New assignee ID (None to unassign)
            author_id: User who initiated change (None for system/AI)

        Returns:
            Tuple of (updated_order, previous_assignee_id)
        """
        previous_assignee_id = order.assignee_id
        order.assignee_id = assignee_id
        await order.save(update_fields=["assignee_id"])

        if assignee_id:
            await CompanyUser.filter(id=assignee_id).update(last_assigned_at=datetime.now(tz=UTC))

        await OrderLog.create(
            order=order,
            type=OrderLogType.ASSIGNEE_CHANGE,
            author_id=author_id,
            data={
                "from_user_id": previous_assignee_id,
                "to_user_id": assignee_id,
            },
        )

        return order, previous_assignee_id

    async def close_order(self, order: Order, result: OrderResult, author_id: int | None = None) -> Order:
        """Close order with result.

        Args:
            order: Order instance
            result: Order result (WON/LOST)
            author_id: User who initiated change (None for system/AI)

        Returns:
            Closed order
        """
        previous_stage = order.stage
        previous_stage_id = previous_stage.id if previous_stage else None
        order.result = result
        order.closed_at = datetime.now(tz=UTC)
        await order.save(update_fields=["result", "closed_at"])

        await OrderLog.create(
            order=order,
            type=OrderLogType.STAGE_CHANGE,
            author_id=author_id,
            data={
                "from_stage_id": previous_stage_id,
                "to_stage_id": previous_stage_id,
                "trigger": "system",
                "result": result.value,
            },
        )

        return order

    async def add_comment(self, order: Order, text: str, author_id: int) -> OrderLog:
        """Add comment to order.

        Args:
            order: Order instance
            text: Comment text
            author_id: User who created comment

        Returns:
            Created OrderLog
        """
        return await OrderLog.create(
            order=order,
            type=OrderLogType.COMMENT,
            author_id=author_id,
            data={"text": text},
        )

    async def get_logs(self, order_id: int) -> list[OrderLog]:
        """Get activity logs for order.

        Args:
            order_id: Order ID

        Returns:
            List of OrderLog entries ordered by created_at desc
        """
        return await OrderLog.filter(order_id=order_id).order_by("-created_at").select_related("author__user")

    async def _ensure_all_order_fields_present(self, order: Order) -> bool:
        """Ensure order has all order-level fields in order_fields.

        Args:
            order: Order instance to check and update

        Returns:
            True if any fields were added, False otherwise
        """
        fields = await Field.filter(company_id=order.company_id, level=FieldLevel.ORDER).all()
        order_fields = order.order_fields or {}
        updated = False

        for field in fields:
            if field.name not in order_fields:
                order_fields[field.name] = None
                updated = True

        if updated:
            order.order_fields = order_fields

        return updated
