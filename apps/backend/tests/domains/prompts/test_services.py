"""Service tests for prompts."""

import pytest

from src.backend.modules.prompts.exceptions import PromptNotFoundError
from src.backend.modules.prompts.models import AgentType, Prompt
from src.backend.modules.prompts.service import PromptsService


async def test_service_list_prompts_empty():
    service = PromptsService()
    prompts = await service.list_prompts()
    assert prompts == []


async def test_service_list_prompts_with_data():
    service = PromptsService()
    await Prompt.create(agent_type=AgentType.AGENT, content="Agent content")
    prompts = await service.list_prompts()
    assert len(prompts) == 1


async def test_service_get_prompt_success():
    service = PromptsService()
    await Prompt.create(agent_type=AgentType.AGENT, content="Test content")
    prompt = await service.get_prompt("agent")
    assert prompt.agent_type == AgentType.AGENT
    assert prompt.content == "Test content"


async def test_service_get_prompt_not_found():
    service = PromptsService()
    with pytest.raises(PromptNotFoundError):
        await service.get_prompt("nonexistent")


async def test_service_upsert_prompt_create():
    service = PromptsService()
    prompt = await service.upsert_prompt("agent", "New content")
    assert prompt.agent_type == AgentType.AGENT
    assert prompt.content == "New content"


async def test_service_upsert_prompt_update():
    service = PromptsService()
    await Prompt.create(agent_type=AgentType.AGENT, content="Original")
    prompt = await service.upsert_prompt("agent", "Updated")
    assert prompt.content == "Updated"


async def test_service_delete_prompt_success():
    service = PromptsService()
    await Prompt.create(agent_type=AgentType.AGENT, content="Test")
    deleted = await service.delete_prompt("agent")
    assert deleted is True
    with pytest.raises(PromptNotFoundError):
        await service.get_prompt("agent")


async def test_service_delete_prompt_not_found():
    service = PromptsService()
    with pytest.raises(PromptNotFoundError):
        await service.delete_prompt("nonexistent")
