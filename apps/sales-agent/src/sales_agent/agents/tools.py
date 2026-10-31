from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from common import SalesAgentSettings as Settings
from common.models.io import SimpleMessage

from src.sales_agent.core.notify import notify_handoff
from src.sales_agent.faq import get_faq_service
from src.sales_agent.rag.retriever import Retriever
from src.sales_agent.services.company_context import get_company_spec, get_customer_answers, set_handoff_result
from src.sales_agent.services.geocoding import (
    distance_from_spb_kad_km,
    geocode_address,
    get_nearest_metro_distance,
)
from src.sales_agent.services.humanizer import humanize_message
from src.sales_agent.storage.customer_store import get_backend_client, update_customer_fields

logger = logging.getLogger(__name__)


class FaqInstructions(BaseModel):
    manager_flag: bool
    avoid_numbers: bool
    category: str | None


class FaqMatch(BaseModel):
    category: str
    question: str
    keywords: list[str]
    score: float


class KnowledgeBaseResponse(BaseModel):
    source: str
    empty: bool = False
    content: str | None = None
    message: str | None = None
    record_id: str | None = None
    title: str | None = None
    path: str | None = None
    topic: str | None = None
    summary: str | None = None
    instructions: FaqInstructions
    keywords: list[str] = []
    guidance: str
    faq: FaqMatch | None = None


class UpdateFieldsResponse(BaseModel):
    updated_customer: list[str] = []
    updated_order: list[str] = []
    updated_extra: list[str] = []
    rejected: list[dict[str, Any]] = []


class GeoMetricsResponse(BaseModel):
    minutes_to_metro: int
    km_from_kad: float


class HandoffSummary(BaseModel):
    text: str | None = None
    reason: str | None = None


async def search_knowledge_base(user_id: int | str, question: str, company_id: int) -> KnowledgeBaseResponse:
    """RAG-backed retrieval maintaining legacy tool response shape.

    Returns structured dict compatible with callers that expect the legacy schema.
    """
    # AICODE-NOTE: FAQ-first — try static FAQ answers before RAG
    faq = get_faq_service()
    match = await faq.find_best(question)
    settings = Settings()
    threshold = settings.faq.threshold if hasattr(settings, "faq") else 0.82
    if match and match.score >= threshold:
        # Light paraphrasing via existing humanizer using conversation history
        text = await humanize_message(match.answer, user_id, company_id)
        return KnowledgeBaseResponse(
            source="faq",
            empty=False,
            content=text,
            faq=FaqMatch(
                category=match.category,
                question=match.question,
                keywords=match.keywords,
                score=match.score,
            ),
            instructions=FaqInstructions(
                manager_flag=False,
                avoid_numbers=False,
                category=match.category,
            ),
            guidance=("Это ответ из FAQ. Используйте как готовую формулировку, допускается лёгкое перефразирование."),
        )

    # AICODE-NOTE: Check if RAG is enabled before attempting retrieval
    if not settings.rag.enabled:
        return KnowledgeBaseResponse(
            source="knowledge_base",
            empty=True,
            message=(
                "Точного фрагмента по этому вопросу нет в базе знаний. "
                "Не называйте точные цифры; предложите обсудить детали с менеджером."
            ),
            instructions=FaqInstructions(
                manager_flag=False,
                avoid_numbers=False,
                category=None,
            ),
            guidance="",
        )

    retriever = Retriever()
    await retriever.ensure_ready()
    items = await retriever.retrieve(question, top_k=1)
    if not items:
        return KnowledgeBaseResponse(
            source="knowledge_base",
            empty=True,
            message=(
                "Точного фрагмента по этому вопросу нет в базе знаний. "
                "Не называйте точные цифры; предложите обсудить детали с менеджером."
            ),
            instructions=FaqInstructions(
                manager_flag=False,
                avoid_numbers=False,
                category=None,
            ),
            guidance="",
        )

    top = items[0]
    return KnowledgeBaseResponse(
        source="knowledge_base",
        record_id=top.get("record_id"),
        title=top.get("title"),
        path=top.get("path"),
        topic=top.get("topic"),
        summary=top.get("summary"),
        content=top.get("content"),
        instructions=FaqInstructions(
            manager_flag=False,
            avoid_numbers=False,
            category=None,
        ),
        keywords=top.get("keywords") or [],
        guidance=("Используйте `content` как точный факт и приведите ссылку, если есть."),
    )


async def update_fields(
    user_id: int | str,
    company_id: int,
    updates: dict[str, Any],
    order_id: int | None = None,
) -> UpdateFieldsResponse:
    """Update customer/order/extra fields via unified backend endpoint.

    Backend handles routing to customer_fields, order_fields, or extra_fields
    based on the company's field schema. Enum validation also happens on backend.
    """
    existing = get_customer_answers()
    form_pending = bool(existing.get("_form_pending_confirmation"))
    blocked_keys = {"stage", "stage_id", "qualifier_done"} if form_pending else {"stage", "stage_id"}

    filtered = {k: v for k, v in updates.items() if k not in blocked_keys}
    if not filtered:
        return UpdateFieldsResponse()

    backend = get_backend_client()
    result = await backend.update_fields(
        user_id=str(user_id),
        company_id=company_id,
        updates=filtered,
        order_id=order_id,
    )
    return UpdateFieldsResponse(**result)


