from common.events.contracts import ChangeType

from src.backend.modules.categories.schemas import CategoryDetailResponse
from src.backend.modules.companies.exceptions import (
    CompanyNotFoundError,
    FAQNotFoundError,
)
from src.backend.modules.companies.models import Company
from src.backend.modules.companies.repository import CompaniesRepository, FAQsRepository
from src.backend.modules.companies.schemas import (
    CompanyConfigResponse,
    CompanyMemberResponse,
    CompanyProductsResponse,
    CompanyResponse,
    FAQResponse,
)
from src.backend.modules.fields.models import Field
from src.backend.modules.fields.schemas import FieldOptionResponse, FieldResponse
from src.backend.modules.products.schemas import ProductDetailResponse
from src.backend.modules.stages.service import StagesService
from src.backend.modules.users.models import CompanyUser, User, UserRole
from src.backend.modules.users.service import UsersService
from src.backend.services.events import publish_company_specification_changed


class CompaniesService:
    repository: CompaniesRepository = CompaniesRepository()

    def __init__(self, users_service: UsersService | None = None):
        self.stages_service = StagesService()
        self._users_service = users_service

    async def _check_readiness(self, company: Company) -> tuple[bool, list[str]]:
        """Проверка готовности агента к деплою.

        Критические условия:
        - Заполнены базовые поля (name, description, assistant_name)
        - Есть хотя бы один активный transport connector (Telegram OR Wappi)

        Returns:
            (is_ready, list_of_issues)
        """
        issues = []

        if not company.name or not company.name.strip():
            issues.append("missing_company_name")
        if not company.description or not company.description.strip():
            issues.append("missing_company_description")
        if not company.assistant_name or not company.assistant_name.strip():
            issues.append("missing_assistant_name")

        active_connectors = await company.connectors.filter(enabled=True).count()

        if active_connectors == 0:
            issues.append("no_active_transport_connector")

        is_ready = len(issues) == 0
        return is_ready, issues

    async def get_config(self, company_id: int) -> CompanyConfigResponse:
        config = await self.repository.get_config(company_id)

        if not config:
            raise CompanyNotFoundError()

        company = await self.repository.get_by_id(company_id)
        if not company:
            raise CompanyNotFoundError()

        enabled_tools = list(company.enabled_tools) if company.enabled_tools else []
        return CompanyConfigResponse(**config, enabled_tools=enabled_tools)

    async def get_company_products(self, company_id: int) -> CompanyProductsResponse:
        """Get company products, categories, and fields. Optimized for batch fetching."""
        from src.backend.modules.categories.models import Category
        from src.backend.modules.products.models import Product

        company = await self.repository.get_by_id(company_id)
        if not company:
            raise CompanyNotFoundError()

        categories = await Category.filter(company_id=company_id).all()

        categories_data = [
            CategoryDetailResponse(
                id=c.id,
                name=c.name,
                description=c.description,
                rules=c.rules,
                examples=c.examples,
                workflow=c.workflow,
                enabled_tools=list(c.enabled_tools) if c.enabled_tools else [],
            )
            for c in categories
        ]

        category_ids = [c.id for c in categories]
        products = (
            await Product.filter(category_id__in=category_ids).prefetch_related("category").all()
            if category_ids
            else []
        )
        products_data = [
            ProductDetailResponse(
                id=p.id,
                name=p.name,
                description=p.description,
                category_id=p.category.id if p.category else None,
                attributes=p.attributes,
            )
            for p in products
        ]

        fields = await Field.filter(company_id=company_id).prefetch_related("options", "category", "product").all()
        fields_data = [
            FieldResponse(
                id=f.id,
                name=f.name,
                question=f.question,
                type=f.answer_type.value,
                required=f.required,
                display_name=f.display_name,
                level=f.level,
                is_system=f.is_system,
                category_id=f.category.id if f.category else None,
                product_id=f.product.id if f.product else None,
                options=[FieldOptionResponse(id=opt.id, value=opt.value, order=opt.order) for opt in f.options],
            )
            for f in fields
        ]

        return CompanyProductsResponse(categories=categories_data, products=products_data, fields=fields_data)

    async def list_companies(self) -> list[CompanyResponse]:
        companies = await self.repository.list()
        results = []
        for company in companies:
            is_ready, issues = await self._check_readiness(company)
            response = self._to_response(company, is_ready, issues)
            results.append(response)
        return results

    async def list_companies_for_user(self, user_id: int) -> list[CompanyResponse]:
        company_users = await CompanyUser.filter(user_id=user_id).prefetch_related("company")
        results = []
        for company_user in company_users:
            company = company_user.company
            is_ready, issues = await self._check_readiness(company)
            response = self._to_response(company, is_ready, issues)
            results.append(response)
        return results

    async def get_company(self, company_id: int) -> CompanyResponse:
        company = await self.repository.get_by_id(company_id)

        if not company:
            raise CompanyNotFoundError()

        is_ready, issues = await self._check_readiness(company)
        return self._to_response(company, is_ready, issues)

    async def get_company_managers(self, company_id: int) -> list[dict]:
        """Get all managers (MANAGER, ADMIN, OWNER roles) of a company.

        Args:
            company_id: Company identifier

        Returns:
            List of manager dictionaries with user details

        Raises:
            CompanyNotFoundError: If company not found
        """
        from src.backend.modules.companies.models import Company

        company = await Company.get_or_none(id=company_id)
        if not company:
            raise CompanyNotFoundError()

        company_users = await CompanyUser.filter(
            company_id=company_id,
            role__in=[UserRole.MANAGER, UserRole.ADMIN, UserRole.OWNER],
        ).prefetch_related("user")

        managers = []
        for company_user in company_users:
            managers.append(
                {
                    "id": company_user.id,
                    "user_id": company_user.user.id,
                    "first_name": company_user.user.first_name,
                    "last_name": company_user.user.last_name,
                    "email": company_user.user.email,
                    "role": company_user.role.value,
                }
            )

        return managers

    async def add_company_member(
        self,
        company_id: int,
        first_name: str,
        last_name: str,
        email: str,
        password: str,
        role: UserRole = UserRole.MANAGER,
    ) -> CompanyMemberResponse:
        """Add a new user to the company. Creates User if new, otherwise links existing user.

        Requires CompaniesService to be constructed with users_service (via DI).
        """
        if self._users_service is None:
            raise RuntimeError("CompaniesService requires users_service to add members")

        from src.backend.modules.users.exceptions import UserAlreadyExistsError

        company = await self.repository.get_by_id(company_id)
        if not company:
            raise CompanyNotFoundError()

        if role == UserRole.OWNER:
            raise ValueError("Cannot add member with owner role via this endpoint")

        user: User
        try:
            user = await self._users_service.create_user(
                first_name=first_name,
                last_name=last_name,
                email=email,
                password=password,
                is_superuser=False,
            )
        except UserAlreadyExistsError:
            existing = await User.get_or_none(email=email.lower())
            if not existing:
                raise
            user = existing

        company_user, created = await CompanyUser.get_or_create(
            user_id=user.id,
            company_id=company_id,
            defaults={"role": role},
        )
        if not created and company_user.role != role:
            company_user.role = role
            await company_user.save(update_fields=["role"])

        return CompanyMemberResponse(
            id=company_user.id,
            user_id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email,
            role=company_user.role.value,
        )

    async def create_company(self, creator_id: int, **kwargs) -> CompanyResponse:
        company = await self.repository.create(**kwargs)

        # Auto-add creator as owner
        await CompanyUser.get_or_create(
            user_id=creator_id,
            company_id=company.id,
            defaults={"role": UserRole.OWNER},
        )

        # Create default stages for new company
        await self.stages_service.create_default_stages(company.id)

        is_ready, issues = await self._check_readiness(company)
        response = self._to_response(company, is_ready, issues)
        await publish_company_specification_changed(company_id=company.id, change_type=ChangeType.UPSERT)
        return response

    async def update_company(self, company_id: int, updates: dict) -> CompanyResponse:
        company = await self.repository.update(company_id, updates)

        if not company:
            raise CompanyNotFoundError()

        is_ready, issues = await self._check_readiness(company)
        response = self._to_response(company, is_ready, issues)
        await publish_company_specification_changed(company_id=company.id, change_type=ChangeType.UPSERT)
        return response

    async def delete_company(self, company_id: int) -> bool:
        deleted = await self.repository.delete(company_id)

        if not deleted:
            raise CompanyNotFoundError()

        await publish_company_specification_changed(company_id=company_id, change_type=ChangeType.DELETE)
        return deleted

    def _to_response(
        self,
        company: Company,
        is_ready: bool = False,
        issues: list[str] | None = None,
    ) -> CompanyResponse:
        enabled_tools = list(company.enabled_tools) if company.enabled_tools else []
        return CompanyResponse(
            id=company.id,
            name=company.name,
            description=company.description,
            rules=company.rules,
            tone_of_voice=company.tone_of_voice,
            assistant_name=company.assistant_name,
            qualification_workflow=company.qualification_workflow,
            qualification_examples=company.qualification_examples,
            collection_name=company.collection_name,
            stages_config=company.stages_config,
            category_rules=company.category_rules,
            crm_forward_metadata_keys=company.crm_forward_metadata_keys,
            crm_default_stage_id=company.crm_default_stage_id,
            crm_manager_attention_stage_id=company.crm_manager_attention_stage_id,
            enabled_tools=enabled_tools,
            is_ready_to_deploy=is_ready,
            readiness_issues=issues or [],
        )

    async def get_specification(self, company_id: int) -> dict:
        """Get complete company specification for Sales Agent.

        Optimized to use batch fetching instead of N+1 queries.
        """
        from src.backend.modules.categories.models import Category

        company = await self.repository.get_by_id(company_id)
        if not company:
            raise CompanyNotFoundError()

        company_enabled_tools = list(company.enabled_tools) if company.enabled_tools else []

        categories = await Category.filter(company_id=company_id).all()
        category_ids = [c.id for c in categories]

        categories_data = [
            CategoryDetailResponse(
                id=c.id,
                name=c.name,
                description=c.description,
                rules=c.rules,
                examples=c.examples,
                workflow=c.workflow,
                enabled_tools=list(c.enabled_tools) if c.enabled_tools else [],
            ).model_dump()
            for c in categories
        ]

        from src.backend.modules.integrations.registry import _resolve
        from src.backend.modules.products.service import ProductsService

        products_service = await _resolve(ProductsService, company_id)
        products_data = await products_service.list_for_agent(category_ids)

        # Batch fetch fields with all relations
        fields = await Field.filter(company_id=company_id).prefetch_related("options", "category", "product").all()
        fields_data = [
            FieldResponse(
                id=f.id,
                name=f.name,
                question=f.question,
                type=f.answer_type.value,
                required=f.required,
                display_name=f.display_name,
                level=f.level,
                is_system=f.is_system,
                category_id=f.category.id if f.category else None,
                product_id=f.product.id if f.product else None,
                options=[FieldOptionResponse(id=opt.id, value=opt.value, order=opt.order) for opt in f.options],
            ).model_dump()
            for f in fields
        ]

        # Batch fetch FAQs
        faqs = await company.faqs.all()
        faqs_data = [
            FAQResponse(
                id=faq.id,
                category=faq.category,
                question=faq.question,
                answer=faq.answer,
                keywords=faq.keywords,
            ).model_dump()
            for faq in faqs
        ]

        return {
            "id": company.id,
            "name": company.name,
            "description": company.description,
            "rules": company.rules,
            "tone_of_voice": company.tone_of_voice,
            "assistant_name": company.assistant_name,
            "collection_name": company.collection_name,
            "stages_config": company.stages_config,
            "category_rules": company.category_rules,
            "crm_forward_metadata_keys": company.crm_forward_metadata_keys,
            "crm_default_stage_id": company.crm_default_stage_id,
            "crm_manager_attention_stage_id": company.crm_manager_attention_stage_id,
            "enabled_tools": company_enabled_tools,
            "categories": categories_data,
            "products": products_data,
            "fields": fields_data,
            "faqs": faqs_data,
        }


