"""Business logic for ping rules."""

from __future__ import annotations

import structlog
from fastapi import HTTPException, status

from src.backend.modules.pings.enums import PingContentType
from src.backend.modules.pings.models import MAX_PINGS_PER_STAGE, PingRule
from src.backend.modules.pings.repository import PingRuleRepository
from src.backend.modules.pings.schemas import PingRuleCreateRequest, PingRuleUpdateRequest
from src.backend.modules.stages.models import StageTemplate
from src.backend.modules.tasks.service import TaskService

log = structlog.get_logger(__name__)


class PingService:
    def __init__(self, ping_repo: PingRuleRepository, task_service: TaskService):
        self.ping_repo = ping_repo
        self.task_service = task_service

    async def list_rules(self, stage_id: int) -> list[PingRule]:
        return await self.ping_repo.get_rules_for_stage(stage_id)

    async def create_rule(
        self,
        company_id: int,
        stage_id: int,
        data: PingRuleCreateRequest,
    ) -> PingRule:
        stage = await StageTemplate.get_or_none(id=stage_id, company_id=company_id)
        if not stage:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")

        if stage.is_final:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot create ping rules for final stages",
            )

        count = await self.ping_repo.count_rules_for_stage(stage_id)
        if count >= MAX_PINGS_PER_STAGE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum {MAX_PINGS_PER_STAGE} ping rules per stage",
            )

        return await self.ping_repo.create_rule(
            company_id=company_id,
            stage_id=stage_id,
            position=data.position,
            delay_seconds=data.delay_seconds,
            condition=data.condition,
            content_type=data.content_type,
            static_content=data.static_content,
            prompt_override=data.prompt_override,
            is_active=data.is_active,
        )

    async def update_rule(
        self,
        company_id: int,
        ping_id: int,
        data: PingRuleUpdateRequest,
    ) -> PingRule:
        rule = await self.ping_repo.get_by_id(ping_id)
        if not rule or rule.company_id != company_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ping rule not found")

        updates = data.model_dump(exclude_unset=True)
        if not updates:
            return rule

        if "content_type" in updates or "static_content" in updates:
            ct = updates.get("content_type", rule.content_type)
            sc = updates.get("static_content", rule.static_content)
            if ct == PingContentType.STATIC and not sc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="static_content is required when content_type is 'static'",
                )

        for key, value in updates.items():
            setattr(rule, key, value)
        await rule.save()
        return rule

    async def delete_rule(self, company_id: int, ping_id: int) -> None:
        rule = await self.ping_repo.get_by_id(ping_id)
        if not rule or rule.company_id != company_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ping rule not found")
        await rule.delete()

    async def reorder_rules(self, company_id: int, stage_id: int, ping_rule_ids: list[int]) -> list[PingRule]:
        stage = await StageTemplate.get_or_none(id=stage_id, company_id=company_id)
        if not stage:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")

        existing = await self.ping_repo.get_rules_for_stage(stage_id)
        existing_ids = {r.id for r in existing}

        if set(ping_rule_ids) != existing_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ping_rule_ids must contain exactly all rule IDs for this stage",
            )

        rules_by_id = {r.id: r for r in existing}
        for rule in existing:
            rule.position = -rule.id
            await rule.save(update_fields=["position"])
        for position, rule_id in enumerate(ping_rule_ids, start=1):
            rule = rules_by_id[rule_id]
            rule.position = position
            await rule.save(update_fields=["position"])

        return await self.ping_repo.get_rules_for_stage(stage_id)

    async def cancel_pending_pings(self, order_id: int, *, stage_id: int | None = None) -> int:
        """Cancel pending auto-ping tasks for an order. Used by lifecycle hooks."""
        count = await self.task_service.cancel_pending_pings_for_order(order_id, stage_id=stage_id)
        if count > 0:
            log.info("pings.cancelled", order_id=order_id, stage_id=stage_id, count=count)
        return count

    async def get_rule_for_task(self, ping_rule_id: int) -> PingRule | None:
        """Get ping rule by ID. Used by task executor to load content config."""
        return await self.ping_repo.get_by_id(ping_rule_id)
