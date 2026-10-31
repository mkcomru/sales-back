"""Tool specifications and registry for single-agent pipeline."""

from src.sales_agent.core.tools.registry import build_tools
from src.sales_agent.core.tools.spec import ToolSpec, to_openai_tool

__all__ = [
    "ToolSpec",
    "to_openai_tool",
    "build_tools",
]
