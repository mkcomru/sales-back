"""Service layer for managing stage templates."""

from __future__ import annotations

import structlog

from src.backend.core.conditions import ConditionSyntaxError, validate_condition
from src.backend.modules.orders.models import Order
from src.backend.modules.orders.service import OrderService
from src.backend.modules.stages.models import StageTemplate
from src.backend.modules.stages.repository import StagesRepository
from src.backend.modules.stages.schemas import (
    RecalculateCompanyOrdersStagesResponse,
    RecalculateOrderStageResponse,
)

log = structlog.get_logger(__name__)


class StagesService:
    """Service for managing stage templates."""

    def __init__(self):
        self.stages_repo = StagesRepository()

    async def list_stages(self, company_id: int) -> list[StageTemplate]:
        """List all stages for a company."""
        return await self.stages_repo.list_by_company(company_id)

    async def get_stage(self, company_id: int, stage_id: int) -> StageTemplate | None:
        """Get stage by ID."""
        return await self.stages_repo.get_by_company_and_id(company_id, stage_id)

    async def create_stage(
        self,
        company_id: int,
        name: str,
        position: int | None = None,
        color: str | None = None,
        is_final: bool = False,
        auto_close: bool = False,
        transition_condition: dict | None = None,
    ) -> StageTemplate:
        """Create a new stage template.

        Args:
            company_id: Company ID
            name: Stage name
            position: Position in funnel (auto-assigned if None)
            color: HEX color code
            is_final: Is this a final stage
            auto_close: Auto-close order when transitioning (only if is_final=True)
            transition_condition: MongoDB-like condition for auto-transition

        Returns:
            Created StageTemplate

        Raises:
            ValueError: If validation fails (constraints, condition syntax)
        """
        if transition_condition is not None:
            try:
                validate_condition(transition_condition)
            except ConditionSyntaxError as e:
                raise ValueError(f"Invalid transition_condition: {e}") from e

        if auto_close and not is_final:
            raise ValueError("auto_close is only allowed when is_final=True")

        return await self.stages_repo.create_stage(
            company_id=company_id,
            name=name,
            position=position,
            color=color,
            is_final=is_final,
            auto_close=auto_close,
            transition_condition=transition_condition,
        )

    async def update_stage(
        self,
        stage: StageTemplate,
        name: str | None = None,
        color: str | None = None,
        is_final: bool | None = None,
        auto_close: bool | None = None,
        transition_condition: dict | None = None,
    ) -> StageTemplate:
        """Update stage template.

        Args:
            stage: StageTemplate instance
            name: Stage name
            color: HEX color code
            is_final: Is this a final stage
            auto_close: Auto-close order when transitioning
            transition_condition: MongoDB-like condition for auto-transition

        Returns:
            Updated StageTemplate

        Raises:
            ValueError: If validation fails (constraints, condition syntax)
        """
        if transition_condition is not None:
            try:
                validate_condition(transition_condition)
            except ConditionSyntaxError as e:
                raise ValueError(f"Invalid transition_condition: {e}") from e

        new_is_final = is_final if is_final is not None else stage.is_final
        new_auto_close = auto_close if auto_close is not None else stage.auto_close

        if new_auto_close and not new_is_final:
            raise ValueError("auto_close is only allowed when is_final=True")

        return await self.stages_repo.update_stage(
            stage=stage,
            name=name,
            color=color,
            is_final=is_final,
            auto_close=auto_close,
            transition_condition=transition_condition,
        )

    async def delete_stage(self, stage: StageTemplate) -> None:
        """Delete stage template.

        Raises:
            ValueError: If attempting to delete a system stage
        """
        if stage.is_system:
            raise ValueError("Cannot delete system stage")

        await self.stages_repo.delete_stage(stage)

    async def reorder_stages(self, company_id: int, stage_ids: list[int]) -> list[StageTemplate]:
        """Reorder stages by assigning new positions.

        Args:
            company_id: Company ID
            stage_ids: Stage IDs in desired order

        Returns:
            Reordered stages

        Raises:
            ValueError: If some stage IDs not found
        """
        return await self.stages_repo.reorder_stages(company_id, stage_ids)

    async def create_default_stages(self, company_id: int) -> list[StageTemplate]:
        """Create default stage funnel for new company.

        Creates 5 default stages:
        - "Новый" (position 0) - fallback stage with $any condition
        - "Квалификация" (position 1)
        - "Предложение" (position 2)
        - "Закрыто (успешно)" (position 3) - final, won, auto_close
        - "Отказ" (position 4) - final, lost, auto_close

        Args:
            company_id: Company ID

        Returns:
            List of created StageTemplate instances
        """
        defaults = [
            {
                "name": "Новый",
                "position": 0,
                "color": "#64748b",
                "transition_condition": {"$any": True},
                "is_system": True,
            },
            {
                "name": "Закрыто",
                "position": 1,
                "color": "#10b981",
                "is_final": True,
                "auto_close": True,
                "transition_condition": None,
                "is_system": True,
            },
        ]

        # Create all stages in a single batch operation
        stage_instances = [
            StageTemplate(
                company_id=company_id,
                name=stage_data["name"],
                position=stage_data["position"],
                color=stage_data["color"],
                is_final=stage_data.get("is_final", False),
                auto_close=stage_data.get("auto_close", False),
                transition_condition=stage_data.get("transition_condition"),
                is_system=stage_data.get("is_system", False),
            )
            for stage_data in defaults
        ]

        # bulk_create returns None in Tortoise ORM, need to query created stages
        await StageTemplate.bulk_create(stage_instances)

        # Fetch created stages
        created_stages = await StageTemplate.filter(company_id=company_id).order_by("position").all()

        log.info(
            "stages.default_created",
            company_id=company_id,
            count=len(created_stages),
            stage_names=[s.name for s in created_stages],
        )

        return created_stages

    async def recalculate_company_orders_stages(self, company_id: int) -> RecalculateCompanyOrdersStagesResponse:
        """Recalculate stages for all active orders in a company.

        Args:
            company_id: Company ID

        Returns:
            RecalculateCompanyOrdersStagesResponse with statistics
        """

        orders_service = OrderService()
        active_orders = await Order.filter(
            company_id=company_id,
            closed_at__isnull=True,
        ).all()

        processed = 0
        transitions = 0
        errors = 0

        for order in active_orders:
            if order.frozen:
                continue

            try:
                await order.fetch_related("stage")
                previous_stage_id = order.stage.id if order.stage else None
                order = await orders_service.recalculate_stage(order.id)
                new_stage_id = order.stage.id if order.stage else None

                if previous_stage_id != new_stage_id:
                    transitions += 1

                processed += 1
            except Exception as e:
                errors += 1
                log.warning(
                    "stages.recalculate_order_failed",
                    order_id=order.id,
                    company_id=company_id,
                    error=str(e),
                )

        log.info(
            "stages.recalculate_company_completed",
            company_id=company_id,
            processed=processed,
            transitions=transitions,
            errors=errors,
        )

        return RecalculateCompanyOrdersStagesResponse(
            processed=processed,
            transitions=transitions,
            errors=errors,
        )

    async def recalculate_order_stage(self, order_id: int) -> RecalculateOrderStageResponse:
        """Recalculate stage for a single order.

        Args:
            order_id: Order ID

        Returns:
            RecalculateOrderStageResponse with result
        """
        orders_service = OrderService()
        try:
            order = await orders_service.recalculate_stage(order_id)
            return RecalculateOrderStageResponse(
                success=True,
                message="Stage recalculated successfully",
                order_id=order_id,
                stage_id=order.stage.id if order.stage else None,
            )
        except ValueError as e:
            return RecalculateOrderStageResponse(
                success=False,
                message=str(e),
                order_id=order_id,
                stage_id=None,
            )
        except Exception as e:
            log.exception("stages.recalculate_order_failed", order_id=order_id, error=str(e))
            return RecalculateOrderStageResponse(
                success=False,
                message=f"Failed to recalculate stage: {e}",
                order_id=order_id,
                stage_id=None,
            )
