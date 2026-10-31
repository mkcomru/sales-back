"""Repository tests for prompts."""

from src.backend.modules.prompts.models import AgentType, Prompt
from src.backend.modules.prompts.repository import PromptsRepository


async def test_repository_list_empty():
    repo = PromptsRepository()
    prompts = await repo.list_all()
    assert prompts == []


async def test_repository_list_with_data():
    repo = PromptsRepository()
    await Prompt.create(agent_type=AgentType.AGENT, content="Agent content")
    prompts = await repo.list_all()
    assert len(prompts) == 1
    agent_types = {p.agent_type for p in prompts}
    assert AgentType.AGENT in agent_types


async def test_repository_get_by_agent_type_success():
    repo = PromptsRepository()
    await Prompt.create(agent_type=AgentType.AGENT, content="Test content")
    prompt = await repo.get_by_agent_type("agent")
    assert prompt is not None
    assert prompt.agent_type == AgentType.AGENT
    assert prompt.content == "Test content"


async def test_repository_get_by_agent_type_not_found():
    repo = PromptsRepository()
    prompt = await repo.get_by_agent_type("nonexistent")
    assert prompt is None


async def test_repository_upsert_prompt_create():
    repo = PromptsRepository()
    prompt = await repo.upsert_prompt("agent", "New content")
    assert prompt.agent_type == AgentType.AGENT
    assert prompt.content == "New content"
    assert isinstance(prompt.id, int)


async def test_repository_upsert_prompt_update():
    repo = PromptsRepository()
    await Prompt.create(agent_type=AgentType.AGENT, content="Original")
    prompt = await repo.upsert_prompt("agent", "Updated")
    assert prompt.content == "Updated"
    count = await Prompt.filter(agent_type=AgentType.AGENT).count()
    assert count == 1


async def test_repository_delete_by_agent_type_success():
    repo = PromptsRepository()
    await Prompt.create(agent_type=AgentType.AGENT, content="Test")
    deleted = await repo.delete_by_agent_type("agent")
    assert deleted is True
    prompt = await Prompt.get_or_none(agent_type=AgentType.AGENT)
    assert prompt is None


async def test_repository_delete_by_agent_type_not_found():
    repo = PromptsRepository()
    deleted = await repo.delete_by_agent_type("nonexistent")
    assert deleted is False
