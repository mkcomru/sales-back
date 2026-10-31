"""Base payload models for event contracts."""

from pydantic import BaseModel, ConfigDict


class BaseEventPayload(BaseModel):
    """
    Base class for all event payloads.

    Payloads are signal-only: minimal data to identify what changed.
    Consumers must fetch current state from backend APIs.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class CompanyScopedPayload(BaseEventPayload):
    """Base for payloads that are scoped to a company."""

    company_id: int
