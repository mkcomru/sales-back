"""Ping evaluator — core logic for determining which pings to schedule.

Called by PingEvaluatorWorker on each tick. Separated from the worker
to keep business logic testable without async loop scaffolding.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from common.models import TaskAutoAction

from src.backend.core.conditions import evaluate_condition
from src.backend.modules.billing.models import BillingStatus
from src.backend.modules.chat.models import AssistantMode, Thread, ThreadState
from src.backend.modules.orders.models import Order
from src.backend.modules.pings.models import PingRule
from src.backend.modules.tasks.models import TaskType
from src.backend.modules.tasks.repository import TaskRepository

log = structlog.get_logger(__name__)

BATCH_SIZE = 100


async def evaluate_pings(task_repo: TaskRepository) -> int:
    """Evaluate all active threads and schedule due pings.

    Returns the number of ping tasks created.
    """
    now = datetime.now(UTC)
    created = 0
    offset = 0

    open_order_ids = list(
        await Order.filter(
            closed_at__isnull=True,
            frozen=False,
            charged_at__isnull=False,
            billing_status=BillingStatus.ACTIVE,
        ).values_list("id", flat=True)
    )
    if not open_order_ids:
        return 0

    while True:
        threads = (
            await Thread.filter(
                active_order_id__in=open_order_ids,
                last_customer_message_at__isnull=False,
                assistant_mode=AssistantMode.ACTIVE,
            )
            .exclude(state__in=[ThreadState.CLOSED, ThreadState.HANDOFF])
            .select_related("active_order")
            .offset(offset)
            .limit(BATCH_SIZE)
        )

        if not threads:
            break

        for thread in threads:
            order = thread.active_order
            if not order or not order.stage_id:
                continue

            if await task_repo.has_pending_agent_followup(order.id):
                continue

            rules = await PingRule.filter(
                stage_id=order.stage_id,
                is_active=True,
            ).order_by("position")

            if not rules:
                continue

            last_msg_at = thread.last_customer_message_at
            silence_seconds = (now - last_msg_at).total_seconds()

            for rule in rules:
                if silence_seconds < rule.delay_seconds:
                    continue

                if await task_repo.has_ping_since(order.id, rule.id, since=last_msg_at):
                    continue

                if rule.condition:
                    ctx = _build_condition_context(order, thread)
                    if not evaluate_condition(rule.condition, ctx):
                        continue

                await task_repo.create_order_task(
                    company_id=order.company_id,
                    order_id=order.id,
                    title=f"Auto-ping #{rule.position}",
                    due_date=now,
                    type=TaskType.AI_SCHEDULED,
                    auto_action=TaskAutoAction.SEND_FOLLOWUP_MESSAGE,
                    ping_rule_id=rule.id,
                )
                created += 1

                log.info(
                    "ping.scheduled",
                    order_id=order.id,
                    rule_id=rule.id,
                    position=rule.position,
                    silence_seconds=int(silence_seconds),
                )

        offset += BATCH_SIZE

    return created


def _build_condition_context(order: Order, thread: Thread) -> dict[str, Any]:
    """Build context dict for condition evaluation."""
    return {
        "order_fields": order.order_fields or {},
        "customer_fields": {},
        "last_customer_message_at": thread.last_customer_message_at,
    }
