"""Tool registry — single build_tools() for unified agent pipeline."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from common import SalesAgentSettings as Settings
from common.models.io import SimpleMessage
from common.tools import TOOL_DESCRIPTIONS_BY_NAME, AvailableTool

from src.sales_agent.agents import tools as agent_tools
from src.sales_agent.core.tools.spec import ToolSpec

# Single source of truth for tool parameter schemas.
# Used both for OpenAI tool calling and prompt formatting.
TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "update_fields": {
        "type": "object",
        "properties": {
            "updates": {
                "type": "object",
                "description": (
                    "Словарь полей для обновления (ключ: значение). Используй ключи из списка полей компании."
                ),
            }
        },
        "required": ["updates"],
    },
    "search_kb": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Вопрос пользователя для поиска в базе знаний",
            }
        },
        "required": ["question"],
    },
    "geo_metrics": {
        "type": "object",
        "properties": {
            "address": {
                "type": "string",
                "description": ("Адрес для анализа гео-метрик (расстояние до метро, расстояние до КАД)"),
            }
        },
        "required": ["address"],
    },
    "handoff": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Краткое содержание разговора для передачи менеджеру",
            },
            "reason": {
                "type": "string",
                "description": "Причина передачи (например: 'complex_question', 'user_request')",
            },
            "escalate": {
                "type": "boolean",
                "description": (
                    "true = жёсткая передача: AI немедленно прекращает отвечать. "
                    "false (по умолчанию) = мягкая передача: AI продолжает отвечать до первого сообщения менеджера."
                ),
            },
        },
        "required": ["summary", "reason"],
    },
    "schedule_reminder": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "What to remind about, e.g. 'Позвонить клиенту'",
            },
            "delay_minutes": {
                "type": "integer",
                "description": "How many minutes from now to send the reminder (e.g. 60 = 1 hour, 1440 = 1 day)",
                "minimum": 1,
            },
            "description": {
                "type": "string",
                "description": "Additional details (optional)",
            },
        },
        "required": ["title", "delay_minutes"],
    },
    "search_product": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search keywords: product name, key features, or what the customer is looking for",
            },
        },
        "required": ["query"],
    },
    "update_order_stage": {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "integer",
                "description": "Идентификатор заказа для обновления стадии (из контекста)",
            },
            "stage": {
                "type": "string",
                "description": "Новая стадия (например: new, qualification, offer, negotiation, closed)",
            },
        },
        "required": ["order_id", "stage"],
    },
    "close_order": {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "integer",
                "description": "Идентификатор заказа для закрытия (из контекста)",
            },
            "result": {
                "type": "string",
                "enum": ["won", "lost"],
                "description": "Результат заказа: 'won' (выигран) или 'lost' (проигран)",
            },
            "reason": {
                "type": "string",
                "description": "Опциональная причина закрытия (например: 'клиент отказался', 'сделка завершена')",
            },
        },
        "required": ["order_id", "result"],
    },
    "get_booking_services": {
        "type": "object",
        "properties": {
            "staff_id": {
                "type": "integer",
                "description": "Фильтр по мастеру — вернуть только его услуги (с длительностями)",
            },
        },
        "required": [],
    },
    "list_staff": {
        "type": "object",
        "properties": {
            "service_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Фильтр по услугам — вернуть только мастеров, оказывающих эти услуги",
            },
        },
        "required": [],
    },
    "get_available_dates": {
        "type": "object",
        "properties": {
            "staff_id": {
                "type": "integer",
                "description": "ID мастера",
            },
            "service_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "ID услуг — если уже известны, передавай для точной доступности по услуге",
            },
        },
        "required": ["staff_id"],
    },
    "get_available_slots": {
        "type": "object",
        "properties": {
            "staff_id": {
                "type": "integer",
                "description": "ID мастера (0 = любой свободный)",
            },
            "date": {
                "type": "string",
                "description": "Дата в формате YYYY-MM-DD",
            },
            "service_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "ID услуг — критично для расчёта длительности слотов",
            },
        },
        "required": ["staff_id", "date", "service_ids"],
    },
    "create_booking": {
        "type": "object",
        "properties": {
            "phone": {
                "type": "string",
                "description": "Телефон клиента (формат: 79001234567)",
            },
            "fullname": {
                "type": "string",
                "description": "Полное имя клиента",
            },
            "email": {
                "type": "string",
                "description": "Email клиента (опционально)",
            },
            "comment": {
                "type": "string",
                "description": "Комментарий к записи (опционально)",
            },
            "appointments": {
                "type": "array",
                "description": "Список записей (услуга + мастер + время)",
                "items": {
                    "type": "object",
                    "properties": {
                        "service_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "ID услуг",
                        },
                        "staff_id": {
                            "type": "integer",
                            "description": "ID мастера",
                        },
                        "datetime": {
                            "type": "string",
                            "description": "Дата и время слота (из get_available_slots)",
                        },
                    },
                    "required": ["service_ids", "staff_id", "datetime"],
                },
            },
        },
        "required": ["phone", "fullname", "appointments"],
    },
}


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences to help JSON parsing for provider quirks."""
    if not isinstance(text, str):
        return text  # type: ignore[return-value]

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


