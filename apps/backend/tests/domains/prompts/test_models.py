"""Model tests for prompts."""

import pytest
from tortoise.exceptions import IntegrityError, ValidationError

from src.backend.modules.prompts.models import AgentType, Prompt


async def test_prompt_required_fields():
    with pytest.raises(ValidationError):
        await Prompt.create()


async def test_prompt_agent_type_required():
    with pytest.raises(ValidationError):
        await Prompt.create(content="Test content")


async def test_prompt_content_required():
    with pytest.raises(IntegrityError):
        await Prompt.create(agent_type=AgentType.AGENT)


async def test_prompt_unique_agent_type():
    await Prompt.create(agent_type=AgentType.AGENT, content="First prompt")
    with pytest.raises(IntegrityError):
        await Prompt.create(agent_type=AgentType.AGENT, content="Second prompt")


async def test_prompt_agent_type_enum():
    prompt = await Prompt.create(agent_type=AgentType.AGENT, content="Test")
    assert prompt.agent_type == AgentType.AGENT
    assert isinstance(prompt.agent_type, AgentType)


async def test_prompt_content_persists():
    content = "Test prompt content"
    prompt = await Prompt.create(agent_type=AgentType.AGENT, content=content)
    assert prompt.content == content
    prompt.content = "Updated content"
    await prompt.save()
    refreshed = await Prompt.get(id=prompt.id)
    assert refreshed.content == "Updated content"


async def test_prompt_all_agent_types():
    for agent_type in AgentType:
        content = f"{agent_type.value} content"
        prompt = await Prompt.create(agent_type=agent_type, content=content)
        assert prompt.agent_type == agent_type