class FAQsService:
    repository: FAQsRepository = FAQsRepository()

    async def get_faq(self, faq_id: int, company_id: int) -> FAQResponse:
        faq = await self.repository.get_by_id(faq_id)

        if not faq:
            raise FAQNotFoundError()

        await faq.fetch_related("company")
        if faq.company.id != company_id:
            raise FAQNotFoundError()

        return FAQResponse(
            id=faq.id,
            category=faq.category,
            question=faq.question,
            answer=faq.answer,
            keywords=faq.keywords,
        )

    async def list_faqs(self, company_id: int) -> list[FAQResponse]:
        faqs = await self.repository.list_by_company(company_id)

        return [
            FAQResponse(
                id=faq.id,
                category=faq.category,
                question=faq.question,
                answer=faq.answer,
                keywords=faq.keywords,
            )
            for faq in faqs
        ]

    async def list_faqs_paginated(self, company_id: int, limit: int, offset: int) -> tuple[list[FAQResponse], int]:
        faqs, total = await self.repository.list_by_company_paginated(company_id, limit, offset)

        items = [
            FAQResponse(
                id=faq.id,
                category=faq.category,
                question=faq.question,
                answer=faq.answer,
                keywords=faq.keywords,
            )
            for faq in faqs
        ]
        return items, total

    async def create_faq(self, company_id: int, payload) -> FAQResponse:
        faq = await self.repository.create_faq(
            company_id=company_id,
            category=payload.category,
            question=payload.question,
            answer=payload.answer,
            keywords=payload.keywords,
        )

        return FAQResponse(
            id=faq.id,
            category=faq.category,
            question=faq.question,
            answer=faq.answer,
            keywords=faq.keywords,
        )

    async def update_faq(self, faq_id: int, company_id: int, payload) -> FAQResponse:
        await self.get_faq(faq_id, company_id)

        updates = payload.model_dump(exclude_unset=True, exclude_none=True)
        updated_faq = await self.repository.update_faq(faq_id, updates)

        if not updated_faq:
            raise FAQNotFoundError()

        return FAQResponse(
            id=updated_faq.id,
            category=updated_faq.category,
            question=updated_faq.question,
            answer=updated_faq.answer,
            keywords=updated_faq.keywords,
        )

    async def delete_faq(self, faq_id: int, company_id: int) -> bool:
        await self.get_faq(faq_id, company_id)
        return await self.repository.delete_faq(faq_id)

    async def search_faqs(self, company_id: int, search_term: str) -> list[FAQResponse]:
        faqs = await self.repository.search_by_keywords(company_id, search_term)

        return [
            FAQResponse(
                id=faq.id,
                category=faq.category,
                question=faq.question,
                answer=faq.answer,
                keywords=faq.keywords,
            )
            for faq in faqs
        ]
