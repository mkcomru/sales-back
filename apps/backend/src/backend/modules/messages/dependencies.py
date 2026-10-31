from typing import Annotated

from fastapi import Depends

from src.backend.modules.chat.dependencies import ChatServiceDep
from src.backend.modules.companies.dependencies import CompaniesServiceDep
from src.backend.modules.core.dependencies import SettingsDep
from src.backend.modules.messages.context_assembly import AgentContextAssembler
from src.backend.modules.messages.outbound_service import OutboundService
from src.backend.modules.messages.transport_client import TransportClient
from src.backend.modules.prompts.dependencies import PromptsServiceDep


def transport_client(settings: SettingsDep) -> TransportClient:
    return TransportClient(settings)


TransportClientDep = Annotated[TransportClient, Depends(transport_client)]


def outbound_service(tc: TransportClientDep) -> OutboundService:
    return OutboundService(tc)


OutboundServiceDep = Annotated[OutboundService, Depends(outbound_service)]


def agent_context_assembler(
    companies_service: CompaniesServiceDep,
    prompts_service: PromptsServiceDep,
    chat_service: ChatServiceDep,
) -> AgentContextAssembler:
    return AgentContextAssembler(companies_service, prompts_service, chat_service)


AgentContextAssemblerDep = Annotated[AgentContextAssembler, Depends(agent_context_assembler)]