class RequestHandoffResponse(BaseModel):
    """Response from request_handoff tool."""

    success: bool
    manager_id: int | None = None
    manager_name: str | None = None
    is_working_now: bool = False
    next_available_at: str | None = None
    schedule_description: str | None = None
    message_hint: str | None = None


async def request_handoff(
    settings: Settings,
    order_id: int,
    summary: str = "Передача менеджеру",
    reason: str = "Требуется участие менеджера",
    *,
    escalate: bool = False,
    message: SimpleMessage | None = None,
) -> RequestHandoffResponse:
    """Request handoff to manager with load balancing.

    order_id is always provided from the envelope (injected by backend).
    escalate=True triggers hard handoff (AI stops immediately).
    escalate=False (default) triggers soft handoff (AI continues in shadowing mode).
    """
    backend_client = get_backend_client()

    result = await backend_client.request_handoff(
        order_id=order_id,
        summary=summary,
        reason=reason,
        escalate=escalate,
    )

    set_handoff_result({"text": summary, "reason": reason, "escalate": escalate})

    manager_info = result.get("manager")
    availability_info = result.get("availability", {})

    return RequestHandoffResponse(
        success=result.get("success", False),
        manager_id=manager_info.get("id") if manager_info else None,
        manager_name=manager_info.get("name") if manager_info else None,
        is_working_now=availability_info.get("is_working_now", False),
        next_available_at=availability_info.get("next_available_at_local"),
        schedule_description=availability_info.get("schedule_description"),
        message_hint=result.get("message_hint"),
    )


async def handoff_commit(
    settings: Settings,
    user_id: int | str,
    summary: dict[str, str],
    *,
    reason: str | None = None,
    message: SimpleMessage | None = None,
    escalate: bool = False,
) -> HandoffSummary:
    """Persist summary and trigger handoff via unified request_handoff path.

    Also notifies CRM proxy for external handoff.
    """
    final = dict(summary)
    if reason and not final.get("reason"):
        final["reason"] = reason

    company_id = None
    order_id = None
    if message and isinstance(message.metadata, dict):
        company_id = message.metadata.get("company_id")
        order_id = message.metadata.get("order_id")

    if company_id is None:
        raise ValueError("company_id is required")

    await update_customer_fields(user_id, company_id, {"handoff_summary": final})

    set_handoff_result(final)

    if order_id:
        backend_client = get_backend_client()
        try:
            await backend_client.request_handoff(
                order_id=int(order_id),
                summary=final.get("text", ""),
                reason=final.get("reason", ""),
                escalate=escalate,
            )
        except Exception as exc:
            import structlog

            log = structlog.get_logger(__name__)
            log.error(
                "handoff.backend_notification_failed",
                user_id=user_id,
                company_id=company_id,
                order_id=order_id,
                error=str(exc),
            )

    if message is not None:
        await notify_handoff(settings, message, final, stage=None)

    return HandoffSummary(
        text=final.get("text"),
        reason=final.get("reason"),
    )


async def geo_metrics(address: str) -> GeoMetricsResponse:
    """Return basic geo metrics for decision making.

    - minutes_to_metro: walking minutes to nearest metro (or -1)
    - km_from_kad: kilometers outside Saint Petersburg KAD (or -1 if N/A)
    """
    settings = Settings()
    api_key = settings.yandex.token
    if not api_key:
        return GeoMetricsResponse(minutes_to_metro=-1, km_from_kad=-1.0)

    minutes_to_metro = -1
    km_from_kad = -1.0

    # Metro distance (both cities)
    metro = get_nearest_metro_distance(address, api_key)
    if metro is not None:
        _station_name, distance_meters = metro
        minutes_to_metro = max(0, round(distance_meters / 80))

    # KAD distance (only for SPB use-cases).
    # We don't detect city here; agent applies rules.
    try:
        lat, lon = geocode_address(address, api_key)
        km_from_kad = float(distance_from_spb_kad_km(lat, lon))
    except Exception:
        km_from_kad = -1.0

    return GeoMetricsResponse(minutes_to_metro=minutes_to_metro, km_from_kad=km_from_kad)


TOP_K = 3
MIN_QUERY_TOKENS = 2


def _serialize_attr_value(value: Any) -> str:
    """Serialize an attribute value for fuzzy matching."""
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value)


