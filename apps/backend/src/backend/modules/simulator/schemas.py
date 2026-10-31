from datetime import datetime

from pydantic import BaseModel, Field


class SimulatorMessageRequest(BaseModel):
    """Request to send message in simulator."""

    text: str = Field(..., min_length=1, description="User message text")


class SimulatorMessageResponse(BaseModel):
    """Response with AI answer from simulator."""

    text: str = Field(..., description="AI assistant response")
    timestamp: datetime = Field(..., description="Message timestamp")


class SimulatorResetResponse(BaseModel):
    """Response after resetting simulator session."""

    success: bool = Field(default=True, description="Reset successful")
    message: str = Field(default="Session reset", description="Status message")


class SimulatorSessionMessage(BaseModel):
    """Single message in simulator session history."""

    role: str = Field(..., description="Message role (user|assistant)")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(..., description="Message timestamp")