def _normalize_updates_input(raw: Any) -> dict[str, Any]:
    """Normalize various shapes of `updates` into a flat dict[str, Any].

    Accepted forms:
    - dict: {key: value}
    - list of {key,value} | {name,val} | {field,value}
    - list of [key, value]
    - string: JSON or "k=v, k2=v2"
    """
    if raw is None:
        return {}

    # String input: could be JSON or k=v pairs
    if isinstance(raw, str):
        s = _strip_code_fences(raw)
        # Try up to two JSON decodes to handle double-encoding
        current: Any = s
        for _ in range(2):
            try:
                decoded = json.loads(current)
            except json.JSONDecodeError:
                break
            if isinstance(decoded, dict):
                return dict(decoded)
            if isinstance(decoded, str):
                current = decoded.strip()
                continue
            if isinstance(decoded, list):
                raw = decoded
                break
            return {}
        else:
            # If loop didn't break, decoded handled; but we return above when dict
            pass

        # Fallback: parse "k=v" pairs
        parts = [p for p in (seg.strip() for seg in s.split(",")) if "=" in p]
        if parts:
            result: dict[str, Any] = {}
            for part in parts:
                k, v = part.split("=", 1)
                result[k.strip()] = v.strip()
            return result
        return {}

    # Dict input
    if isinstance(raw, dict):
        return dict(raw)

    # List input
    if isinstance(raw, list):
        out: dict[str, Any] = {}
        for item in raw:
            if isinstance(item, dict):
                key = item.get("key") or item.get("name") or item.get("field")
                if key is None:
                    continue
                out[str(key)] = item.get("value") if "value" in item else item.get("val")
                continue
            if isinstance(item, (list, tuple)) and len(item) == 2:
                k, v = item
                out[str(k)] = v
                continue
            if isinstance(item, str) and "=" in item:
                k, v = item.split("=", 1)
                out[k.strip()] = v.strip()
        return out

    # Unsupported shape
    return {}


def _create_update_fields_handler(user_id: int | str, company_id: int, order_id: int | None = None) -> Any:
    """Create handler for update_fields tool."""

    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        raw_updates = args.get("updates") if isinstance(args, dict) else None
        updates_map = _normalize_updates_input(raw_updates)
        if not updates_map:
            return {"updated_customer": [], "updated_order": [], "updated_extra": [], "rejected": []}

        result = await agent_tools.update_fields(
            user_id=user_id,
            company_id=company_id,
            updates=updates_map,
            order_id=order_id,
        )
        return result.model_dump()

    return handler


def _create_search_kb_handler(user_id: int | str, company_id: int) -> Any:
    """Create handler for search_kb tool."""

    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        result = await agent_tools.search_knowledge_base(
            user_id=user_id, question=args["question"], company_id=company_id
        )
        return result.model_dump()

    return handler


def _create_geo_metrics_handler() -> Any:
    """Create handler for geo_metrics tool."""

    async def handler(args: dict[str, Any]) -> dict[str, int | float]:
        result = await agent_tools.geo_metrics(args["address"])
        return result.model_dump()

    return handler


def _create_handoff_handler(
    settings: Settings, user_id: int | str, message: SimpleMessage | None, order_id: int | None = None
) -> Any:
    """Create handler for handoff tool — delegates to unified request_handoff path."""

    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        if not order_id:
            return {"success": False, "error": "order_id is required"}
        result = await agent_tools.request_handoff(
            settings=settings,
            order_id=order_id,
            summary=args.get("summary", "Передача менеджеру"),
            reason=args.get("reason", "Требуется участие менеджера"),
            escalate=bool(args.get("escalate", False)),
            message=message,
        )
        return result.model_dump()

    return handler


def _create_search_product_handler() -> Any:
    """Create handler for search_product tool."""

    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        result = await agent_tools.search_product(query=args["query"])
        return result.model_dump()

    return handler