def _score_product(query: str, product: dict[str, Any], customer_answers: dict[str, Any]) -> float:
    """Score a single product against query using token_set_ratio.

    Combined score (0–300 range):
      - name:        token_set_ratio(query, name)       → 0–100
      - description: token_set_ratio(query, description) → 0–100
      - attributes:  max(token_set_ratio(query, attr))   → 0–100
    Plus soft bonus when customer answers overlap with product attribute values.
    """
    name = product.get("name") or ""
    description = product.get("description") or ""
    attrs: dict[str, Any] = product.get("attributes") or {}

    name_score = fuzz.token_set_ratio(query, name)
    desc_score = fuzz.token_set_ratio(query, description)

    attr_scores = [fuzz.token_set_ratio(query, _serialize_attr_value(v)) for v in attrs.values() if v is not None]
    attr_score = max(attr_scores) if attr_scores else 0.0

    total = name_score + desc_score + attr_score

    # AICODE-NOTE: Soft bonus for customer answer overlap with product attributes.
    # Matching attribute values boost ranking but never eliminate products.
    for key, customer_value in customer_answers.items():
        if customer_value is None or key not in attrs:
            continue
        product_value = attrs[key]
        overlap = fuzz.token_set_ratio(str(customer_value), _serialize_attr_value(product_value))
        total += overlap * 0.3

    return total


class ProductSearchResult(BaseModel):
    """Single product in search results."""

    id: int
    name: str
    description: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    fields: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Product-level fields to collect after selection",
    )
    match_score: float = Field(default=0.0, description="Relevance score (higher = better match)")


class SearchProductOutput(BaseModel):
    """Output of search_product tool."""

    products: list[ProductSearchResult]
    message: str


async def search_product(query: str) -> SearchProductOutput:
    """Score-based product search using rapidfuzz token_set_ratio.

    Scores ALL products, returns top 3 — never empty if catalog has products.
    """
    tokens = query.strip().split()
    if len(tokens) < MIN_QUERY_TOKENS:
        return SearchProductOutput(
            products=[],
            message=f"Запрос слишком короткий — нужно минимум {MIN_QUERY_TOKENS} слова для поиска.",
        )

    spec = get_company_spec()
    products: list[dict[str, Any]] = spec.get("products") or []
    all_fields: list[dict[str, Any]] = spec.get("fields") or []

    if not products:
        return SearchProductOutput(products=[], message="Пока нет доступных продуктов.")

    try:
        customer_answers = get_customer_answers()
    except RuntimeError:
        customer_answers = {}

    scored: list[tuple[dict[str, Any], float]] = []
    for product in products:
        score = _score_product(query, product, customer_answers)
        scored.append((product, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:TOP_K]

    results: list[ProductSearchResult] = []
    for product, score in top:
        product_id = product.get("id")
        if product_id is None:
            continue
        product_fields = [f for f in all_fields if f.get("product_id") == product_id]
        results.append(
            ProductSearchResult(
                id=product_id,
                name=product.get("name", ""),
                description=product.get("description", ""),
                attributes=product.get("attributes") or {},
                fields=product_fields,
                match_score=round(score, 2),
            )
        )

    return SearchProductOutput(
        products=results,
        message=f"Найдено {len(results)} лучших вариантов по запросу.",
    )


class UpdateOrderStageResponse(BaseModel):
    """Response from update_order_stage tool."""

    order_id: int
    current_stage: str
    success: bool = True


class CloseOrderResponse(BaseModel):
    """Response from close_order tool."""

    order_id: int
    result: str
    closed: bool = True
    message: str


async def update_order_stage(
    order_id: int,
    stage: str,
) -> UpdateOrderStageResponse:
    """Update current order stage.

    Args:
        order_id: Order identifier (from context)
        stage: New stage value (e.g., new, qualification, offer, negotiation, closed)

    Returns:
        UpdateOrderStageResponse with order_id and current stage
    """
    backend = get_backend_client()
    result = await backend.update_order_stage(order_id=order_id, stage=stage)

    return UpdateOrderStageResponse(
        order_id=result["id"],
        current_stage=result["stage"],
        success=True,
    )


async def close_order(
    order_id: int,
    result: str,
    reason: str | None = None,
) -> CloseOrderResponse:
    """Close order and mark it as won or lost.

    AICODE-NOTE: This tool moves the order to the final stage and sets the result.
    Use this when:
    - Customer explicitly refuses/cancels → result="lost"
    - Deal is successfully completed → result="won"
    - Customer stops responding after qualification → result="lost"

    This is the ONLY way to reach the final stage - auto-transitions cannot do it.

    Args:
        order_id: Order identifier (from context)
        result: Order result - "won" or "lost"
        reason: Optional reason for closing (e.g., "customer refused", "deal completed")

    Returns:
        CloseOrderResponse with order_id, result, and confirmation
    """
    if result not in ("won", "lost"):
        raise ValueError(f"Invalid result: {result}. Must be 'won' or 'lost'")

    backend = get_backend_client()
    response = await backend.close_order(order_id=order_id, result=result)

    message = f"Order closed as {result}"
    if reason:
        message += f": {reason}"

    return CloseOrderResponse(
        order_id=response["id"],
        result=result,
        closed=True,
        message=message,
    )
