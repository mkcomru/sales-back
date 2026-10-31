"""Tests for LLM tool loop with mocked LLM client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.sales_agent.core.llm.client import LLMClient
from src.sales_agent.core.llm.loop import run_tool_loop
from src.sales_agent.core.tools.spec import ToolSpec


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Mock LLMClient for testing."""
    client = MagicMock(spec=LLMClient)
    client.chat = AsyncMock()
    client.model = "gpt-4"
    return client


@pytest.fixture
def sample_tool() -> ToolSpec:
    """Sample tool for testing."""

    async def handler(args: dict) -> dict:
        return {"result": f"Processed: {args.get('input', '')}"}

    return ToolSpec(
        name="test_tool",
        description="Test tool",
        parameters={
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Input text"},
            },
            "required": ["input"],
        },
        handler=handler,
    )


@pytest.mark.asyncio
async def test_tool_loop_simple_response_no_tools(
    mock_llm_client: MagicMock,
) -> None:
    """Test tool loop returns simple response when no tools are called."""
    mock_response = {
        "id": "chat-1",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hello, world!",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"total_tokens": 10},
    }
    mock_llm_client.chat.return_value = mock_response

    messages = [{"role": "user", "content": "Hello"}]
    tools: list[ToolSpec] = []

    final_messages, final_text = await run_tool_loop(
        mock_llm_client,
        messages,
        tools,
    )

    assert final_text == "Hello, world!"
    assert len(final_messages) == 2
    assert final_messages[-1]["role"] == "assistant"
    assert final_messages[-1]["content"] == "Hello, world!"


@pytest.mark.asyncio
async def test_tool_loop_single_tool_call(
    mock_llm_client: MagicMock,
    sample_tool: ToolSpec,
) -> None:
    """Test tool loop executes single tool call and returns final response."""
    tool_call_response = {
        "id": "chat-1",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "test_tool",
                                "arguments": '{"input": "test"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"total_tokens": 10},
    }

    final_response = {
        "id": "chat-2",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Tool executed successfully!",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"total_tokens": 10},
    }

    mock_llm_client.chat.side_effect = [tool_call_response, final_response]

    messages = [{"role": "user", "content": "Use test_tool with input 'test'"}]

    final_messages, final_text = await run_tool_loop(
        mock_llm_client,
        messages,
        [sample_tool],
    )

    assert final_text == "Tool executed successfully!"
    assert mock_llm_client.chat.call_count == 2

    tool_messages = [m for m in final_messages if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert "Processed: test" in tool_messages[0]["content"]


@pytest.mark.asyncio
async def test_tool_loop_multiple_tool_calls(
    mock_llm_client: MagicMock,
    sample_tool: ToolSpec,
) -> None:
    """Test tool loop handles multiple tool calls in sequence."""
    tool_call_1 = {
        "id": "chat-1",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "test_tool",
                                "arguments": '{"input": "first"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"total_tokens": 10},
    }

    tool_call_2 = {
        "id": "chat-2",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-2",
                            "type": "function",
                            "function": {
                                "name": "test_tool",
                                "arguments": '{"input": "second"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"total_tokens": 10},
    }

    final_response = {
        "id": "chat-3",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "All tools executed!",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"total_tokens": 10},
    }

    mock_llm_client.chat.side_effect = [tool_call_1, tool_call_2, final_response]

    messages = [{"role": "user", "content": "Use test_tool twice"}]

    final_messages, final_text = await run_tool_loop(
        mock_llm_client,
        messages,
        [sample_tool],
    )

    assert final_text == "All tools executed!"
    assert mock_llm_client.chat.call_count == 3

    tool_messages = [m for m in final_messages if m.get("role") == "tool"]
    assert len(tool_messages) == 2


@pytest.mark.asyncio
async def test_tool_loop_unknown_tool_returns_error(
    mock_llm_client: MagicMock,
) -> None:
    """Test tool loop handles unknown tool gracefully."""
    tool_call_response = {
        "id": "chat-1",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "unknown_tool",
                                "arguments": '{"input": "test"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"total_tokens": 10},
    }

    final_response = {
        "id": "chat-2",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "I'll try a different approach.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"total_tokens": 10},
    }

    mock_llm_client.chat.side_effect = [tool_call_response, final_response]

    messages = [{"role": "user", "content": "Use unknown_tool"}]

    final_messages, final_text = await run_tool_loop(
        mock_llm_client,
        messages,
        [],
    )

    assert "different approach" in final_text
    tool_messages = [m for m in final_messages if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert "error" in tool_messages[0]["content"].lower()


@pytest.mark.asyncio
async def test_tool_loop_tool_execution_error_handled(
    mock_llm_client: MagicMock,
) -> None:
    """Test tool loop handles tool execution errors gracefully."""

    async def failing_handler(args: dict) -> dict:
        raise ValueError("Tool execution failed")

    failing_tool = ToolSpec(
        name="failing_tool",
        description="Tool that fails",
        parameters={
            "type": "object",
            "properties": {},
        },
        handler=failing_handler,
    )

    tool_call_response = {
        "id": "chat-1",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "failing_tool",
                                "arguments": "{}",
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"total_tokens": 10},
    }

    final_response = {
        "id": "chat-2",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "I'll handle the error.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"total_tokens": 10},
    }

    mock_llm_client.chat.side_effect = [tool_call_response, final_response]

    messages = [{"role": "user", "content": "Use failing_tool"}]

    final_messages, final_text = await run_tool_loop(
        mock_llm_client,
        messages,
        [failing_tool],
    )

    assert "handle the error" in final_text
    tool_messages = [m for m in final_messages if m.get("role") == "tool"]
    assert len(tool_messages) == 1
    assert "error" in tool_messages[0]["content"].lower()


@pytest.mark.asyncio
async def test_tool_loop_max_calls_exceeded_raises(
    mock_llm_client: MagicMock,
    sample_tool: ToolSpec,
) -> None:
    """Test tool loop raises error when max_calls exceeded."""
    tool_call_response = {
        "id": "chat-1",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "test_tool",
                                "arguments": '{"input": "test"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"total_tokens": 10},
    }

    mock_llm_client.chat.return_value = tool_call_response

    messages = [{"role": "user", "content": "Use test_tool"}]

    with pytest.raises(ValueError, match="exceeded max_calls"):
        await run_tool_loop(
            mock_llm_client,
            messages,
            [sample_tool],
            max_calls=2,
        )


@pytest.mark.asyncio
async def test_tool_loop_text_with_tool_calls_preserved(
    mock_llm_client: MagicMock,
    sample_tool: ToolSpec,
) -> None:
    """Test tool loop preserves text content when tool calls are also present."""
    tool_call_with_text = {
        "id": "chat-1",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Let me check that for you.",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "test_tool",
                                "arguments": '{"input": "test"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"total_tokens": 10},
    }

    final_response = {
        "id": "chat-2",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"total_tokens": 10},
    }

    mock_llm_client.chat.side_effect = [tool_call_with_text, final_response]

    messages = [{"role": "user", "content": "Check something"}]

    final_messages, final_text = await run_tool_loop(
        mock_llm_client,
        messages,
        [sample_tool],
    )

    assert final_text == "Let me check that for you."