def _create_update_order_stage_handler(order_id: int | None = None) -> Any:
    """Create handler for update_order_stage tool.

    Args:
        order_id: Order identifier to update (injected from context)
    """

    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        # Use order_id from context if not provided in args
        target_order_id = args.get("order_id") or order_id
        if not target_order_id:
            return {"success": False, "error": "order_id is required"}

        result = await agent_tools.update_order_stage(
            order_id=int(target_order_id),
            stage=args["stage"],
        )
        return result.model_dump()

    return handler


def _create_close_order_handler(order_id: int | None = None) -> Any:
    """Create handler for close_order tool.

    Args:
        order_id: Order identifier to close (injected from context)
    """

    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        # Use order_id from context if not provided in args
        target_order_id = args.get("order_id") or order_id
        if not target_order_id:
            return {"success": False, "error": "order_id is required"}

        result = await agent_tools.close_order(
            order_id=int(target_order_id),
            result=args["result"],
            reason=args.get("reason"),
        )
        return result.model_dump()

    return handler


def _create_schedule_reminder_handler(company_id: int, order_id: int | None = None) -> Any:
    """Create handler for schedule_reminder tool.

    Follows existing pattern from build_qualifier_tools where order_id
    is injected via closure, not passed by AI.
    """

    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        from src.sales_agent.storage.customer_store import get_backend_client

        backend_client = get_backend_client()

        if not order_id:
            return {"success": False, "error": "order_id is required"}

        delay_minutes = int(args["delay_minutes"])
        if delay_minutes < 1:
            return {"success": False, "error": "delay_minutes must be at least 1"}

        due_date = datetime.now(UTC) + timedelta(minutes=delay_minutes)

        payload = {
            "title": args["title"],
            "due_date": due_date.isoformat(),
            "description": args.get("description"),
            "type": "ai_scheduled",
            "auto_action": "send_followup_message",
        }

        result = await backend_client.create_order_task(
            company_id=company_id,
            order_id=order_id,
            data=payload,
        )
        return {"success": True, "task_id": result["id"], "due_date": result["due_date"]}

    return handler


def _create_get_booking_services_handler(company_id: int) -> Any:
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        from src.sales_agent.storage.customer_store import get_backend_client

        backend = get_backend_client()
        return await backend.get_booking_services(
            company_id=company_id,
            staff_id=args.get("staff_id"),
        )

    return handler


def _create_list_staff_handler(company_id: int) -> Any:
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        from src.sales_agent.storage.customer_store import get_backend_client

        backend = get_backend_client()
        return await backend.list_staff(
            company_id=company_id,
            service_ids=args.get("service_ids"),
        )

    return handler


def _create_get_available_dates_handler(company_id: int) -> Any:
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        from src.sales_agent.storage.customer_store import get_backend_client

        backend = get_backend_client()
        return await backend.get_available_dates(
            company_id=company_id,
            staff_id=args["staff_id"],
            service_ids=args.get("service_ids"),
        )

    return handler


def _create_get_available_slots_handler(company_id: int) -> Any:
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        from src.sales_agent.storage.customer_store import get_backend_client

        backend = get_backend_client()
        return await backend.get_available_slots(
            company_id=company_id,
            staff_id=args["staff_id"],
            date=args["date"],
            service_ids=args.get("service_ids"),
        )

    return handler


def _create_create_booking_handler(company_id: int) -> Any:
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        from src.sales_agent.storage.customer_store import get_backend_client

        backend = get_backend_client()
        return await backend.create_booking(
            company_id=company_id,
            phone=args["phone"],
            fullname=args["fullname"],
            email=args.get("email", ""),
            comment=args.get("comment", ""),
            appointments=args.get("appointments", []),
        )

    return handler


TOOL_DESCRIPTIONS = TOOL_DESCRIPTIONS_BY_NAME


