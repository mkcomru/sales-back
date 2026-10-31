from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CredentialFieldSchema(BaseModel):
    """Describes one credential field a provider expects (for frontend form rendering)."""

    key: str = Field(description="Field key, e.g. 'api_key', 'bearer_token'")
    label: str = Field(description="Human-readable label for the form field")
    field_type: str = Field(
        default="string",
        description="Input type hint: 'string', 'password', 'url', 'number'",
    )
    required: bool = True
    placeholder: str = ""


class ConfigFieldSchema(BaseModel):
    """Describes one non-secret config field a provider accepts."""

    key: str
    label: str
    field_type: str = "string"
    required: bool = False
    placeholder: str = ""
    default: Any = None


class ProviderCatalogEntry(BaseModel):
    """Self-describing metadata for a single integration provider.

    Populated by provider packages at import time via register_provider().
    Served to the frontend so it knows what can be connected and how.
    """

    provider_type: str = Field(description="Unique provider identifier, e.g. 'yclients'")
    display_name: str = Field(description="Human-readable name, e.g. 'YClients'")
    description: str = Field(default="", description="Short description of what this integration does")
    logo_url: str = Field(default="", description="URL to provider logo (optional)")
    supported_capabilities: list[str] = Field(
        description="Capabilities this provider can deliver, e.g. ['scheduling', 'staff']"
    )
    credential_fields: list[CredentialFieldSchema] = Field(
        default_factory=list,
        description="Credential fields the admin must fill in to connect",
    )
    config_fields: list[ConfigFieldSchema] = Field(
        default_factory=list,
        description="Non-secret configuration fields",
    )


class IntegrationCreate(BaseModel):
    provider_type: str = Field(min_length=1, max_length=64)
    credentials: dict[str, Any] = Field(
        default_factory=dict,
        description="Plaintext credentials — will be encrypted at rest",
    )
    config: dict[str, Any] = Field(default_factory=dict)
    enabled_capabilities: list[str] = Field(default_factory=list)
    enabled: bool = True


class IntegrationUpdate(BaseModel):
    credentials: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    enabled_capabilities: list[str] | None = None
    enabled: bool | None = None


class IntegrationResponse(BaseModel):
    id: int
    company_id: int
    provider_type: str
    config: dict[str, Any]
    enabled_capabilities: list[str]
    enabled: bool

    model_config = {"from_attributes": True}
