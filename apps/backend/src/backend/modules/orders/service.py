"""Service layer for managing orders."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from fastapi import HTTPException, status

from src.backend.core.conditions import evaluate_condition, evaluate_condition_detailed
from src.backend.modules.chat.models import Thread
from src.backend.modules.orders.auto_stage_notify import notify_auto_stage_transition
from src.backend.modules.orders.models import Order, OrderLog, OrderLogType
from src.backend.modules.orders.repository import OrdersRepository
from src.backend.modules.stages.repository import StagesRepository
from src.backend.modules.users.models import CompanyUser
from src.backend.modules.users.schemas import ManagerScheduleInfo

log = structlog.get_logger(__name__)


class OrderService:
    """Service for managing customer orders."""

    def __init__(self):
        self.orders_repo = OrdersRepository()
        self.stages_repo = StagesRepository()

    async def get_order(self, company_id: int, order_id: int) -> Order | None:
        """Get order by company_id and order_id.

        Args:
            company_id: Company ID
            order_id: Order ID

        Returns:
            Order instance or None if not found
        """
        order = await self.orders_repo.get_by_id(order_id)
        if order and order.company_id == company_id:
            return order
        return None

    async def log_event(
        self,
        order_id: int,
        event_type: str,
        data: dict[str, Any],
        author_id: int | None = None,
    ) -> None:
        """Log an event to order history.

        Args:
            order_id: Order ID
            event_type: Event type (OrderLogType enum value or string)
            data: Event data dictionary
            author_id: User who triggered the event (None for system/AI)
        """
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        try:
            log_type = OrderLogType(event_type)
        except ValueError:
            log_type = None

        if log_type:
            await OrderLog.create(
                order=order,
                type=log_type,
                author_id=author_id,
                data=data,
            )
        else:
            log.warning(
                "order.log_event.unknown_type",
                order_id=order_id,
                event_type=event_type,
            )

    async def ensure_active_order(self, thread: Thread) -> Order:
        """Ensure thread has an active order, creating one if needed.

        Called from message router AFTER get_or_create_thread().
        Keeps thread logic and order logic separated.

        Args:
            thread: Thread instance

        Returns:
            Active Order instance
        """
        if thread.active_order_id:
            order = await Order.get(id=thread.active_order_id).select_related("customer", "company")
            if order.closed_at is None:
                return order

        order = await self._create_order(thread)
        thread.active_order = order
        await thread.save(update_fields=["active_order_id"])
        log.info(
            "order.created",
            order_id=order.id,
            order_number=order.order_number,
            thread_id=thread.thread_id,
            customer_id=thread.customer_id,
        )
        return order

    async def create_order(
        self,
        company_id: int,
        customer_id: int,
        assignee_id: int | None = None,
        author_id: int | None = None,
        initial_channel: str | None = None,
    ) -> Order:
        """Create new order with automatic stage assignment.

        Args:
            company_id: Company ID
            customer_id: Customer ID
            assignee_id: Assignee ID (optional)
            author_id: User who created the order (None for system/AI)
            initial_channel: Initial channel (optional)

        Returns:
            Created order with assigned stage

        Raises:
            HTTPException: If assignee_id is provided but not found or doesn't belong to company
        """
        if assignee_id is not None:
            assignee = await CompanyUser.get_or_none(id=assignee_id, company_id=company_id)
            if not assignee:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignee not found")

        order_number = await self.orders_repo.get_next_order_number(company_id)
        order = await self.orders_repo.create_order(
            company_id=company_id,
            customer_id=customer_id,
            order_number=order_number,
            initial_channel=initial_channel,
            assignee_id=assignee_id,
            author_id=author_id,
        )

        # Trigger initial stage assignment
        if not order.frozen:
            order = await self.recalculate_stage(order.id)

        return order

    async def _create_order(self, thread: Thread) -> Order:
        """Create new order for thread."""
        order_number = await self.orders_repo.get_next_order_number(thread.company_id)
        order = await self.orders_repo.create_order(
            company_id=thread.company_id,
            customer_id=thread.customer_id,
            order_number=order_number,
            initial_channel=thread.channel_type,
        )
        # Trigger initial stage assignment
        if not order.frozen:
            order = await self.recalculate_stage(order.id)
        return order

    async def recalculate_stage(self, order_id: int) -> Order:
        """Recalculate order stage based on transition_condition of all company stages.

        Algorithm:
        1. If order.frozen — do nothing
        2. Load all company stages (sorted by position)
        3. Load completed_stages from OrderLog (type=STAGE_CHANGE)
        4. Build context: {order_fields, customer_fields, completed_stages}
        5. Check stages with position > current_position
        6. First matching stage — transition
        7. If is_final + auto_close — close order

        Args:
            order_id: Order ID

        Returns:
            Updated order
        """
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        if order.frozen:
            log.debug("order.stage_recalculation_skipped_frozen", order_id=order_id)
            return order

        if order.closed_at is not None:
            log.debug("order.stage_recalculation_skipped_closed", order_id=order_id)
            return order

        # Load all company stages sorted by position
        stages = await self.stages_repo.list_by_company(order.company_id)
        if not stages:
            log.debug("order.stage_recalculation_no_stages", order_id=order_id, company_id=order.company_id)
            return order

        # Load completed stages from OrderLog
        stage_change_logs = await OrderLog.filter(
            order_id=order_id,
            type=OrderLogType.STAGE_CHANGE,
        ).order_by("created_at")

        completed_stage_ids = []
        completed_stages_by_position = {}
        for log_entry in stage_change_logs:
            log_data = log_entry.data or {}
            to_stage_id = log_data.get("to_stage_id")
            if to_stage_id:
                completed_stage_ids.append(to_stage_id)
                # Find stage position
                for stage in stages:
                    if stage.id == to_stage_id:
                        completed_stages_by_position[stage.position] = to_stage_id
                        break

        # Get current stage position
        current_position = -1
        if order.stage:
            current_position = order.stage.position

        # Load customer fields
        await order.fetch_related("customer")
        customer_fields = order.customer.customer_fields or {}

        # Build context for condition evaluation
        context = {
            "order_fields": order.order_fields or {},
            "customer_fields": customer_fields,
            "completed_stages": completed_stage_ids,
            "completed_stages_by_position": completed_stages_by_position,
        }

        # Check stages with position > current_position to find furthest matching stage
        furthest_matching_stage = None

        for stage in stages:
            if stage.position <= current_position:
                continue

            if not stage.transition_condition:
                continue

            try:
                matches = evaluate_condition(
                    condition=stage.transition_condition,
                    context=context,
                    current_stage_position=current_position,
                )

                if matches:
                    furthest_matching_stage = stage
                    # Continue checking to find furthest stage

            except Exception as e:
                log.warning(
                    "order.stage_condition_evaluation_failed",
                    order_id=order_id,
                    stage_id=stage.id,
                    error=str(e),
                )
                continue

        # Transition to furthest matching stage if found
        if furthest_matching_stage:
            from_stage_id = order.stage.id if order.stage else None
            from_stage_name = order.stage.name if order.stage else "Без стадии"
            to_stage_name = furthest_matching_stage.name
            order, _ = await self.orders_repo.update_stage(order, furthest_matching_stage, author_id=None)
            log.info(
                "order.stage_auto_transitioned",
                order_id=order_id,
                from_stage_id=from_stage_id,
                to_stage_id=furthest_matching_stage.id,
                to_stage_position=furthest_matching_stage.position,
            )
            await notify_auto_stage_transition(order_id, from_stage_name, to_stage_name)

        # Fallback: if order still has no stage and stages exist, assign first stage
        if not order.stage and stages:
            first_stage = stages[0]
            from_stage_name = "Без стадии"
            to_stage_name = first_stage.name
            order, _ = await self.orders_repo.update_stage(order, first_stage, author_id=None)
            log.warning(
                "order.stage_fallback_to_first",
                order_id=order_id,
                stage_id=first_stage.id,
                stage_position=first_stage.position,
                reason="No stage matched conditions, assigned first stage as fallback",
            )
            await notify_auto_stage_transition(order_id, from_stage_name, to_stage_name)

        return order

    async def update_order_fields(
        self, order_id: int, fields_update: dict[str, Any], author_id: int | None = None
    ) -> Order:
        """Update order fields and trigger stage recalculation.

        Args:
            order_id: Order ID
            fields_update: Fields to update
            author_id: User who initiated change (None for system/AI)

        Returns:
            Updated order
        """
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        order = await self.orders_repo.update_fields(order, fields_update, author_id)

        # Trigger auto-transition
        if not order.frozen:
            order = await self.recalculate_stage(order.id)

        return order

    async def get_order_stage_requirements(self, order_id: int) -> dict[str, Any]:
        """Get missing fields for next stages for a given order.

        Analyzes transition_condition of all next stages and determines:
        - Which fields are needed
        - Which fields are missing
        - Condition status (met/partial/blocked)

        Args:
            order_id: Order ID

        Returns:
            Dict with current_stage and next_stages with requirements
        """
        order = await self.orders_repo.get_by_id(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        # Load all company stages sorted by position
        stages = await self.stages_repo.list_by_company(order.company_id)
        if not stages:
            return {
                "current_stage": None,
                "next_stages": [],
            }

        # Get current stage position
        current_position = -1
        current_stage = None
        if order.stage:
            current_stage = order.stage
            current_position = order.stage.position

        # Load customer fields
        await order.fetch_related("customer")
        customer_fields = order.customer.customer_fields or {}
        order_fields = order.order_fields or {}

        # Load completed stages from OrderLog
        stage_change_logs = await OrderLog.filter(
            order_id=order_id,
            type=OrderLogType.STAGE_CHANGE,
        ).order_by("created_at")

        completed_stage_ids = []
        completed_stages_by_position = {}
        for log_entry in stage_change_logs:
            log_data = log_entry.data or {}
            to_stage_id = log_data.get("to_stage_id")
            if to_stage_id:
                completed_stage_ids.append(to_stage_id)
                for stage in stages:
                    if stage.id == to_stage_id:
                        completed_stages_by_position[stage.position] = to_stage_id
                        break

        # Build context for condition evaluation
        context = {
            "order_fields": order_fields,
            "customer_fields": customer_fields,
            "completed_stages": completed_stage_ids,
            "completed_stages_by_position": completed_stages_by_position,
        }

        # Analyze next stages
        next_stages_info = []
        for stage in stages:
            if stage.position <= current_position:
                continue

            if not stage.transition_condition:
                continue

            # Extract field names from condition
            required_fields = self._extract_field_names(stage.transition_condition)

            # Check which fields are missing
            missing_fields = []
            for field_path in required_fields:
                if field_path.startswith("order_fields."):
                    field_name = field_path.replace("order_fields.", "")
                    if field_name not in order_fields or order_fields[field_name] is None:
                        missing_fields.append(field_name)
                elif field_path.startswith("customer_fields."):
                    field_name = field_path.replace("customer_fields.", "")
                    if field_name not in customer_fields or customer_fields[field_name] is None:
                        missing_fields.append(field_name)

            # Determine condition status with detailed report
            condition_report = None
            try:
                report = evaluate_condition_detailed(
                    condition=stage.transition_condition,
                    context=context,
                    current_stage_position=current_position,
                )
                condition_status = "met" if report.overall else "partial"
                condition_report = report
            except Exception:
                condition_status = "blocked"

            from src.backend.modules.stages.schemas import StageInfo

            next_stages_info.append(
                {
                    "stage": StageInfo.from_model(stage),
                    "missing_fields": missing_fields,
                    "condition_status": condition_status,
                    "condition_report": condition_report,
                }
            )

        from src.backend.modules.stages.schemas import StageInfo

        return {
            "current_stage": StageInfo.from_model(current_stage) if current_stage else None,
            "next_stages": next_stages_info,
        }

    def _extract_field_names(self, condition: dict[str, Any]) -> list[str]:
        """Extract field names referenced in condition.

        Args:
            condition: Condition dict (MongoDB-like syntax)

        Returns:
            List of field paths (e.g., ["order_fields.budget", "customer_fields.name"])
        """
        fields = []

        if not isinstance(condition, dict):
            return fields

        for key, value in condition.items():
            if key.startswith("$"):
                # Operator
                if key in {"$and", "$or"}:
                    if isinstance(value, list):
                        for item in value:
                            fields.extend(self._extract_field_names(item))
                elif key == "$not":
                    fields.extend(self._extract_field_names(value))
                elif key in {"$stage_completed", "$prev_stage_completed", "$any"}:
                    pass  # These don't reference fields
            else:
                # Field path
                if key.startswith(("order_fields.", "customer_fields.")):
                    fields.append(key)
                elif isinstance(value, dict):
                    # Field with operator: {"order_fields.budget": {"$gte": 1000}}
                    fields.append(key)
                    for op_key, _ in value.items():
                        if op_key.startswith("$"):
                            pass  # Operator, already handled
                else:
                    # Direct field value: {"order_fields.budget": 1000}
                    if key.startswith(("order_fields.", "customer_fields.")):
                        fields.append(key)

        return list(set(fields))  # Remove duplicates

    @staticmethod
    def get_city_name_from_timezone(tz_str: str) -> str:
        """Extract city name from IANA timezone string.

        Args:
            tz_str: IANA timezone string (e.g., "Europe/Moscow", "America/New_York")

        Returns:
            City name with underscores replaced by spaces (e.g., "Moscow", "New York")
        """
        if "/" in tz_str:
            city = tz_str.split("/")[-1]
            return city.replace("_", " ")
        return tz_str

    @staticmethod
    def build_message_hint(schedule_info: ManagerScheduleInfo, timezone_str: str) -> str | None:
        """Build message hint for manager availability.

        Args:
            schedule_info: Manager schedule information
            timezone_str: IANA timezone string

        Returns:
            Message hint string or None if manager is not available
        """
        if not schedule_info.next_working_time:
            return None

        tz = ZoneInfo(timezone_str)
        local_time = schedule_info.next_working_time.astimezone(tz)
        city_name = OrderService.get_city_name_from_timezone(timezone_str)

        if schedule_info.is_working:
            return f"Менеджер работает сейчас ({city_name} time)"

        today = datetime.now(UTC).date()
        tomorrow = (datetime.now(UTC) + timedelta(days=1)).date()
        next_date = schedule_info.next_working_time.date()

        if next_date == today:
            return f"сегодня в {local_time.strftime('%H:%M')} {city_name} time"
        elif next_date == tomorrow:
            return f"завтра в {local_time.strftime('%H:%M')} {city_name} time"
        else:
            return f"{local_time.strftime('%d.%m')} в {local_time.strftime('%H:%M')} {city_name} time"
