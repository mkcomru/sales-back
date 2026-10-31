"""Task executor — dispatches AI tasks to Sales Agent, delivers static pings directly.

AI tasks use fire-and-forget dispatch: the executor builds context, sends
the request to the sales agent (which returns 202 immediately), and marks
the task completed.  The agent handles LLM generation and outbound delivery
asynchronously — matching the inbound message pattern.

Static pings bypass the agent entirely: the executor stores the message
and delivers to transport itself.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog

from common.correlation import make_correlation_id
from common.models import (
    ConnectorContext,
    DebounceConfig,
    PingContext,
    TaskAutoAction,
    TaskExecutionRequest,
)

from src.backend.modules.billing.models import BillingStatus
from src.backend.modules.chat.models import AssistantMode, ChatMessageRole, ChatMessageStatus, Thread, ThreadState
from src.backend.modules.chat.service import ChatService
from src.backend.modules.messages.context_assembly import AgentContextAssembler
from src.backend.modules.messages.outbound_service import OutboundService
from src.backend.modules.messages.sales_agent_client import SalesAgentClient
from src.backend.modules.orders.models import Order
from src.backend.modules.orders.service import OrderService
from src.backend.modules.pings.enums import PingContentType
from src.backend.modules.pings.models import PingRule
from src.backend.modules.tasks.models import CompletedByType, Task, TaskSubjectType
from src.backend.modules.tasks.repository import TaskRepository
from src.backend.modules.transport.models import Connector

log = structlog.get_logger(__name__)


class TaskExecutor:
    """Dispatches AI-scheduled tasks to Sales Agent and delivers static pings."""

    def __init__(
        self,
        task_repo: TaskRepository,
        sales_agent_client: SalesAgentClient,
        order_service: OrderService,
        context_assembler: AgentContextAssembler,
        chat_service: ChatService,
        outbound_service: OutboundService,
    ):
        self.task_repo = task_repo
        self.sales_agent_client = sales_agent_client
        self.order_service = order_service
        self.context_assembler = context_assembler
        self.chat_service = chat_service
        self.outbound_service = outbound_service

    async def execute_ai_task(self, task: Task) -> None:
        """Validate guards then dispatch or deliver the task."""
        log.info(
            "task.executing",
            task_id=task.id,
            auto_action=task.auto_action,
        )

        try:
            if task.subject_type != TaskSubjectType.ORDER:
                raise ValueError(f"Unsupported subject type: {task.subject_type}")

            order = await self.order_service.get_order(task.company_id, task.get_order_id())
            if not order:
                raise ValueError(f"Order {task.get_order_id()} not found")

            if order.charged_at is None or order.billing_status != BillingStatus.ACTIVE:
                await self.task_repo.cancel_task(task.id)
                log.info(
                    "task.billing_guard.cancelled",
                    task_id=task.id,
                    order_id=order.id,
                    billing_status=order.billing_status,
                    charged=order.charged_at is not None,
                )
                return

            thread = await Thread.filter(active_order_id=order.id).first()
            if not thread:
                raise ValueError(f"Thread not found for order {order.id}")

            if task.ping_rule_id:
                should_cancel = (
                    (thread.last_customer_message_at and thread.last_customer_message_at > task.created_at)
                    or thread.assistant_mode == AssistantMode.INACTIVE
                    or thread.state in (ThreadState.HANDOFF, ThreadState.CLOSED)
                )
                if should_cancel:
                    await self.task_repo.cancel_task(task.id)
                    log.info("ping.guard.cancelled", task_id=task.id, reason="stale_or_frozen")
                    return

            connector = await Connector.filter(connector_id=thread.connector_id).first()
            if not connector:
                raise ValueError(f"Connector {thread.connector_id} not found")

            ping_rule = None
            if task.ping_rule_id:
                ping_rule = await PingRule.get_or_none(id=task.ping_rule_id)
                if not ping_rule:
                    raise ValueError(f"PingRule {task.ping_rule_id} not found")

            if ping_rule and ping_rule.content_type == PingContentType.STATIC:
                await self._send_static_ping(task, ping_rule, thread, connector)
            else:
                await self._dispatch_to_agent(task, thread, connector, order, ping_rule)

            await self.task_repo.complete_task(task.id, completed_by_type=CompletedByType.SYSTEM)
            log.info("task.dispatched", task_id=task.id, is_ping=bool(ping_rule))

        except Exception:
            log.exception("task.dispatch.failed", task_id=task.id)
            await self.task_repo.cancel_task(task.id)

    async def _dispatch_to_agent(
        self,
        task: Task,
        thread: Thread,
        connector: Connector,
        order: Order,
        ping_rule: PingRule | None,
    ) -> None:
        """Build context and dispatch to sales-agent (fire-and-forget).

        The agent returns 202 immediately; LLM + outbound happen async.
        """
        await thread.fetch_related("customer")
        agent_ctx = await self.context_assembler.build(
            company_id=task.company_id,
            user_id=thread.customer.user_id,
            thread_id=thread.thread_id,
            conversation_id=thread.conversation_id,
            order_id=order.id,
        )

        ping_context = None
        title = task.title
        description = task.description

        if ping_rule:
            ping_context = PingContext(
                ping_rule_id=ping_rule.id,
                content_type=ping_rule.content_type,
                prompt_override=ping_rule.prompt_override,
            )
            if ping_rule.prompt_override:
                description = ping_rule.prompt_override

        payload = TaskExecutionRequest(
            context=ConnectorContext(
                connector_id=thread.connector_id,
                company_id=task.company_id,
                type=connector.type.value,
                channel_type=thread.channel_type,
                debounce=DebounceConfig(),
            ),
            thread_id=thread.thread_id,
            order_id=order.id,
            agent_context=agent_ctx,
            task_id=task.id,
            auto_action=TaskAutoAction(task.auto_action),
            title=title,
            description=description,
            ping_context=ping_context,
        )

        await self.sales_agent_client.execute_task(payload)

    async def _send_static_ping(
        self,
        task: Task,
        ping_rule: PingRule,
        thread: Thread,
        connector: Connector,
    ) -> None:
        """Send static ping content directly via transport, bypassing sales-agent."""
        if not ping_rule.static_content:
            raise ValueError(f"PingRule {ping_rule.id} is STATIC but has no static_content")

        await self.chat_service.create_message(
            thread_id=thread.thread_id,
            role=ChatMessageRole.ASSISTANT,
            content=ping_rule.static_content,
            status=ChatMessageStatus.SENT,
            delivered_at=datetime.now(UTC),
            metadata={"ping_rule_id": ping_rule.id, "auto_ping": True},
        )

        await self.outbound_service.deliver_to_thread(
            connector=connector,
            thread=thread,
            replies=[ping_rule.static_content],
            correlation_id=make_correlation_id("ping", str(task.id)),
            metadata={"ping_rule_id": ping_rule.id, "thread_id": thread.thread_id},
        )
