from __future__ import annotations

from common import SalesAgentSettings as Settings
from common.models.io import SimpleMessage

from src.sales_agent.services.crm_adapter import CRMAdapter


async def notify_handoff(
    settings: Settings,
    message: SimpleMessage,
    summary: dict[str, str],
    stage: str | None = None,
    *,
    operator: bool | None = None,
) -> None:
    """Delegate handoff notification to CRM adapter layer."""
    adapter = CRMAdapter(settings=settings)
    await adapter.notify_handoff(message=message, summary=summary, stage=stage, operator=operator)
