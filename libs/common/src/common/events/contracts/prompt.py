"""Prompt-related event payload contracts."""

from common.events.contracts.base import BaseEventPayload, CompanyScopedPayload
from common.events.contracts.transport import ChangeType


class PromptChangedPayloadV1(BaseEventPayload):
    """
    Payload for prompt.changed event (v1).

    Signal-only: identifies which prompt changed.
    Consumers must fetch current prompt content via backend API.
    """

    agent_type: str
    change_type: ChangeType


class CompanySpecificationChangedPayloadV1(CompanyScopedPayload):
    """
    Payload for company.specification.changed event (v1).

    Signal-only: identifies which company spec changed.
    Consumers must fetch current spec via backend API.
    """

    change_type: ChangeType