def build_tools(
    *,
    enabled_tools: list[str],
    settings: Settings,
    user_id: int | str,
    company_id: int,
    message: SimpleMessage | None = None,
    order_id: int | None = None,
) -> list[ToolSpec]:
    """Build tool specs from enabled_tools list in the envelope.

    Maps tool names to local handler implementations.
    """
    enabled_names = set(enabled_tools)
    # Legacy alias: companies may still have "request_handoff" in DB
    if "request_handoff" in enabled_names:
        enabled_names.discard("request_handoff")
        enabled_names.add(AvailableTool.HANDOFF.value)
    tools: list[ToolSpec] = []

    if AvailableTool.UPDATE_FIELDS.value in enabled_names:
        tools.append(
            ToolSpec(
                name="update_fields",
                description=TOOL_DESCRIPTIONS["update_fields"],
                parameters=TOOL_SCHEMAS["update_fields"],
                handler=_create_update_fields_handler(user_id, company_id, order_id),
            )
        )

    if AvailableTool.SEARCH_KB.value in enabled_names:
        tools.append(
            ToolSpec(
                name="search_kb",
                description=TOOL_DESCRIPTIONS["search_kb"],
                parameters=TOOL_SCHEMAS["search_kb"],
                handler=_create_search_kb_handler(user_id, company_id),
            )
        )

    if AvailableTool.GEO_METRICS.value in enabled_names:
        tools.append(
            ToolSpec(
                name="geo_metrics",
                description=TOOL_DESCRIPTIONS["geo_metrics"],
                parameters=TOOL_SCHEMAS["geo_metrics"],
                handler=_create_geo_metrics_handler(),
            )
        )

    if AvailableTool.HANDOFF.value in enabled_names:
        tools.append(
            ToolSpec(
                name="handoff",
                description=TOOL_DESCRIPTIONS["handoff"],
                parameters=TOOL_SCHEMAS["handoff"],
                handler=_create_handoff_handler(settings, user_id, message, order_id),
            )
        )

    if AvailableTool.SEARCH_PRODUCT.value in enabled_names:
        tools.append(
            ToolSpec(
                name="search_product",
                description=TOOL_DESCRIPTIONS["search_product"],
                parameters=TOOL_SCHEMAS["search_product"],
                handler=_create_search_product_handler(),
            )
        )

    if AvailableTool.UPDATE_ORDER_STAGE.value in enabled_names and order_id:
        tools.append(
            ToolSpec(
                name="update_order_stage",
                description=TOOL_DESCRIPTIONS["update_order_stage"],
                parameters=TOOL_SCHEMAS["update_order_stage"],
                handler=_create_update_order_stage_handler(order_id),
            )
        )

    if AvailableTool.CLOSE_ORDER.value in enabled_names and order_id:
        tools.append(
            ToolSpec(
                name="close_order",
                description=TOOL_DESCRIPTIONS["close_order"],
                parameters=TOOL_SCHEMAS["close_order"],
                handler=_create_close_order_handler(order_id),
            )
        )

    if AvailableTool.SCHEDULE_REMINDER.value in enabled_names and order_id:
        tools.append(
            ToolSpec(
                name="schedule_reminder",
                description=TOOL_DESCRIPTIONS["schedule_reminder"],
                parameters=TOOL_SCHEMAS["schedule_reminder"],
                handler=_create_schedule_reminder_handler(company_id, order_id),
            )
        )

    if AvailableTool.GET_BOOKING_SERVICES.value in enabled_names:
        tools.append(
            ToolSpec(
                name="get_booking_services",
                description=TOOL_DESCRIPTIONS["get_booking_services"],
                parameters=TOOL_SCHEMAS["get_booking_services"],
                handler=_create_get_booking_services_handler(company_id),
            )
        )

    if AvailableTool.LIST_STAFF.value in enabled_names:
        tools.append(
            ToolSpec(
                name="list_staff",
                description=TOOL_DESCRIPTIONS["list_staff"],
                parameters=TOOL_SCHEMAS["list_staff"],
                handler=_create_list_staff_handler(company_id),
            )
        )

    if AvailableTool.GET_AVAILABLE_DATES.value in enabled_names:
        tools.append(
            ToolSpec(
                name="get_available_dates",
                description=TOOL_DESCRIPTIONS["get_available_dates"],
                parameters=TOOL_SCHEMAS["get_available_dates"],
                handler=_create_get_available_dates_handler(company_id),
            )
        )

    if AvailableTool.GET_AVAILABLE_SLOTS.value in enabled_names:
        tools.append(
            ToolSpec(
                name="get_available_slots",
                description=TOOL_DESCRIPTIONS["get_available_slots"],
                parameters=TOOL_SCHEMAS["get_available_slots"],
                handler=_create_get_available_slots_handler(company_id),
            )
        )

    if AvailableTool.CREATE_BOOKING.value in enabled_names:
        tools.append(
            ToolSpec(
                name="create_booking",
                description=TOOL_DESCRIPTIONS["create_booking"],
                parameters=TOOL_SCHEMAS["create_booking"],
                handler=_create_create_booking_handler(company_id),
            )
        )

    return tools
