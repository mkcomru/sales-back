from tortoise.exceptions import DoesNotExist

from src.backend.modules.core.base_repo import BaseRepository
from src.backend.modules.prompts.models import AgentType, Prompt


class PromptsRepository(BaseRepository[Prompt]):
    def __init__(self):
        super().__init__(Prompt)

    async def get_by_agent_type(self, agent_type: str) -> Prompt | None:
        try:
            AgentType(agent_type)
        except ValueError:
            return None
        return await Prompt.get_or_none(agent_type=agent_type)

    async def upsert_prompt(self, agent_type: str, content: str) -> Prompt:
        try:
            AgentType(agent_type)
        except ValueError as e:
            raise ValueError(f"Invalid agent_type: {agent_type}") from e
        prompt, created = await Prompt.get_or_create(agent_type=agent_type, defaults={"content": content})
        if not created:
            prompt.content = content
            await prompt.save()
        return prompt

    async def list_all(self) -> list[Prompt]:
        return await Prompt.all()

    async def delete_by_agent_type(self, agent_type: str) -> bool:
        try:
            AgentType(agent_type)
        except ValueError:
            return False
        try:
            prompt = await Prompt.get(agent_type=agent_type)
            await prompt.delete()
            return True
        except DoesNotExist:
            return False
