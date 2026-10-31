from tortoise.exceptions import DoesNotExist

from src.backend.modules.core.base_repo import BaseRepository
from src.backend.modules.prompt_addon.models import PromptAddon


class PromptAddonsRepository(BaseRepository[PromptAddon]):
    def __init__(self):
        super().__init__(PromptAddon)

    async def get_by_id(self, addon_id: int) -> PromptAddon | None:
        try:
            return await PromptAddon.get(id=addon_id)
        except DoesNotExist:
            return None

    async def list_by_company(self, company_id: int) -> list[PromptAddon]:
        return await PromptAddon.filter(company_id=company_id).all()

    async def create(
        self, company_id: int, name: str, qualification_workflow: str, qualification_examples: str
    ) -> PromptAddon:
        return await self._create(
            company_id=company_id,
            name=name,
            qualification_workflow=qualification_workflow,
            qualification_examples=qualification_examples,
        )

    async def update(self, addon_id: int, updates: dict) -> PromptAddon | None:
        return await self._update(id=addon_id, updates=updates)

    async def delete(self, addon_id: int) -> bool:
        return await self._delete(id=addon_id)
