"""Integration tests fixtures for stages."""

import pytest_asyncio

from src.backend.modules.stages.models import StageTemplate


@pytest_asyncio.fixture
async def clear_stages():
    """Helper to clear all stages for a company."""

    async def _clear(company_id: int):
        await StageTemplate.filter(company_id=company_id).delete()

    return _clear
