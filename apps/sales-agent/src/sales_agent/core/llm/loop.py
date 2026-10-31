"""Tool loop implementation for OpenAI Chat Completions function calling."""

from __future__ import annotations

import inspect
import json
import re
from typing import Any

import httpx
import structlog

from src.sales_agent.core.llm.client import LLMClient
from src.sales_agent.core.telemetry import Tracer
from src.sales_agent.core.tools.spec import ToolSpec

log = structlog.get_logger()

MAX_TOOL_CALLS = 6
STEP_TIMEOUT_SEC = 60.0


# Provider-compat helpers
def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences like ```json ... ``` from a string.

    Some providers (notably via OpenRouter) occasionally wrap function.arguments
    in code fences; strip them so json.loads can succeed.
    """
    s = text.strip()

    if s.startswith("```"):
        lines = s.split("\n")
        if len(lines) > 1:
            s = "\n".join(lines[1:])
        if s.endswith("```"):
            s = s[:-3].strip()

    if s.startswith("```"):
        s = s[3:].strip()
    if s.endswith("```"):
        s = s[:-3].strip()

    return s.strip()


def _parse_tool_arguments(arguments: Any) -> dict[str, Any]:
    """Parse tool arguments into a dict, tolerating double-encoded JSON.

    - Pass through dict as-is
    - For strings: strip code fences and attempt up to two json.loads passes
    - Otherwise: return empty dict
    """
    if isinstance(arguments, dict):
        return arguments
    if arguments is None:
        return {}
    if not isinstance(arguments, str):
        return {}

    cleaned = _strip_code_fences(arguments)

    # Try up to two decode passes in case of double-encoded JSON
    current: Any = cleaned
    for _ in range(2):
        try:
            decoded = json.loads(current)
        except json.JSONDecodeError:
            break
        if isinstance(decoded, dict):
            return decoded
        if isinstance(decoded, str):
            current = decoded.strip()
            continue
        # Non-dict (e.g., list) is not universally mappable here
        return {}

    return {}


def extract_content_without_thinking(text: str) -> str:
    """Remove <thinking> blocks from Claude responses.

    Public utility for cleaning thinking tags from messages.
    """
    # Remove thinking blocks with their content
    cleaned = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL)
    return cleaned.strip()


def _is_claude_model(model: str) -> bool:
    """Check if model is Claude (Anthropic)."""
    model_lower = model.lower()
    return "claude" in model_lower or "anthropic" in model_lower


def _should_use_thinking(model: str) -> bool:
    """Determine if we should use <thinking> tags for this model."""
    return _is_claude_model(model)


async def run_tool_loop(
    llm: LLMClient,
    messages: list[dict[str, Any]],
    tools: list[ToolSpec],
    *,
    max_calls: int = MAX_TOOL_CALLS,
    stream: bool = False,
    temperature: float | None = None,
    max_completion_tokens: int | None = None,
    reasoning_effort: str | None = None,
    verbosity: str | None = None,
    tracer: Tracer | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Execute tool calling loop with LLM.

    Algorithm:
    1. Call llm.chat() with messages and tools
    2. If response contains tool_calls:
       - Execute each tool call using corresponding ToolSpec handler
       - Add tool response messages to conversation
       - Repeat from step 1
    3. Return final messages and assistant text

    Args:
        llm: LLMClient instance for API calls
        messages: Initial conversation messages (user/assistant/system)
        tools: List of ToolSpec instances available for calling
        max_calls: Maximum number of tool call iterations (default: MAX_TOOL_CALLS)
        stream: Whether to use streaming (not implemented for tool calls)
        temperature: Sampling temperature (for non-GPT-5 models)
        max_completion_tokens: Maximum completion tokens to generate
            (for non-GPT-5 models).
        reasoning_effort: GPT-5 reasoning effort ("minimal", "low", "medium", "high")
        verbosity: GPT-5 verbosity ("low", "medium", "high")
        tracer: Optional tracer for telemetry

    Returns:
        Tuple of (final_messages, final_text) where:
        - final_messages: Complete conversation including all tool calls/responses
        - final_text: Final assistant response text (None if only tool calls)

    Raises:
        ValueError: If max_calls exceeded or invalid tool call
        Exception: If LLM API call fails
    """
    if stream:
        log.warning("tool_loop.stream_not_supported", fallback_to_non_stream=True)

    tools_dict = {tool.name: tool for tool in tools}
    tools_openai = [tool.to_openai_tool() for tool in tools]

    current_messages = messages.copy()
    iterations = 0
    pre_tool_text: str | None = None

    while iterations < max_calls:
        iterations += 1

        log.debug(
            "tool_loop.iteration",
            iteration=iterations,
            messages_count=len(current_messages),
            tools_count=len(tools),
        )

        response = await llm.chat(
            messages=current_messages,
            tools=tools_openai if tools_openai else None,
            tool_choice="auto" if tools_openai else "none",
            temperature=temperature,
            max_completion_tokens=max_completion_tokens,
            reasoning_effort=reasoning_effort,
            verbosity=verbosity,
            tracer=tracer,
        )

        if not response.get("choices"):
            raise ValueError("Empty response from LLM")

        choice = response["choices"][0]
        message = choice["message"]
        finish_reason = choice.get("finish_reason")
        tool_calls = message.get("tool_calls")

        # AICODE-NOTE: Detect incomplete responses when model hits max_tokens limit
        # If finish_reason is "length" and response contains unclosed <thinking> tag,
        # treat as generation error and return empty text to trigger handoff
        if finish_reason == "length":
            message_content = message.get("content") or ""
            if message_content.startswith("<thinking>") and "</thinking>" not in message_content:
                log.error(
                    "llm.incomplete_thinking_response",
                    model=llm.model,
                    output_length=len(message_content),
                    finish_reason=finish_reason,
                    messages_count=len(current_messages),
                    iterations=iterations,
                )
                # Return empty text to signal error - caller should trigger handoff
                return current_messages, ""

        assistant_message: dict[str, Any] = {
            "role": message["role"],
            "content": message.get("content"),
        }

        if tool_calls:
            assistant_message["tool_calls"] = tool_calls
            current_messages.append(assistant_message)

            # If model returned text alongside tool calls, keep it as a fallback
            # for providers that produce an empty final message after tools.
            if assistant_message.get("content"):
                pre_tool_text = assistant_message["content"]
                # Clean thinking tags for Claude models
                if _is_claude_model(llm.model) and pre_tool_text:
                    pre_tool_text = extract_content_without_thinking(pre_tool_text)

            for tool_call in tool_calls:
                tool_id = tool_call["id"]
                tool_name = tool_call["function"]["name"]
                tool_args_raw = tool_call["function"]["arguments"]
                tool_args = _parse_tool_arguments(tool_args_raw)

                if tracer:
                    with tracer.start_span(
                        name=tool_name,
                        input=tool_args,
                        metadata={"tool_call_id": tool_id},
                    ):
                        if tool_name not in tools_dict:
                            error_msg = f"Unknown tool: {tool_name}"
                            log.error("tool_loop.unknown_tool", tool_name=tool_name)
                            tool_result = {"error": error_msg}
                            try:
                                tracer.update_current_span(output=tool_result)
                            except Exception:
                                pass
                        else:
                            tool_spec = tools_dict[tool_name]

                            try:
                                handler = tool_spec.handler
                                if inspect.iscoroutinefunction(handler):
                                    tool_result = await handler(tool_args)
                                else:
                                    tool_result = handler(tool_args)

                                if not isinstance(tool_result, dict):
                                    tool_result = {"result": tool_result}

                                log.debug(
                                    "tool_loop.tool_executed",
                                    tool=tool_name,
                                    has_result=True,
                                )
                                try:
                                    tracer.update_current_span(output=tool_result)
                                except Exception:
                                    pass
                            except httpx.HTTPStatusError as e:
                                response_body = e.response.text[:500]
                                error_msg = (
                                    f"HTTP {e.response.status_code} on "
                                    f"{e.request.method} {e.request.url}: {response_body}"
                                )
                                log.exception(
                                    "tool_loop.tool_error",
                                    tool=tool_name,
                                    status=e.response.status_code,
                                    url=str(e.request.url),
                                    response_body=response_body,
                                )
                                tool_result = {"error": error_msg}
                            except Exception as e:
                                error_msg = f"Tool execution failed: {e}"
                                log.exception(
                                    "tool_loop.tool_error",
                                    tool=tool_name,
                                    error=str(e),
                                )
                                tool_result = {"error": error_msg}
                                try:
                                    tracer.update_current_span(output=tool_result)
                                except Exception:
                                    pass
                else:
                    if tool_name not in tools_dict:
                        error_msg = f"Unknown tool: {tool_name}"
                        log.error("tool_loop.unknown_tool", tool_name=tool_name)
                        tool_result = {"error": error_msg}
                    else:
                        tool_spec = tools_dict[tool_name]

                        try:
                            handler = tool_spec.handler
                            if inspect.iscoroutinefunction(handler):
                                tool_result = await handler(tool_args)
                            else:
                                tool_result = handler(tool_args)

                            if not isinstance(tool_result, dict):
                                tool_result = {"result": tool_result}

                            log.debug(
                                "tool_loop.tool_executed",
                                tool=tool_name,
                                has_result=True,
                            )
                        except Exception as e:
                            error_msg = f"Tool execution failed: {e}"
                            log.exception(
                                "tool_loop.tool_error",
                                tool=tool_name,
                                error=str(e),
                            )
                            tool_result = {"error": error_msg}

                tool_response: dict[str, Any] = {
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": json.dumps(tool_result, ensure_ascii=False),
                }
                current_messages.append(tool_response)

        else:
            current_messages.append(assistant_message)
            final_text = message.get("content") or ""
            if not final_text and pre_tool_text:
                log.debug(
                    "tool_loop.pre_tool_text_used",
                    iterations=iterations,
                )
                final_text = pre_tool_text

            # Remove thinking blocks from Claude responses
            if _is_claude_model(llm.model) and final_text:
                final_text = extract_content_without_thinking(final_text)

            log.debug(
                "tool_loop.completed",
                iterations=iterations,
                final_text_length=len(final_text),
            )
            return current_messages, final_text

    raise ValueError(f"Tool loop exceeded max_calls ({max_calls}). Assistant may be calling tools indefinitely.")
