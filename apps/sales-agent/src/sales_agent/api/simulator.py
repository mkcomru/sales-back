"""Simulator API for testing AI agent in sandbox environment."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from common import SalesAgentSettings
from common.models.io import SimpleChat, SimpleMessage, SimpleUser

from src.sales_agent.agents.pipeline import process_user_message_agents
from src.sales_agent.core.llm.client import LLMClient
from src.sales_agent.core.telemetry import Tracer
from src.sales_agent.handlers.dependencies import (
    get_large_llm_client,
    get_settings,
    get_tracer,
)
from src.sales_agent.services.backend_client import BackendClient

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/simulator", tags=["simulator"])


class SimulatorMessageRequest(BaseModel):
    """Request to process message in simulator mode."""

    text: str = Field(..., min_length=1, description="User message text")
    company_id: int = Field(..., ge=1, description="Company ID")
    user_id: str = Field(default="simulator_user", description="Simulated user ID")


class SimulatorMessageResponse(BaseModel):
    """Response from simulator with AI answer."""

    text: str = Field(..., description="AI assistant response")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional response metadata")


@router.post("/message", response_model=SimulatorMessageResponse)
async def process_simulator_message(
    request: SimulatorMessageRequest,
    settings: SalesAgentSettings = Depends(get_settings),
    llm_client: LLMClient = Depends(get_large_llm_client),
    tracer: Tracer = Depends(get_tracer),
) -> SimulatorMessageResponse:
    """Process message in simulator sandbox mode.

    This endpoint:
    - Does NOT save to customer store
    - Does NOT save to backend threads/messages
    - Does NOT use conversation history
    - Uses current company settings
    - Returns AI response immediately
    """
    log.info(
        "simulator.message.received",
        company_id=request.company_id,
        text_length=len(request.text),
    )

    try:
        backend_client = BackendClient(settings)

        simple_msg = SimpleMessage(
            text=request.text,
            from_user=SimpleUser(id=hash(request.user_id) & 0x7FFFFFFF),
            chat=SimpleChat(id=1),
            message_id=0,
            metadata={
                "company_id": request.company_id,
                "_simulator_mode": True,
            },
        )

        result = await process_user_message_agents(
            message=simple_msg,
            settings=settings,
            large_llm_client=llm_client,
            tracer=tracer,
            backend_client=backend_client,
            connector_context=None,
        )

        log.info(
            "simulator.message.processed",
            company_id=request.company_id,
            response_length=len(result.text or ""),
        )

        return SimulatorMessageResponse(
            text=result.text or "",
            metadata={
                "stage_id": result.stage_id,
            },
        )

    except ValueError as exc:
        log.error(
            "simulator.message.validation_error",
            company_id=request.company_id,
            error=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except Exception as exc:
        log.exception(
            "simulator.message.error",
            company_id=request.company_id,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="Failed to process simulator message") from exc
