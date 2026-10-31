from pydantic import BaseModel, Field

from src.backend.modules.prompt_addon.models import PromptAddon


class PromptAddonBase(BaseModel):
    name: str = Field(..., max_length=255)
    qualification_workflow: str
    qualification_examples: str


class PromptAddonRequest(PromptAddonBase):
    pass


class PromptAddonResponse(PromptAddonBase):
    id: int
    company_id: int

    @classmethod
    def from_model(cls, addon: "PromptAddon") -> "PromptAddonResponse":
        """Convert PromptAddon model to PromptAddonResponse."""
        return cls(
            id=addon.id,
            company_id=addon.company_id,
            name=addon.name,
            qualification_workflow=addon.qualification_workflow,
            qualification_examples=addon.qualification_examples,
        )


class PromptAddonPatch(BaseModel):
    name: str | None = Field(None, max_length=255)
    qualification_workflow: str | None = None
    qualification_examples: str | None = None


class ConnectorPromptAddonPatch(BaseModel):
    prompt_addon_id: int | None = None
