"""API schemas for sync endpoints."""

from pydantic import BaseModel, Field


class BatchProcessResponse(BaseModel):
    """Response for batch processing."""

    status: str = Field(description="Processing status: 'processed' or 'duplicate'")
    message_count: int = Field(description="Number of messages processed")


class CursorResponse(BaseModel):
    """Response for cursor retrieval."""

    cursor: str | None = Field(default=None, description="Last cursor for resume, or None if not found")
