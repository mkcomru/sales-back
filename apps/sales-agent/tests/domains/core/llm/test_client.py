"""Tests for LLM client module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr

from common import SalesAgentSettings

from src.sales_agent.core.llm.client import LLMClient

TEST_API_KEY = "test-key"  # pragma: allowlist secret


class TestLLMClientInit:
    """Test LLMClient initialization."""

    def test_init_success(self) -> None:
        """Test successful initialization."""
        client = LLMClient(
            base_url="https://api.openai.com/v1",
            api_key=TEST_API_KEY,
            model="gpt-4",
        )

        assert client.base_url == "https://api.openai.com/v1"
        assert client.api_key == TEST_API_KEY
        assert client.model == "gpt-4"
        assert client.timeout == 60.0

    def test_init_with_custom_timeout(self) -> None:
        """Test initialization with custom timeout."""
        client = LLMClient(
            base_url="https://api.openai.com/v1",
            api_key=TEST_API_KEY,
            model="gpt-4",
            timeout=30.0,
        )

        assert client.timeout == 30.0

    def test_init_with_extra_headers(self) -> None:
        """Test initialization with extra headers."""
        client = LLMClient(
            base_url="https://api.openai.com/v1",
            api_key=TEST_API_KEY,
            model="gpt-4",
            extra_headers={"X-Custom": "value"},
        )

        assert client._client is not None


class TestLLMClientFromSettings:
    """Test LLMClient.from_settings method."""

    def test_from_settings_success(self, settings: SalesAgentSettings) -> None:
        """Test creating client from settings."""
        settings.llm.base_url = "https://api.openai.com/v1"
        settings.llm.api_key = SecretStr(TEST_API_KEY)
        settings.llm.large_model = "gpt-4"

        client = LLMClient.from_settings(settings)

        assert client.model == "gpt-4"
        assert client.base_url == "https://api.openai.com/v1"

    def test_from_settings_custom_model(self, settings: SalesAgentSettings) -> None:
        """Test from_settings with custom model override."""
        settings.llm.base_url = "https://api.openai.com/v1"
        settings.llm.api_key = SecretStr(TEST_API_KEY)
        settings.llm.large_model = "gpt-4"

        client = LLMClient.from_settings(settings, model="gpt-3.5-turbo")

        assert client.model == "gpt-3.5-turbo"

    def test_from_settings_missing_model_raises_error(self, settings: SalesAgentSettings) -> None:
        """Test from_settings raises error when model is missing."""
        settings.llm.base_url = "https://api.openai.com/v1"
        settings.llm.api_key = SecretStr(TEST_API_KEY)
        settings.llm.large_model = None

        with pytest.raises(ValueError, match="No model configured"):
            LLMClient.from_settings(settings)

    def test_from_settings_missing_api_key_raises_error(self, settings: SalesAgentSettings) -> None:
        """Test from_settings raises error when API key is missing."""
        settings.llm.base_url = "https://api.openai.com/v1"
        settings.llm.api_key = None
        settings.llm.large_model = "gpt-4"

        with pytest.raises(ValueError, match="No API key configured"):
            LLMClient.from_settings(settings)


class TestIsGPT5Model:
    """Test _is_gpt5_model method."""

    def test_is_gpt5_model_o1(self) -> None:
        """Test o1 model is detected as GPT-5."""
        client = LLMClient(
            base_url="https://api.openai.com/v1",
            api_key=TEST_API_KEY,
            model="o1-preview",
        )

        assert client._is_gpt5_model() is True

    def test_is_gpt5_model_o3(self) -> None:
        """Test o3 model is detected as GPT-5."""
        client = LLMClient(
            base_url="https://api.openai.com/v1",
            api_key=TEST_API_KEY,
            model="o3-mini",
        )

        assert client._is_gpt5_model() is True

    def test_is_gpt5_model_gpt5(self) -> None:
        """Test gpt-5 model is detected as GPT-5."""
        client = LLMClient(
            base_url="https://api.openai.com/v1",
            api_key=TEST_API_KEY,
            model="gpt-5",
        )

        assert client._is_gpt5_model() is True

    def test_is_gpt5_model_gpt4(self) -> None:
        """Test gpt-4 model is not detected as GPT-5."""
        client = LLMClient(
            base_url="https://api.openai.com/v1",
            api_key=TEST_API_KEY,
            model="gpt-4",
        )

        assert client._is_gpt5_model() is False


class TestChat:
    """Test chat method."""

    @pytest.mark.asyncio
    async def test_chat_success(self) -> None:
        """Test successful chat completion."""
        client = LLMClient(
            base_url="https://api.openai.com/v1",
            api_key=TEST_API_KEY,
            model="gpt-4",
        )

        mock_response = MagicMock()
        mock_response.id = "chatcmpl-123"
        mock_choice = MagicMock()
        mock_choice.index = 0
        mock_choice.message.role = "assistant"
        mock_choice.message.content = "Hello!"
        mock_choice.message.tool_calls = None
        mock_response.choices = [mock_choice]
        mock_response.usage.total_tokens = 10

        client._client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await client.chat(messages=[{"role": "user", "content": "Hello"}])

        assert result["id"] == "chatcmpl-123"
        assert len(result["choices"]) == 1
        assert result["choices"][0]["message"]["content"] == "Hello!"

    @pytest.mark.asyncio
    async def test_chat_with_tools(self) -> None:
        """Test chat with tools."""
        client = LLMClient(
            base_url="https://api.openai.com/v1",
            api_key=TEST_API_KEY,
            model="gpt-4",
        )

        mock_response = MagicMock()
        mock_response.id = "chatcmpl-123"
        mock_choice = MagicMock()
        mock_choice.index = 0
        mock_choice.message.role = "assistant"
        mock_choice.message.content = None
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call-1"
        mock_tool_call.type = "function"
        mock_tool_call.function.name = "test_function"
        mock_tool_call.function.arguments = '{"arg": "value"}'
        mock_choice.message.tool_calls = [mock_tool_call]
        mock_response.choices = [mock_choice]
        mock_response.usage.total_tokens = 20

        client._client.chat.completions.create = AsyncMock(return_value=mock_response)

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_function",
                    "description": "Test function",
                    "parameters": {},
                },
            }
        ]

        result = await client.chat(
            messages=[{"role": "user", "content": "Hello"}],
            tools=tools,
        )

        assert result["choices"][0]["message"]["tool_calls"] is not None
        assert len(result["choices"][0]["message"]["tool_calls"]) == 1

    @pytest.mark.asyncio
    async def test_chat_gpt5_model(self) -> None:
        """Test chat with GPT-5 model uses Responses API."""
        client = LLMClient(
            base_url="https://api.openai.com/v1",
            api_key=TEST_API_KEY,
            model="o1-preview",
        )

        mock_response = MagicMock()
        mock_response.id = "resp-123"
        mock_output = MagicMock()
        mock_output.text = "Hello from GPT-5!"
        mock_response.output = mock_output
        mock_response.usage.total_tokens = 10

        client._client.responses.create = AsyncMock(return_value=mock_response)

        result = await client.chat(
            messages=[{"role": "user", "content": "Hello"}],
            reasoning_effort="medium",
        )

        assert result["id"] == "resp-123"
        client._client.responses.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_with_temperature(self) -> None:
        """Test chat with temperature parameter."""
        client = LLMClient(
            base_url="https://api.openai.com/v1",
            api_key=TEST_API_KEY,
            model="gpt-4",
        )

        mock_response = MagicMock()
        mock_response.id = "chatcmpl-123"
        mock_choice = MagicMock()
        mock_choice.index = 0
        mock_choice.message.role = "assistant"
        mock_choice.message.content = "Hello!"
        mock_choice.message.tool_calls = None
        mock_response.choices = [mock_choice]
        mock_response.usage.total_tokens = 10

        client._client.chat.completions.create = AsyncMock(return_value=mock_response)

        await client.chat(
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.7,
        )

        call_kwargs = client._client.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.7
