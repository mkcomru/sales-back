from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class AttachmentDescriptor(BaseModel):
    artifact_id: str
    type: Literal["image", "audio", "voice", "video", "document"]
    mime_type: str
    caption: str | None = None


class TransportDeliveryPayload(BaseModel):
    connector_id: str
    company_id: str
    channel_type: str
    user_id: str
    conversation_id: str
    correlation_id: str
    replies: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    stage_id: str | None = None
    handoff: dict[str, Any] | None = None
    delivery_hint: dict[str, Any] | None = None
    attachments: list[AttachmentDescriptor] | None = None

    model_config = {"extra": "forbid"}

    @field_validator("replies")
    @classmethod
    def _strip_replies(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if str(item or "").strip()]

    @model_validator(mode="after")
    def _require_content(self) -> TransportDeliveryPayload:
        if not self.replies and not self.attachments:
            raise ValueError("Either replies or attachments must be non-empty")
        return self
