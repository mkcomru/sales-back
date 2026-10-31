"""Assembles AgentContext for Sales Agent envelope.

Single entry point for building the full LLM execution context
that travels in InternalInboundRequest / TaskExecutionRequest.
"""

from __future__ import annotations

from typing import Any

import structlog

from common.integrations import Capability
from common.models.outbound import AgentContext
from common.tools import LEGACY_TOOLS

from src.backend.modules.chat.service import ChatService
from src.backend.modules.companies.service import CompaniesService
from src.backend.modules.integrations.repository import IntegrationRepository
from src.backend.modules.orders.models import Order
from src.backend.modules.prompts.models import AgentType
from src.backend.modules.prompts.service import PromptsService

log = structlog.get_logger(__name__)

HISTORY_LIMIT = 20


class AgentContextAssembler:
    """Builds AgentContext from DB for a given thread/user/company."""

    def __init__(
        self,
        companies_service: CompaniesService,
        prompts_service: PromptsService,
        chat_service: ChatService,
    ) -> None:
        self._companies = companies_service
        self._prompts = prompts_service
        self._chat = chat_service
        self._integration_repo = IntegrationRepository()

    async def build(
        self,
        *,
        company_id: int,
        user_id: str,
        thread_id: str,
        conversation_id: str | None,
        order_id: int | None = None,
    ) -> AgentContext:
        """Assemble full agent context from DB."""
        prompt = await self._prompts.get_prompt(AgentType.AGENT)
        company_spec = await self._companies.get_specification(company_id)
        profile = await self._chat.get_customer_profile(user_id, company_id)
        history = await self._chat.get_recent_history(thread_id, limit=HISTORY_LIMIT, exclude_internal_notes=True)
        langfuse_resp = await self._chat.get_langfuse_session_id(user_id, company_id, conversation_id)

        enabled_tools = _extract_enabled_tools(company_spec)
        active_capabilities = await self._get_active_capabilities(company_id)

        order_fields: dict[str, Any] = {}
        extra_fields: dict[str, Any] = {}
        if order_id:
            order = await Order.get_or_none(id=order_id)
            if order:
                order_fields = order.order_fields or {}
                extra_fields = order.extra_fields or {}

        return AgentContext(
            prompt_template=prompt.content,
            company=company_spec,
            customer_answers=profile.customer_fields,
            customer_name=profile.name,
            order_fields=order_fields,
            extra_fields=extra_fields,
            history=history,
            enabled_tools=enabled_tools,
            active_capabilities=[c.value for c in active_capabilities],
            langfuse_session_id=langfuse_resp.session_id,
        )

    async def _get_active_capabilities(self, company_id: int) -> list[Capability]:
        integrations = await self._integration_repo.get_for_company(company_id)
        capabilities: list[Capability] = []
        for integration in integrations:
            for cap_str in integration.enabled_capabilities:
                try:
                    capabilities.append(Capability(cap_str))
                except ValueError:
                    log.warning(
                        "integration.unknown_capability",
                        company_id=company_id,
                        provider=integration.provider_type,
                        capability=cap_str,
                    )
        return capabilities


def _extract_enabled_tools(company_spec: dict[str, Any]) -> list[str]:
    """Return enabled tool names from company spec only.

    Only company-level enabled_tools; no category or capability auto-add.
    Legacy tools are excluded so the agent never receives them.
    """
    legacy = {t.value for t in LEGACY_TOOLS}
    result: list[str] = []
    seen: set[str] = set()
    for name in company_spec.get("enabled_tools", []):
        if name and name not in seen and name not in legacy:
            seen.add(name)
            result.append(name)
    return result
