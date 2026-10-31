from fastapi import APIRouter

from src.backend.modules.auth.dependencies import SuperuserDep
from src.backend.modules.prompts.dependencies import PromptsServiceDep
from src.backend.modules.prompts.models import AgentType
from src.backend.modules.prompts.schemas import PromptRequest, PromptResponse

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.get("/")
async def list_prompts(
    _superuser: SuperuserDep,
    prompts_service: PromptsServiceDep,
) -> list[PromptResponse]:
    prompts = await prompts_service.list_prompts()
    return [PromptResponse(id=p.id, agent_type=p.agent_type.value, content=p.content) for p in prompts]


@router.get("/{agent_type}")
async def get_prompt(
    agent_type: AgentType,
    _superuser: SuperuserDep,
    prompts_service: PromptsServiceDep,
) -> PromptResponse:
    prompt = await prompts_service.get_prompt(agent_type.value)
    return PromptResponse(id=prompt.id, agent_type=prompt.agent_type.value, content=prompt.content)


@router.put("/{agent_type}")
async def upsert_prompt(
    agent_type: AgentType,
    request: PromptRequest,
    _superuser: SuperuserDep,
    prompts_service: PromptsServiceDep,
) -> PromptResponse:
    prompt = await prompts_service.upsert_prompt(agent_type.value, request.content)
    return PromptResponse(id=prompt.id, agent_type=prompt.agent_type.value, content=prompt.content)


@router.delete("/{agent_type}")
async def delete_prompt(
    agent_type: AgentType,
    _superuser: SuperuserDep,
    prompts_service: PromptsServiceDep,
) -> dict:
    await prompts_service.delete_prompt(agent_type.value)
    return {"message": "Prompt deleted successfully"}
