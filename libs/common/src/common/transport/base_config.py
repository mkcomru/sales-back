from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class BaseConnectorConfig(BaseModel):
    """Common base for all connector configuration models.

    Enforces that connector_id, company_id, and channel_type are always
    present and normalized. Subclasses add their platform-specific fields.
    """

    connector_id: str
    company_id: str
    channel_type: str = "telegram"
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "ignore"}

    @model_validator(mode="before")
    @classmethod
    def _coerce_base_fields(cls, data: Any) -> Any:
        """Coerce company_id to str and normalize channel_type before Pydantic validates types."""
        if not isinstance(data, dict):
            return data
        if "company_id" in data:
            data["company_id"] = str(data["company_id"])
        if "channel_type" in data and data["channel_type"] is None:
            data["channel_type"] = "telegram"
        return data

    @model_validator(mode="after")
    def _normalize_base_fields(self) -> BaseConnectorConfig:
        self.connector_id = self.connector_id.strip()
        if not self.connector_id:
            raise ValueError("connector_id must be provided")
        self.company_id = self.company_id.strip()
        if not self.company_id:
            raise ValueError("company_id must be provided")
        self.channel_type = (self.channel_type or "telegram").strip() or "telegram"
        return self
