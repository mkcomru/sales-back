"""LLM client for OpenAI-compatible Chat Completions API.

This module provides a unified interface for working with OpenAI-compatible
Chat Completions API through base_url/api_key/model configuration.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, TypeVar

import httpx
import structlog
from langfuse.openai import AsyncOpenAI  # type: ignore[attr-defined]
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel

from common import SalesAgentSettings

from src.sales_agent.core.llm.struct import parse_fallback, parse_openai_response
from src.sales_agent.core.llm.utils import (
    convert_messages_to_responses_input,
    convert_tools_to_responses,
    normalize_responses_output_to_chat_completion,
)
from src.sales_agent.core.telemetry import Tracer

log = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)

DEFAULT_TIMEOUT_SEC = 60.0
DEFAULT_BASE_URL_OPENAI = "https://api.openai.com/v1"


class LLMClient:
    """Client for OpenAI-compatible Chat Completions API.

    Configured via base_url/api_key/model settings.
    Supports GPT-5 models (o1/o3) with reasoning_effort/verbosity parameters.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        model: str,
        timeout: float = DEFAULT_TIMEOUT_SEC,
        extra_headers: dict[str, str] | None = None,
        use_langfuse_wrapper: bool = False,
    ):
        """Initialize LLM client.

        Args:
            base_url: Base URL for the API (e.g., https://api.openai.com/v1)
            api_key: API key for authentication
            model: Model name to use
            timeout: Request timeout in seconds
            extra_headers: Additional headers to include in requests
        """
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if extra_headers:
            headers.update(extra_headers)

        # Use Langfuse drop-in OpenAI client (no fallbacks)
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=httpx.Timeout(timeout),
            default_headers=headers if headers else None,
        )

    def _is_gpt5_model(self) -> bool:
        """Check if current model is GPT-5 (o1/o3) series.

        GPT-5 models use reasoning_effort and verbosity
        instead of temperature/max_completion_tokens.
        """
        return self.model.startswith(("o1", "o3", "gpt-5"))

    @classmethod
    def from_settings(cls, settings: SalesAgentSettings, model: str | None = None) -> LLMClient:
        """Create LLMClient from SalesAgentSettings.

        Args:
            settings: Application settings with LLM configuration
            model: Optional model name to override default. If not provided,
                uses large_model from settings.

        Returns:
            Configured LLMClient instance

        Raises:
            ValueError: If LLM configuration is invalid or missing
        """
        llm_config = settings.llm

        model_name = model or llm_config.large_model
        if not model_name:
            raise ValueError("No model configured")

        if not llm_config.api_key:
            raise ValueError("No API key configured")

        api_key = llm_config.api_key.get_secret_value()

        return cls(
            base_url=llm_config.base_url,
            api_key=api_key,
            model=model_name,
            use_langfuse_wrapper=bool(settings.langfuse and settings.langfuse.enabled),
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
        temperature: float | None = None,
        max_completion_tokens: int | None = None,
        reasoning_effort: str | None = None,
        verbosity: str | None = None,
        tracer: Tracer | None = None,
    ) -> dict[str, Any]:
        """Send a chat completion request.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            tools: Optional list of tool definitions (OpenAI format)
            tool_choice: Tool choice strategy ('auto', 'none', or tool dict)
            temperature: Sampling temperature (for non-GPT-5 models)
            max_completion_tokens: Maximum completion tokens to generate
                (for non-GPT-5 models).
            reasoning_effort: GPT-5 reasoning effort
                ("minimal", "low", "medium", "high")
            verbosity: GPT-5 verbosity ("low", "medium", "high")
            tracer: Optional tracer for telemetry

        Returns:
            Response dictionary with 'choices', 'usage', etc.

        Raises:
            Exception: If API request fails
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        is_gpt5 = self._is_gpt5_model()

        model_params: dict[str, Any] = {}
        if is_gpt5:
            if reasoning_effort:
                model_params["reasoning_effort"] = reasoning_effort
            if verbosity:
                model_params["verbosity"] = verbosity
        else:
            if temperature is not None:
                kwargs["temperature"] = temperature
                model_params["temperature"] = temperature
            if max_completion_tokens is not None:
                kwargs["max_completion_tokens"] = max_completion_tokens
                model_params["max_completion_tokens"] = max_completion_tokens
        if tools:
            model_params["tools_count"] = len(tools)
            model_params["tool_choice"] = tool_choice

        log.debug(
            "llm.chat.request",
            model=self.model,
            messages_count=len(messages),
            has_tools=bool(tools),
            tool_choice=tool_choice,
        )

        if is_gpt5:
            # Route GPT-5/o1/o3 through Responses API with unified normalization
            resp_input = convert_messages_to_responses_input(messages)

            resp_kwargs: dict[str, Any] = {
                "model": self.model,
                "input": resp_input,
            }
            if tools:
                resp_kwargs["tools"] = convert_tools_to_responses(tools)
                if tool_choice and tool_choice != "auto":
                    resp_kwargs["tool_choice"] = tool_choice
            if reasoning_effort:
                resp_kwargs["reasoning"] = {"effort": reasoning_effort}
            if verbosity:
                resp_kwargs["text"] = {"verbosity": verbosity}

            # Ensure GPT-5 specific params are visible in Langfuse via wrapper
            _meta: dict[str, Any] = {}
            if reasoning_effort:
                _meta["reasoning_effort"] = reasoning_effort
            if verbosity:
                _meta["verbosity"] = verbosity
            if _meta:
                resp_kwargs["metadata"] = _meta

            resp = await self._client.responses.create(**resp_kwargs)
            normalized = normalize_responses_output_to_chat_completion(resp)

            return normalized

        # Non-GPT-5: use Chat Completions as-is
        response = await self._client.chat.completions.create(**kwargs)

        if response.usage:
            usage_dict = response.usage.model_dump() if hasattr(response.usage, "model_dump") else {}
            log.debug("llm.usage_debug", usage=usage_dict)
            cache_stats = {k: v for k, v in usage_dict.items() if "cache" in k.lower() and v}
            if cache_stats:
                log.debug("llm.cache_stats", **cache_stats)

        return {
            "id": response.id,
            "choices": [
                {
                    "index": choice.index,
                    "message": {
                        "role": choice.message.role,
                        "content": choice.message.content,
                        "tool_calls": (
                            [
                                {
                                    "id": tc.id,
                                    "type": tc.type,
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments,
                                    },
                                }
                                for tc in choice.message.tool_calls or []
                            ]
                            if choice.message.tool_calls
                            else None
                        ),
                    },
                    "finish_reason": choice.finish_reason,
                }
                for choice in response.choices
            ],
            "usage": (
                {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
                if response.usage
                else None
            ),
        }

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
        temperature: float | None = None,
        max_completion_tokens: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Send a streaming chat completion request.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            tools: Optional list of tool definitions (OpenAI format)
            tool_choice: Tool choice strategy ('auto', 'none', or tool dict)
            temperature: Sampling temperature
            max_completion_tokens: Maximum completion tokens to generate

        Yields:
            Chunk dictionaries with delta content

        Raises:
            Exception: If API request fails
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        if temperature is not None:
            kwargs["temperature"] = temperature

        if max_completion_tokens is not None:
            kwargs["max_completion_tokens"] = max_completion_tokens

        log.debug(
            "llm.chat_stream.request",
            model=self.model,
            messages_count=len(messages),
            has_tools=bool(tools),
        )

        # Capture usage on final chunk per Langfuse/OpenAI best practices
        kwargs.setdefault("stream_options", {"include_usage": True})

        stream = await self._client.chat.completions.create(**kwargs)

        async for chunk in stream:
            yield {
                "id": chunk.id,
                "choices": [
                    {
                        "index": choice.index,
                        "delta": {
                            "role": choice.delta.role,
                            "content": choice.delta.content,
                        },
                        "finish_reason": choice.finish_reason,
                    }
                    for choice in chunk.choices
                ],
            }

    async def chat_parse(
        self,
        messages: list[dict[str, Any]],
        response_model: type[T],
        *,
        temperature: float | None = None,
        max_completion_tokens: int | None = None,
        reasoning_effort: str | None = None,
        verbosity: str | None = None,
        tracer: Tracer | None = None,
    ) -> T:
        """Send a chat completion request with structured output parsing.

        Uses native structured outputs for OpenAI models (response_format),
        falls back to JSON extraction + pydantic validation for other providers.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            response_model: Pydantic model class for structured output
            temperature: Sampling temperature (for non-GPT-5 models)
            max_completion_tokens: Maximum completion tokens to generate
                (for non-GPT-5 models).
            reasoning_effort: GPT-5 reasoning effort
                ("minimal", "low", "medium", "high")
            verbosity: GPT-5 verbosity ("low", "medium", "high")
            tracer: Optional tracer for telemetry

        Returns:
            Parsed and validated instance of response_model

        Raises:
            Exception: If API request fails or parsing fails
        """
        is_openai_provider = self.base_url == DEFAULT_BASE_URL_OPENAI
        is_gpt5 = self._is_gpt5_model()

        model_params: dict[str, Any] = {}
        if is_gpt5:
            if reasoning_effort:
                model_params["reasoning_effort"] = reasoning_effort
            if verbosity:
                model_params["verbosity"] = verbosity
        else:
            if temperature is not None:
                model_params["temperature"] = temperature
            if max_completion_tokens is not None:
                model_params["max_completion_tokens"] = max_completion_tokens
        model_params["response_model"] = response_model.__name__
        model_params["using_native"] = is_openai_provider

        # Try native structured outputs first when using Chat Completions API
        # regardless of exact base_url. Many OpenAI‑compatible providers
        # (including Claude via OpenAI Completions) support response_format
        # or the SDK's beta.parse helper. Fall back to schema-instruction JSON
        # extraction if the provider does not support it.
        try:
            if is_gpt5 and is_openai_provider:
                # Use Responses API for GPT‑5/o1/o3 models only on OpenAI
                system_parts = [m.get("content", "") for m in messages if m.get("role") == "system"]
                system_text = "\n\n".join([s for s in system_parts if s])
                user_text = next(
                    (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"),
                    "",
                )
                input_text = f"{system_text}\n\nUser: {user_text}" if system_text else user_text

                resp_kwargs: dict[str, Any] = {
                    "model": self.model,
                    "input": input_text,
                }
                if reasoning_effort:
                    resp_kwargs["reasoning"] = {"effort": reasoning_effort}
                if verbosity:
                    resp_kwargs["text"] = {"verbosity": verbosity}

                _meta: dict[str, Any] = {}
                if reasoning_effort:
                    _meta["reasoning_effort"] = reasoning_effort
                if verbosity:
                    _meta["verbosity"] = verbosity
                if _meta:
                    resp_kwargs["metadata"] = _meta

                resp = await self._client.responses.create(**resp_kwargs)
                content_text = getattr(resp, "output_text", None) or ""
                if not content_text:
                    raise ValueError("Empty response content")
                return parse_fallback(content_text, response_model)
            else:
                # Non‑GPT‑5 (or GPT‑5 through compatible proxy): attempt native parse
                typed_messages: list[ChatCompletionMessageParam] = messages  # type: ignore[assignment]

                schema = response_model.model_json_schema()
                parse_kwargs: dict[str, Any] = {
                    "model": self.model,
                    "messages": typed_messages,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": response_model.__name__.lower(),
                            "schema": schema,
                            "strict": True,
                        },
                    },
                }
                if temperature is not None:
                    parse_kwargs["temperature"] = temperature
                if max_completion_tokens is not None:
                    parse_kwargs["max_completion_tokens"] = max_completion_tokens

                response = await self._client.beta.chat.completions.parse(**parse_kwargs)
                parsed = response.choices[0].message.parsed
                if parsed is not None:
                    return parse_openai_response(response, response_model)
                content = response.choices[0].message.content
                if content:
                    return parse_fallback(content, response_model)
                raise ValueError("No parsed content or message content in OpenAI response")

        except Exception as e:
            log.warning(
                "llm.chat_parse.native_failed",
                error=str(e),
                fallback_to_json=True,
            )

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }

        if not is_gpt5:
            if temperature is not None:
                kwargs["temperature"] = temperature
            if max_completion_tokens is not None:
                kwargs["max_completion_tokens"] = max_completion_tokens

        schema = response_model.model_json_schema()
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": response_model.__name__.lower(),
                "schema": schema,
                "strict": True,
            },
        }

        log.debug(
            "llm.chat_parse.request",
            model=self.model,
            messages_count=len(messages),
            using_fallback=not is_openai_provider,
        )

        response = await self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response content")
        return parse_fallback(content, response_model)
