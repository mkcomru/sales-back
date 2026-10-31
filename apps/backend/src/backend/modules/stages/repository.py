"""Repository for StageTemplate model."""

from __future__ import annotations

from src.backend.modules.core.base_repo import BaseRepository
from src.backend.modules.stages.models import StageTemplate


class StagesRepository(BaseRepository[StageTemplate]):
    """Repository for stage templates."""

    def __init__(self):
        super().__init__(StageTemplate)

    async def list_by_company(self, company_id: int) -> list[StageTemplate]:
        """List all stages for a company, sorted by position."""
        return await self.model.filter(company_id=company_id).order_by("position").all()

    async def get_by_id(self, stage_id: int) -> StageTemplate | None:
        """Get stage by ID."""
        return await self.model.get_or_none(id=stage_id)

    async def get_by_company_and_id(self, company_id: int, stage_id: int) -> StageTemplate | None:
        """Get stage by company and ID."""
        return await self.model.get_or_none(company_id=company_id, id=stage_id)

    async def get_max_position(self, company_id: int) -> int:
        """Get maximum position for company stages."""
        max_stage = await self.model.filter(company_id=company_id).order_by("-position").limit(1).first()
        if max_stage:
            return max_stage.position
        return -1

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

        If creating a non-final stage, final stages will be automatically moved to the end.
        """
        if position is None:
            max_position = await self.get_max_position(company_id)
            position = max_position + 1

        # AICODE-NOTE: If creating non-final stage, ensure final stages stay at the end
        if not is_final:
            # Get all final stages
            final_stages = await self.model.filter(company_id=company_id, is_final=True).order_by("position").all()

            if final_stages:
                # Move final stages to temporary high positions to avoid UNIQUE constraint violations
                for idx, final_stage in enumerate(final_stages):
                    final_stage.position = 10000 + idx
                    await final_stage.save(update_fields=["position"])

        # Create the new stage
        new_stage = await self.model.create(
            company_id=company_id,
            name=name,
            position=position,
            color=color,
            is_final=is_final,
            auto_close=auto_close,
            transition_condition=transition_condition,
        )

        # If we moved final stages, now reposition them properly at the end
        if not is_final and final_stages:
            # Get current max position (excluding final stages)
            max_non_final = await self.model.filter(company_id=company_id, is_final=False).order_by("-position").first()
            next_position = (max_non_final.position + 1) if max_non_final else 0

            # Reposition final stages sequentially after non-final stages
            for final_stage in final_stages:
                final_stage.position = next_position
                await final_stage.save(update_fields=["position"])
                next_position += 1

        return new_stage

    async def update_stage(
        self,
        stage: StageTemplate,
        name: str | None = None,
        color: str | None = None,
        is_final: bool | None = None,
        auto_close: bool | None = None,
        transition_condition: dict | None = None,
    ) -> StageTemplate:
        """Update stage template."""
        update_fields = []
        if name is not None:
            stage.name = name
            update_fields.append("name")
        if color is not None:
            stage.color = color
            update_fields.append("color")
        if is_final is not None:
            stage.is_final = is_final
            update_fields.append("is_final")
        if auto_close is not None:
            stage.auto_close = auto_close
            update_fields.append("auto_close")
        if transition_condition is not None:
            stage.transition_condition = transition_condition
            update_fields.append("transition_condition")

        if update_fields:
            await stage.save(update_fields=update_fields)
        return stage

    async def delete_stage(self, stage: StageTemplate) -> None:
        """Delete stage template."""
        await stage.delete()

    async def reorder_stages(self, company_id: int, stage_ids: list[int]) -> list[StageTemplate]:
        """Reorder stages by assigning new positions based on stage_ids order."""
        stages = await self.model.filter(company_id=company_id, id__in=stage_ids).all()
        stage_dict = {stage.id: stage for stage in stages}

        if len(stages) != len(stage_ids):
            raise ValueError("Some stage IDs not found")

        base = (await self.get_max_position(company_id)) + 1
        for index, stage_id in enumerate(stage_ids):
            stage = stage_dict[stage_id]
            stage.position = base + index
            await stage.save(update_fields=["position"])

        for index, stage_id in enumerate(stage_ids):
            stage = stage_dict[stage_id]
            stage.position = index
            await stage.save(update_fields=["position"])

        return [stage_dict[stage_id] for stage_id in stage_ids]
