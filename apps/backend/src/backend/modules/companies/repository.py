from tortoise.exceptions import DoesNotExist

from src.backend.modules.companies.models import FAQ, Company
from src.backend.modules.core.base_repo import BaseRepository


class CompaniesRepository(BaseRepository[Company]):
    def __init__(self):
        super().__init__(Company)

    async def get_by_id(self, company_id: int) -> Company | None:
        try:
            return await Company.get(id=company_id).prefetch_related("fields__options", "categories", "faqs")
        except DoesNotExist:
            return None

    async def get_config(self, company_id: int) -> dict | None:
        company = await self.get_by_id(company_id)
        if not company:
            return None

        return {
            "id": company.id,
            "name": company.name,
            "description": company.description,
            "rules": company.rules,
            "tone_of_voice": company.tone_of_voice,
            "assistant_name": company.assistant_name,
            "qualification_workflow": company.qualification_workflow,
            "qualification_examples": company.qualification_examples,
            "collection_name": company.collection_name,
            "stages_config": company.stages_config,
            "category_rules": company.category_rules,
            "crm_forward_metadata_keys": company.crm_forward_metadata_keys,
            "crm_default_stage_id": company.crm_default_stage_id,
            "crm_manager_attention_stage_id": company.crm_manager_attention_stage_id,
        }

    async def list(self) -> list[Company]:
        return await self._list()

    async def create(self, name: str, description: str, rules: str, tone_of_voice: str, **kwargs) -> Company:
        return await self._create(
            name=name,
            description=description,
            rules=rules,
            tone_of_voice=tone_of_voice,
            **kwargs,
        )

    async def update(self, company_id: int, updates: dict) -> Company | None:
        return await self._update(id=company_id, updates=updates)

    async def delete(self, company_id: int) -> bool:
        return await self._delete(id=company_id)


class FAQsRepository(BaseRepository[FAQ]):
    def __init__(self):
        super().__init__(FAQ)

    async def list_by_company(self, company_id: int) -> list[FAQ]:
        return await FAQ.filter(company_id=company_id).all()

    async def list_by_company_paginated(self, company_id: int, limit: int, offset: int) -> tuple[list[FAQ], int]:
        total = await FAQ.filter(company_id=company_id).count()
        items = await FAQ.filter(company_id=company_id).offset(offset).limit(limit).all()
        return items, total

    async def create_faq(
        self,
        company_id: int,
        category: str,
        question: str,
        answer: str,
        keywords: list[str] | None = None,
    ) -> FAQ:
        return await self._create(
            company_id=company_id,
            category=category,
            question=question,
            answer=answer,
            keywords=keywords or [],
        )

    async def get_by_id(self, faq_id: int) -> FAQ | None:
        return await self._get(id=faq_id)

    async def update_faq(self, faq_id: int, updates: dict) -> FAQ | None:
        return await self._update(id=faq_id, updates=updates)

    async def delete_faq(self, faq_id: int) -> bool:
        return await self._delete(id=faq_id)

    async def search_by_keywords(self, company_id: int, search_term: str) -> list[FAQ]:
        return await FAQ.filter(company_id=company_id, question__icontains=search_term).all()
