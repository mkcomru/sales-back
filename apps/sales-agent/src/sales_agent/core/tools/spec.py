"""Tool specification for OpenAI Chat Completions function calling."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class ToolSpec:
    """Specification for a tool/function callable by LLM.

    Encapsulates tool metadata (name, description, parameters schema)
    and handler function for execution.
    """

    def __init__(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: (Callable[[dict[str, Any]], Any] | Callable[[dict[str, Any]], Awaitable[Any]]),
    ):
        """Initialize tool specification.

        Args:
            name: Tool name (must match OpenAI function naming rules)
            description: Human-readable description for LLM
            parameters: JSON Schema dict for function parameters
            handler: Async or sync callable that executes the tool with parsed args
        """
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler

    def to_openai_tool(self) -> dict[str, Any]:
        """Convert ToolSpec to OpenAI Chat Completions tool format.

        Returns:
            Dictionary in OpenAI tools format:
            {
                "type": "function",
                "function": {
                    "name": "...",
                    "description": "...",
                    "parameters": {...}
                }
            }
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def to_openai_tool(spec: ToolSpec) -> dict[str, Any]:
    """Helper to convert ToolSpec to OpenAI tool format.

    Args:
        spec: ToolSpec instance

    Returns:
        OpenAI tool dictionary
    """
    return spec.to_openai_tool()
