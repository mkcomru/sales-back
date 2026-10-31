from pydantic import BaseModel, EmailStr, Field, field_validator

from common.tools import AvailableTool

from src.backend.modules.categories.schemas import CategoryDetailResponse
from src.backend.modules.fields.schemas import FieldResponse
from src.backend.modules.products.schemas import ProductDetailResponse
from src.backend.modules.users.models import UserRole


def _validate_enabled_tools(v: list[str]) -> list[str]:
    invalid = [t for t in v if t not in {e.value for e in AvailableTool}]
    if invalid:
        raise ValueError(f"Invalid tool names: {invalid}. Must be one of {[e.value for e in AvailableTool]}")
    return v


class CompanyRequest(BaseModel):
    """Запрос на создание компании"""

    name: str
    description: str
    rules: str
    tone_of_voice: str
    assistant_name: str
    qualification_workflow: str
    qualification_examples: str
    collection_name: str
    stages_config: list[dict] = Field(default_factory=list)
    category_rules: list[dict] = Field(default_factory=list)
    crm_forward_metadata_keys: list[str] = Field(default_factory=list)
    crm_default_stage_id: str = "PROCESSED"
    crm_manager_attention_stage_id: str | None = None
    enabled_tools: list[str] = Field(default_factory=list)

    @field_validator("enabled_tools")
    @classmethod
    def validate_enabled_tools(cls, v: list[str]) -> list[str]:
        return _validate_enabled_tools(v)


class CompanyPatch(BaseModel):
    """Запрос на обновление компании"""

    name: str | None = None
    description: str | None = None
    rules: str | None = None
    tone_of_voice: str | None = None
    assistant_name: str | None = None
    qualification_workflow: str | None = None
    qualification_examples: str | None = None
    collection_name: str | None = None
    stages_config: list[dict] | None = None
    category_rules: list[dict] | None = None
    crm_forward_metadata_keys: list[str] | None = None
    crm_default_stage_id: str | None = None
    crm_manager_attention_stage_id: str | None = None
    enabled_tools: list[str] | None = None

    @field_validator("enabled_tools")
    @classmethod
    def validate_enabled_tools(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return _validate_enabled_tools(v)


class CompanyResponse(BaseModel):
    """Базовая информация о компании"""

    id: int
    name: str
    description: str
    rules: str
    tone_of_voice: str
    assistant_name: str
    qualification_workflow: str
    qualification_examples: str
    collection_name: str
    stages_config: list[dict] = Field(default_factory=list)
    category_rules: list[dict] = Field(default_factory=list)
    crm_forward_metadata_keys: list[str] = Field(default_factory=list)
    crm_default_stage_id: str
    crm_manager_attention_stage_id: str | None = None
    enabled_tools: list[str] = Field(default_factory=list)
    is_ready_to_deploy: bool = False
    readiness_issues: list[str] = Field(default_factory=list)


class CompanyConfigResponse(BaseModel):
    """Полная конфигурация компании для Sales Agent"""

    id: int
    name: str
    description: str
    rules: str
    tone_of_voice: str
    assistant_name: str
    qualification_workflow: str
    qualification_examples: str
    stages_config: list[dict] = Field(default_factory=list)
    category_rules: list[dict] = Field(default_factory=list)
    crm_forward_metadata_keys: list[str] = Field(default_factory=list)
    crm_default_stage_id: str
    crm_manager_attention_stage_id: str | None = None
    collection_name: str
    enabled_tools: list[str] = Field(default_factory=list)


class CompanyProductsResponse(BaseModel):
    """Продукты, категории и поля компании для Sales Agent"""

    categories: list[CategoryDetailResponse]
    products: list[ProductDetailResponse]
    fields: list[FieldResponse]


class FAQResponse(BaseModel):
    """FAQ запись"""

    id: int
    category: str
    question: str
    answer: str
    keywords: list[str] = Field(default_factory=list)


class CompanySpecificationResponse(BaseModel):
    """Полная спецификация компании для Sales Agent - все данные разом"""

    id: int
    name: str
    description: str

    # Company-level config
    rules: str
    tone_of_voice: str
    assistant_name: str
    collection_name: str

    # Domain config (routing)
    stages_config: list[dict] = Field(default_factory=list)
    category_rules: list[dict] = Field(default_factory=list)

    # CRM integration
    crm_forward_metadata_keys: list[str] = Field(default_factory=list)
    crm_default_stage_id: str
    crm_manager_attention_stage_id: str | None = None

    # Tools
    enabled_tools: list[str] = Field(default_factory=list)

    # Categories with products
    categories: list[CategoryDetailResponse] = Field(default_factory=list)

    # Products with full configuration
    products: list[ProductDetailResponse] = Field(default_factory=list)

    # Fields
    fields: list[FieldResponse] = Field(default_factory=list)

    # FAQs
    faqs: list[FAQResponse] = Field(default_factory=list)


class FAQBase(BaseModel):
    """Базовая модель FAQ"""

    category: str
    question: str
    answer: str
    keywords: list[str] = Field(default_factory=list)


class FAQRequest(FAQBase):
    """Запрос на создание FAQ"""

    pass


class FAQPatch(BaseModel):
    """Запрос на обновление FAQ"""

    category: str | None = None
    question: str | None = None
    answer: str | None = None
    keywords: list[str] | None = None


class CompanyMemberResponse(BaseModel):
    """Company member information for assignee selection and team schedule."""

    id: int = Field(description="CompanyUser ID")
    user_id: int = Field(description="User ID")
    first_name: str = Field(description="First name")
    last_name: str = Field(description="Last name")
    email: str = Field(description="Email")
    role: str = Field(description="Role in the company")
    is_available: bool = Field(default=True, description="Whether manager is available for assignment")


class AddCompanyMemberRequest(BaseModel):
    """Request to add a new user to a company."""

    first_name: str = Field(min_length=1, max_length=255, description="First name")
    last_name: str = Field(min_length=1, max_length=255, description="Last name")
    email: EmailStr = Field(description="Email")
    password: str = Field(min_length=8, description="Password")
    role: UserRole = Field(default=UserRole.MANAGER, description="Role: viewer, manager, admin")

    @field_validator("role")
    @classmethod
    def role_not_owner(cls, v: UserRole) -> UserRole:
        if v == UserRole.OWNER:
            raise ValueError("Cannot add member with owner role via this endpoint")
        return v
