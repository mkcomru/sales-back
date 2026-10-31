"""Utility functions for working with tool definitions."""


def merge_tools(company_tools: list[str], category_tools: list[str]) -> list[str]:
    """Merge company and category tools (set union).

    Returns deduplicated list of tool names.
    """
    return list(dict.fromkeys(company_tools + category_tools))
