from pydantic import BaseModel, Field, field_validator

from common.tools import AvailableTool


def _validate_enabled_tools(v: list[str]) -> list[str]:
    invalid = [t for t in v if t not in {e.value for e in AvailableTool}]
    if invalid:
        raise ValueError(f"Invalid tool names: {invalid}. Must be one of {[e.value for e in AvailableTool]}")
    return v


class CategoryBase(BaseModel):
    name: str
    description: str
    rules: str
    examples: str = ""
    workflow: str


class CategoryRequest(CategoryBase):
    company_id: int
    enabled_tools: list[str] = Field(default_factory=list)

    @field_validator("enabled_tools")
    @classmethod
    def validate_enabled_tools(cls, v: list[str]) -> list[str]:
        return _validate_enabled_tools(v)


class CategoryResponse(CategoryBase):
    id: int
    company_id: int
    enabled_tools: list[str] = Field(default_factory=list)


class CategoryPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    rules: str | None = None
    examples: str | None = None
    workflow: str | None = None
    enabled_tools: list[str] | None = None

    @field_validator("enabled_tools")
    @classmethod
    def validate_enabled_tools(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return _validate_enabled_tools(v)


class CategoryDetailResponse(BaseModel):
    """Детальная информация о категории для Sales Agent"""

    id: int
    name: str
    description: str
    rules: str
    examples: str = ""
    workflow: str
    enabled_tools: list[str] = Field(default_factory=list)
