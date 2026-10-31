"""Stages test fixtures."""

from __future__ import annotations

import pytest

from src.backend.modules.stages.models import StageTemplate
from src.backend.modules.stages.repository import StagesRepository
from src.backend.modules.stages.service import StagesService


@pytest.fixture
def stages_repo() -> StagesRepository:
    """Create stages repository instance."""
    return StagesRepository()


@pytest.fixture
def stages_service() -> StagesService:
    """Create stages service instance."""
    return StagesService()


@pytest.fixture
async def clear_stages():
    """Helper fixture to clear stages for a company."""

    async def _clear(company_id: int):
        await StageTemplate.filter(company_id=company_id).delete()

    return _clear


@pytest.fixture
async def company_without_stages(company_factory, clear_stages):
    """Create a company without default stages."""
    company = await company_factory()
    await clear_stages(company.id)
    return company


@pytest.fixture
async def stage_template(company_without_stages) -> StageTemplate:
    """Create a single stage template."""
    return await StageTemplate.create(
        company_id=company_without_stages.id,
        name="Test Stage",
        color="#3b82f6",
        position=0,
        transition_condition={"$any": True},
    )


@pytest.fixture
async def stage_templates(company_without_stages) -> list[StageTemplate]:
    """Create multiple stage templates for testing funnel."""
    stages = []
    stages.append(
        await StageTemplate.create(
            company_id=company_without_stages.id,
            name="Новый",
            color="#64748b",
            position=0,
            transition_condition={"$any": True},
        )
    )
    stages.append(
        await StageTemplate.create(
            company_id=company_without_stages.id,
            name="Квалификация",
            color="#3b82f6",
            position=1,
            transition_condition={"order_fields.budget": {"$gte": 1000}},
        )
    )
    stages.append(
        await StageTemplate.create(
            company_id=company_without_stages.id,
            name="Предложение",
            color="#f59e0b",
            position=2,
            transition_condition={
                "$and": [
                    {"order_fields.budget": {"$gte": 1000}},
                    {"customer_fields.city": {"$exists": True}},
                ]
            },
        )
    )
    stages.append(
        await StageTemplate.create(
            company_id=company_without_stages.id,
            name="Закрыто (успешно)",
            color="#10b981",
            position=3,
            is_final=True,
            result="won",
            auto_close=True,
            transition_condition={"order_fields.deal_closed": {"$eq": True}},
        )
    )
    stages.append(
        await StageTemplate.create(
            company_id=company_without_stages.id,
            name="Отказ",
            color="#ef4444",
            position=4,
            is_final=True,
            result="lost",
            auto_close=True,
            transition_condition={"order_fields.rejected": {"$eq": True}},
        )
    )
    return stages
