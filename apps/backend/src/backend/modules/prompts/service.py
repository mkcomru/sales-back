from common.events.contracts import ChangeType

from src.backend.modules.prompts.exceptions import PromptNotFoundError
from src.backend.modules.prompts.models import Prompt
from src.backend.modules.prompts.repository import PromptsRepository
from src.backend.services.events import publish_prompt_changed


class PromptsService:
    repository: PromptsRepository = PromptsRepository()

    async def get_prompt(self, agent_type: str) -> Prompt:
        prompt = await self.repository.get_by_agent_type(agent_type)

        if not prompt:
            raise PromptNotFoundError()

        return prompt

    async def upsert_prompt(self, agent_type: str, content: str) -> Prompt:
        prompt = await self.repository.upsert_prompt(agent_type, content)
        await publish_prompt_changed(agent_type=agent_type, change_type=ChangeType.UPSERT)
        return prompt

    async def list_prompts(self) -> list[Prompt]:
        return await self.repository.list_all()

    async def delete_prompt(self, agent_type: str) -> bool:
        deleted = await self.repository.delete_by_agent_type(agent_type)

        if not deleted:
            raise PromptNotFoundError()

        await publish_prompt_changed(agent_type=agent_type, change_type=ChangeType.DELETE)
        return True
