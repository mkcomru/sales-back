from src.backend.modules.companies.exceptions import CompanyNotFoundError
from src.backend.modules.companies.models import Company
from src.backend.modules.prompt_addon.exceptions import PromptAddonNotFoundError
from src.backend.modules.prompt_addon.repository import PromptAddonsRepository
from src.backend.modules.prompt_addon.schemas import PromptAddonPatch, PromptAddonResponse


class PromptAddonsService:
    repository: PromptAddonsRepository = PromptAddonsRepository()

    async def list_addons(self, company_id: int) -> list[PromptAddonResponse]:
        await self._ensure_company_exists(company_id)
        addons = await self.repository.list_by_company(company_id)
        return [PromptAddonResponse.from_model(addon) for addon in addons]

    async def get_addon(self, company_id: int, addon_id: int) -> PromptAddonResponse:
        await self._ensure_company_exists(company_id)
        addon = await self.repository.get_by_id(addon_id)

        if not addon:
            raise PromptAddonNotFoundError()

        if addon.company_id != company_id:
            raise PromptAddonNotFoundError()

        return PromptAddonResponse.from_model(addon)

    async def create_addon(
        self, company_id: int, name: str, qualification_workflow: str, qualification_examples: str
    ) -> PromptAddonResponse:
        await self._ensure_company_exists(company_id)
        addon = await self.repository.create(
            company_id=company_id,
            name=name,
            qualification_workflow=qualification_workflow,
            qualification_examples=qualification_examples,
        )
        return PromptAddonResponse.from_model(addon)

    async def update_addon(self, company_id: int, addon_id: int, patch: PromptAddonPatch) -> PromptAddonResponse:
        await self._ensure_company_exists(company_id)
        addon = await self.repository.get_by_id(addon_id)

        if not addon:
            raise PromptAddonNotFoundError()

        if addon.company_id != company_id:
            raise PromptAddonNotFoundError()

        updates = patch.model_dump(exclude_unset=True)
        updated_addon = await self.repository.update(addon_id, updates)

        if not updated_addon:
            raise PromptAddonNotFoundError()

        return PromptAddonResponse.from_model(updated_addon)

    async def delete_addon(self, company_id: int, addon_id: int) -> bool:
        await self._ensure_company_exists(company_id)
        addon = await self.repository.get_by_id(addon_id)

        if not addon:
            raise PromptAddonNotFoundError()

        if addon.company_id != company_id:
            raise PromptAddonNotFoundError()

        deleted = await self.repository.delete(addon_id)

        if not deleted:
            raise PromptAddonNotFoundError()

        return deleted

    @staticmethod
    async def _ensure_company_exists(company_id: int) -> None:
        company = await Company.get_or_none(id=company_id)
        if not company:
            raise CompanyNotFoundError()
