from __future__ import annotations

from typing import Any


def convert_messages_to_responses_input(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        tool_calls = m.get("tool_calls")

        # Plain system/user/assistant turns without tool calls (manager→assistant at pipeline level)
        if role in ("system", "user", "assistant") and not tool_calls:
            if isinstance(content, list):
                # Content blocks (e.g. from cache-aware prompts) — extract text
                text = " ".join(block["text"] for block in content if isinstance(block, dict) and block.get("text"))
                if text:
                    converted.append({"role": role, "content": text})
            elif content:
                converted.append({"role": role, "content": content})
            continue

        # Assistant messages with tool calls -> function_call items
        if tool_calls and isinstance(tool_calls, list):
            for tc in tool_calls:
                fn = (tc or {}).get("function", {})
                name = fn.get("name")
                args = fn.get("arguments")
                call_id = (tc or {}).get("id")
                if name and args is not None:
                    converted.append(
                        {
                            "type": "function_call",
                            "name": name,
                            "arguments": args,
                            "call_id": call_id,
                        }
                    )
            continue

        # Tool outputs -> function_call_output items
        if role == "tool":
            call_id = m.get("tool_call_id")
            out = content if isinstance(content, str) else ""
            if call_id and out is not None:
                converted.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": out,
                    }
                )
            continue

    return converted


def convert_tools_to_responses(tools_in: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resp_tools: list[dict[str, Any]] = []
    for t in tools_in:
        ttype = t.get("type")
        if ttype == "function":
            fn = t.get("function") or {}
            name = fn.get("name") or t.get("name")
            params = fn.get("parameters") or t.get("parameters")
            desc = fn.get("description") or t.get("description")
            if name:
                rt: dict[str, Any] = {
                    "type": "function",
                    "name": name,
                }
                if desc:
                    rt["description"] = desc
                if params:
                    rt["parameters"] = params
                resp_tools.append(rt)
        else:
            # pass-through for built-in tools (e.g., web_search) if present
            resp_tools.append(t)
    return resp_tools


def normalize_responses_output_to_chat_completion(resp_obj: Any) -> dict[str, Any]:
    tool_calls: list[dict[str, Any]] = []
    final_text: str = getattr(resp_obj, "output_text", None) or ""

    output_items = getattr(resp_obj, "output", None)
    if output_items:
        for item in output_items:
            itype = getattr(item, "type", None)
            if itype == "message":
                content = getattr(item, "content", None) or []
                texts: list[str] = []
                for c in content:
                    ctype = getattr(c, "type", None)
                    if ctype in ("output_text", "text"):
                        text_val = getattr(c, "text", None)
                        if text_val:
                            texts.append(text_val)
                if texts:
                    final_text = "".join(texts)
            if itype in ("function_call", "custom_tool_call", "mcp_call"):
                name = getattr(item, "name", None)
                args = getattr(item, "arguments", None)
                call_id = getattr(item, "id", None)
                if name and args is not None:
                    tool_calls.append(
                        {
                            "id": call_id or "",
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": args,
                            },
                        }
                    )

    return {
        "id": getattr(resp_obj, "id", ""),
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": final_text or None,
                    "tool_calls": tool_calls or None,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": None,
    }
