"""Repository for PingRule model."""

from __future__ import annotations

from src.backend.modules.core.base_repo import BaseRepository
from src.backend.modules.pings.models import PingRule


class PingRuleRepository(BaseRepository[PingRule]):
    def __init__(self):
        super().__init__(PingRule)

    async def get_by_id(self, rule_id: int) -> PingRule | None:
        return await self.model.get_or_none(id=rule_id)

    async def get_rules_for_stage(self, stage_id: int, *, active_only: bool = False) -> list[PingRule]:
        query = self.model.filter(stage_id=stage_id)
        if active_only:
            query = query.filter(is_active=True)
        return await query.order_by("position")

    async def count_rules_for_stage(self, stage_id: int) -> int:
        return await self.model.filter(stage_id=stage_id).count()

    async def create_rule(
        self,
        company_id: int,
        stage_id: int,
        **kwargs,
    ) -> PingRule:
        return await self.model.create(
            company_id=company_id,
            stage_id=stage_id,
            **kwargs,
        )

    async def delete_rule(self, rule_id: int) -> bool:
        rule = await self.model.get_or_none(id=rule_id)
        if not rule:
            return False
        await rule.delete()
        return True
