"""Canonical tool catalog — single source of truth for backend and sales-agent."""

from __future__ import annotations

from enum import StrEnum


class ToolGroup(StrEnum):
    ORDER_MANAGEMENT = "order_management"
    KNOWLEDGE = "knowledge"
    CUSTOMER = "customer"
    COMMUNICATION = "communication"
    SCHEDULING = "scheduling"


class AvailableTool(StrEnum):
    UPDATE_FIELDS = "update_fields"
    SEARCH_KB = "search_kb"
    GEO_METRICS = "geo_metrics"
    HANDOFF = "handoff"
    SCHEDULE_REMINDER = "schedule_reminder"
    SEARCH_PRODUCT = "search_product"
    UPDATE_ORDER_STAGE = "update_order_stage"
    CLOSE_ORDER = "close_order"
    GET_BOOKING_SERVICES = "get_booking_services"
    LIST_STAFF = "list_staff"
    GET_AVAILABLE_DATES = "get_available_dates"
    GET_AVAILABLE_SLOTS = "get_available_slots"
    CREATE_BOOKING = "create_booking"


TOOL_CATALOG: dict[ToolGroup, list[AvailableTool]] = {
    ToolGroup.ORDER_MANAGEMENT: [
        AvailableTool.UPDATE_ORDER_STAGE,
        AvailableTool.UPDATE_FIELDS,
        AvailableTool.CLOSE_ORDER,
    ],
    ToolGroup.KNOWLEDGE: [
        AvailableTool.SEARCH_KB,
        AvailableTool.SEARCH_PRODUCT,
        AvailableTool.GEO_METRICS,
    ],
    ToolGroup.COMMUNICATION: [
        AvailableTool.HANDOFF,
        AvailableTool.SCHEDULE_REMINDER,
    ],
    ToolGroup.SCHEDULING: [
        AvailableTool.GET_BOOKING_SERVICES,
        AvailableTool.LIST_STAFF,
        AvailableTool.GET_AVAILABLE_DATES,
        AvailableTool.GET_AVAILABLE_SLOTS,
        AvailableTool.CREATE_BOOKING,
    ],
}

TOOL_DESCRIPTIONS: dict[AvailableTool, str] = {
    AvailableTool.UPDATE_FIELDS: (
        "Обновляет поля клиента и заказа. Используй ключи из списка полей компании. "
        "Если информация не вписывается ни в одно из существующих полей, но критически важна "
        "для менеджера при продаже, можешь добавить произвольный ключ. Это допустимо ТОЛЬКО для "
        "стабильных фактов: бюджет, конкретные требования, ограничения клиента, ключевое возражение. "
        "НЕ записывай: эмоции, настроение, временные состояния, даты контактов, внутренние пометки."
    ),
    AvailableTool.SEARCH_KB: "Ищет в базе знаний и FAQ ответы на вопросы пользователя.",
    AvailableTool.GEO_METRICS: ("Получает гео-метрики для адреса: минуты до метро, километры от КАД."),
    AvailableTool.HANDOFF: "Передаёт разговор живому оператору.",
    AvailableTool.SCHEDULE_REMINDER: "Планирует напоминание для follow-up с клиентом.",
    AvailableTool.SEARCH_PRODUCT: (
        "Ищет продукты по ключевым словам. Всегда передавай в query максимум релевантных слов из разговора: "
        "название продукта, предпочтения клиента, характеристики, бюджет, локацию и т.д. "
        "Минимум 3 слова. Чем больше ключевых слов — тем точнее результат."
    ),
    AvailableTool.UPDATE_ORDER_STAGE: "Обновляет стадию заказа.",
    AvailableTool.CLOSE_ORDER: "Закрывает заказ с результатом (won/lost).",
    AvailableTool.GET_BOOKING_SERVICES: (
        "Возвращает услуги, доступные для записи (id, название, категория, цена, длительность). "
        "Если указан staff_id — вернёт только услуги этого мастера с точными длительностями."
    ),
    AvailableTool.LIST_STAFF: (
        "Возвращает список мастеров/сотрудников. "
        "Можно отфильтровать по услугам — вернутся только мастера, оказывающие указанные услуги."
    ),
    AvailableTool.GET_AVAILABLE_DATES: (
        "Возвращает ближайшие даты, где есть свободные слоты у мастера. "
        "Используй этот инструмент перед запросом времени, чтобы не просить у клиента дату вслепую."
    ),
    AvailableTool.GET_AVAILABLE_SLOTS: (
        "Возвращает свободные слоты для записи на конкретную дату к конкретному мастеру. "
        "ОБЯЗАТЕЛЬНО передавай service_ids — без них слоты не учитывают длительность процедуры."
    ),
    AvailableTool.CREATE_BOOKING: (
        "Создаёт запись клиента. Нужны: телефон, имя, мастер, услуга, время (из get_available_slots). "
        "После создания возвращает номер записи."
    ),
}

assert set(TOOL_DESCRIPTIONS) == set(AvailableTool), (
    f"TOOL_DESCRIPTIONS must cover every AvailableTool; missing {set(AvailableTool) - set(TOOL_DESCRIPTIONS)}"
)

TOOL_DESCRIPTIONS_BY_NAME: dict[str, str] = {tool.value: desc for tool, desc in TOOL_DESCRIPTIONS.items()}

_cataloged = {t for tools in TOOL_CATALOG.values() for t in tools}
_missing = set(AvailableTool) - _cataloged
assert not _missing, f"Tools missing from TOOL_CATALOG: {_missing}"

CAPABILITY_GATED_GROUPS: dict[ToolGroup, str] = {
    ToolGroup.SCHEDULING: "scheduling",
}

LEGACY_TOOLS: set[AvailableTool] = {
    AvailableTool.UPDATE_ORDER_STAGE,
}
