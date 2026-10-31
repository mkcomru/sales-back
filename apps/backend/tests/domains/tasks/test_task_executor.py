"""Tests for TaskExecutor."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from common.models import TaskAutoAction

from src.backend.modules.chat.models import AssistantMode, Thread
from src.backend.modules.chat.service import ChatService
from src.backend.modules.messages.context_assembly import AgentContextAssembler
from src.backend.modules.messages.outbound_service import OutboundService
from src.backend.modules.messages.sales_agent_client import SalesAgentClient
from src.backend.modules.orders.models import Order
from src.backend.modules.orders.service import OrderService
from src.backend.modules.pings.enums import PingContentType
from src.backend.modules.pings.models import PingRule
from src.backend.modules.stages.models import StageTemplate
from src.backend.modules.tasks.models import CompletedByType, TaskType
from src.backend.modules.tasks.repository import TaskRepository
from src.backend.modules.transport.models import Connector, ConnectorType
from src.backend.workers.task_executor import TaskExecutor


async def _ensure_order_charged_for_task_dispatch(order: Order) -> None:
    order.charged_at = datetime.now(UTC)
    await order.save()


def _chat_and_outbound_mocks() -> tuple[MagicMock, MagicMock]:
    chat_service = MagicMock(spec=ChatService)
    chat_service.create_message = AsyncMock()
    outbound_service = MagicMock(spec=OutboundService)
    outbound_service.deliver_to_thread = AsyncMock()
    return chat_service, outbound_service


@pytest.mark.asyncio
async def test_execute_ai_task_success(
    order_with_customer: tuple,
    task_repository: TaskRepository,
):
    """Test successful AI task execution."""
    order, _, company = order_with_customer
    await _ensure_order_charged_for_task_dispatch(order)

    connector = await Connector.create(
        connector_id="test-connector-123",
        company_id=company.id,
        type=ConnectorType.TELEGRAM,
        channel_type="telegram",
        display_name="Test Connector",
        config={},
    )

    thread = await Thread.create(
        thread_id="test-thread-123",
        connector_id=connector.connector_id,
        company_id=company.id,
        customer_id=order.customer_id,
        channel_type="telegram",
        active_order_id=order.id,
    )

    task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="AI Follow-up",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.AI_SCHEDULED,
        auto_action=TaskAutoAction.SEND_FOLLOWUP_MESSAGE.value,
    )

    sales_agent_client = MagicMock(spec=SalesAgentClient)
    sales_agent_client.execute_task = AsyncMock()

    context_assembler = MagicMock(spec=AgentContextAssembler)
    context_assembler.build = AsyncMock(
        return_value={"prompt_template": "", "company": {}, "customer_answers": {}, "history": [], "enabled_tools": []}
    )

    chat_service, outbound_service = _chat_and_outbound_mocks()

    executor = TaskExecutor(
        task_repo=task_repository,
        sales_agent_client=sales_agent_client,
        order_service=OrderService(),
        context_assembler=context_assembler,
        chat_service=chat_service,
        outbound_service=outbound_service,
    )

    await executor.execute_ai_task(task)

    sales_agent_client.execute_task.assert_called_once()
    call_args = sales_agent_client.execute_task.call_args[0][0]
    assert call_args.task_id == task.id
    assert call_args.auto_action == TaskAutoAction.SEND_FOLLOWUP_MESSAGE
    assert call_args.thread_id == thread.thread_id
    assert call_args.order_id == order.id

    completed_task = await task_repository.get_by_id(task.id)
    assert completed_task.completed is True
    assert completed_task.completed_by_type == CompletedByType.SYSTEM
    assert completed_task.attempt_count == 0
    assert completed_task.last_attempt_at is None


@pytest.mark.asyncio
async def test_execute_ai_task_records_attempt(
    order_with_customer: tuple,
    task_repository: TaskRepository,
):
    """Dispatch path does not use record_attempt; attempt metadata stays at defaults."""
    order, _, company = order_with_customer
    await _ensure_order_charged_for_task_dispatch(order)

    connector = await Connector.create(
        connector_id="test-connector-123",
        company_id=company.id,
        type=ConnectorType.TELEGRAM,
        channel_type="telegram",
        display_name="Test Connector",
        config={},
    )

    _thread = await Thread.create(
        thread_id="test-thread-123",
        connector_id=connector.connector_id,
        company_id=company.id,
        customer_id=order.customer_id,
        channel_type="telegram",
        active_order_id=order.id,
    )

    task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="AI Follow-up",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.AI_SCHEDULED,
        auto_action=TaskAutoAction.SEND_FOLLOWUP_MESSAGE.value,
    )

    initial_attempt_count = task.attempt_count

    sales_agent_client = MagicMock(spec=SalesAgentClient)
    sales_agent_client.execute_task = AsyncMock()

    context_assembler = MagicMock(spec=AgentContextAssembler)
    context_assembler.build = AsyncMock(
        return_value={"prompt_template": "", "company": {}, "customer_answers": {}, "history": [], "enabled_tools": []}
    )

    chat_service, outbound_service = _chat_and_outbound_mocks()

    executor = TaskExecutor(
        task_repo=task_repository,
        sales_agent_client=sales_agent_client,
        order_service=OrderService(),
        context_assembler=context_assembler,
        chat_service=chat_service,
        outbound_service=outbound_service,
    )

    await executor.execute_ai_task(task)

    updated_task = await task_repository.get_by_id(task.id)
    assert updated_task.attempt_count == initial_attempt_count
    assert updated_task.last_attempt_at is None
    assert updated_task.completed is True


@pytest.mark.asyncio
async def test_execute_ai_task_handles_order_not_found(
    order_with_customer: tuple,
    task_repository: TaskRepository,
):
    """Test that executor handles order not found error."""
    order, _, company = order_with_customer

    task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=99999,
        title="AI Follow-up",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.AI_SCHEDULED,
        auto_action=TaskAutoAction.SEND_FOLLOWUP_MESSAGE.value,
    )

    sales_agent_client = MagicMock(spec=SalesAgentClient)
    sales_agent_client.execute_task = AsyncMock()

    context_assembler = MagicMock(spec=AgentContextAssembler)
    context_assembler.build = AsyncMock(
        return_value={"prompt_template": "", "company": {}, "customer_answers": {}, "history": [], "enabled_tools": []}
    )

    chat_service, outbound_service = _chat_and_outbound_mocks()

    executor = TaskExecutor(
        task_repo=task_repository,
        sales_agent_client=sales_agent_client,
        order_service=OrderService(),
        context_assembler=context_assembler,
        chat_service=chat_service,
        outbound_service=outbound_service,
    )

    await executor.execute_ai_task(task)

    sales_agent_client.execute_task.assert_not_called()

    failed_task = await task_repository.get_by_id(task.id)
    assert failed_task.completed is False
    assert failed_task.cancelled_at is not None
    assert failed_task.failure_reason is None


@pytest.mark.asyncio
async def test_execute_ai_task_handles_thread_not_found(
    order_with_customer: tuple,
    task_repository: TaskRepository,
):
    """Test that executor handles thread not found error."""
    order, _, company = order_with_customer
    await _ensure_order_charged_for_task_dispatch(order)

    task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="AI Follow-up",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.AI_SCHEDULED,
        auto_action=TaskAutoAction.SEND_FOLLOWUP_MESSAGE.value,
    )

    sales_agent_client = MagicMock(spec=SalesAgentClient)
    sales_agent_client.execute_task = AsyncMock()

    context_assembler = MagicMock(spec=AgentContextAssembler)
    context_assembler.build = AsyncMock(
        return_value={"prompt_template": "", "company": {}, "customer_answers": {}, "history": [], "enabled_tools": []}
    )

    chat_service, outbound_service = _chat_and_outbound_mocks()

    executor = TaskExecutor(
        task_repo=task_repository,
        sales_agent_client=sales_agent_client,
        order_service=OrderService(),
        context_assembler=context_assembler,
        chat_service=chat_service,
        outbound_service=outbound_service,
    )

    await executor.execute_ai_task(task)

    sales_agent_client.execute_task.assert_not_called()

    failed_task = await task_repository.get_by_id(task.id)
    assert failed_task.completed is False
    assert failed_task.cancelled_at is not None
    assert failed_task.failure_reason is None


@pytest.mark.asyncio
async def test_execute_ai_task_handles_execution_failure(
    order_with_customer: tuple,
    task_repository: TaskRepository,
):
    """Test that executor handles execution failure."""
    order, _, company = order_with_customer
    await _ensure_order_charged_for_task_dispatch(order)

    connector = await Connector.create(
        connector_id="test-connector-123",
        company_id=company.id,
        type=ConnectorType.TELEGRAM,
        channel_type="telegram",
        display_name="Test Connector",
        config={},
    )

    _thread = await Thread.create(
        thread_id="test-thread-123",
        connector_id=connector.connector_id,
        company_id=company.id,
        customer_id=order.customer_id,
        channel_type="telegram",
        active_order_id=order.id,
    )

    task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="AI Follow-up",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.AI_SCHEDULED,
        auto_action=TaskAutoAction.SEND_FOLLOWUP_MESSAGE.value,
    )

    sales_agent_client = MagicMock(spec=SalesAgentClient)
    sales_agent_client.execute_task = AsyncMock(side_effect=Exception("Network error"))

    context_assembler = MagicMock(spec=AgentContextAssembler)
    context_assembler.build = AsyncMock(
        return_value={"prompt_template": "", "company": {}, "customer_answers": {}, "history": [], "enabled_tools": []}
    )

    chat_service, outbound_service = _chat_and_outbound_mocks()

    executor = TaskExecutor(
        task_repo=task_repository,
        sales_agent_client=sales_agent_client,
        order_service=OrderService(),
        context_assembler=context_assembler,
        chat_service=chat_service,
        outbound_service=outbound_service,
    )

    await executor.execute_ai_task(task)

    failed_task = await task_repository.get_by_id(task.id)
    assert failed_task.completed is False
    assert failed_task.cancelled_at is not None
    assert failed_task.failure_reason is None
    assert failed_task.attempt_count == 0


@pytest.mark.asyncio
async def test_execute_ai_task_handles_invalid_order_id(
    order_with_customer: tuple,
    task_repository: TaskRepository,
):
    """Test that executor handles invalid order_id."""
    order, _, company = order_with_customer

    task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=99999,
        title="AI Follow-up",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.AI_SCHEDULED,
        auto_action=TaskAutoAction.SEND_FOLLOWUP_MESSAGE.value,
    )

    sales_agent_client = MagicMock(spec=SalesAgentClient)
    sales_agent_client.execute_task = AsyncMock()

    context_assembler = MagicMock(spec=AgentContextAssembler)
    context_assembler.build = AsyncMock(
        return_value={"prompt_template": "", "company": {}, "customer_answers": {}, "history": [], "enabled_tools": []}
    )

    chat_service, outbound_service = _chat_and_outbound_mocks()

    executor = TaskExecutor(
        task_repo=task_repository,
        sales_agent_client=sales_agent_client,
        order_service=OrderService(),
        context_assembler=context_assembler,
        chat_service=chat_service,
        outbound_service=outbound_service,
    )

    await executor.execute_ai_task(task)

    sales_agent_client.execute_task.assert_not_called()

    failed_task = await task_repository.get_by_id(task.id)
    assert failed_task.completed is False
    assert failed_task.cancelled_at is not None
    assert failed_task.failure_reason is None


@pytest.mark.asyncio
async def test_execute_ping_task_cancelled_when_assistant_inactive(
    order_with_customer: tuple,
    task_repository: TaskRepository,
):
    """Ping-linked AI tasks are not dispatched when thread.assistant_active is False (042: maps to INACTIVE)."""
    order, _, company = order_with_customer
    await _ensure_order_charged_for_task_dispatch(order)

    connector = await Connector.create(
        connector_id="test-connector-ping-guard",
        company_id=company.id,
        type=ConnectorType.TELEGRAM,
        channel_type="telegram",
        display_name="Ping Guard Connector",
        config={},
    )

    await Thread.create(
        thread_id="test-thread-ping-guard",
        connector_id=connector.connector_id,
        company_id=company.id,
        customer_id=order.customer_id,
        channel_type="telegram",
        active_order_id=order.id,
        assistant_mode=AssistantMode.INACTIVE,
    )

    stage = await StageTemplate.filter(company_id=company.id).first()
    assert stage is not None
    ping_rule = await PingRule.create(
        company_id=company.id,
        stage_id=stage.id,
        position=0,
        delay_seconds=60,
        content_type=PingContentType.AI_GENERATED,
    )

    task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Ping follow-up",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.AI_SCHEDULED,
        auto_action=TaskAutoAction.SEND_FOLLOWUP_MESSAGE.value,
        ping_rule_id=ping_rule.id,
    )

    sales_agent_client = MagicMock(spec=SalesAgentClient)
    sales_agent_client.execute_task = AsyncMock()

    context_assembler = MagicMock(spec=AgentContextAssembler)
    context_assembler.build = AsyncMock(
        return_value={"prompt_template": "", "company": {}, "customer_answers": {}, "history": [], "enabled_tools": []}
    )

    chat_service, outbound_service = _chat_and_outbound_mocks()

    executor = TaskExecutor(
        task_repo=task_repository,
        sales_agent_client=sales_agent_client,
        order_service=OrderService(),
        context_assembler=context_assembler,
        chat_service=chat_service,
        outbound_service=outbound_service,
    )

    await executor.execute_ai_task(task)

    sales_agent_client.execute_task.assert_not_called()

    updated = await task_repository.get_by_id(task.id)
    assert updated.completed is False
    assert updated.cancelled_at is not None


@pytest.mark.asyncio
async def test_execute_ai_task_without_ping_dispatches_when_assistant_inactive(
    order_with_customer: tuple,
    task_repository: TaskRepository,
):
    """AS-IS: non-ping AI tasks ignore assistant_active; only ping_rule_id path applies the guard."""
    order, _, company = order_with_customer
    await _ensure_order_charged_for_task_dispatch(order)

    connector = await Connector.create(
        connector_id="test-connector-no-ping",
        company_id=company.id,
        type=ConnectorType.TELEGRAM,
        channel_type="telegram",
        display_name="No Ping Connector",
        config={},
    )

    await Thread.create(
        thread_id="test-thread-no-ping",
        connector_id=connector.connector_id,
        company_id=company.id,
        customer_id=order.customer_id,
        channel_type="telegram",
        active_order_id=order.id,
        assistant_mode=AssistantMode.INACTIVE,
    )

    task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="AI Follow-up",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.AI_SCHEDULED,
        auto_action=TaskAutoAction.SEND_FOLLOWUP_MESSAGE.value,
    )

    sales_agent_client = MagicMock(spec=SalesAgentClient)
    sales_agent_client.execute_task = AsyncMock()

    context_assembler = MagicMock(spec=AgentContextAssembler)
    context_assembler.build = AsyncMock(
        return_value={"prompt_template": "", "company": {}, "customer_answers": {}, "history": [], "enabled_tools": []}
    )

    chat_service, outbound_service = _chat_and_outbound_mocks()

    executor = TaskExecutor(
        task_repo=task_repository,
        sales_agent_client=sales_agent_client,
        order_service=OrderService(),
        context_assembler=context_assembler,
        chat_service=chat_service,
        outbound_service=outbound_service,
    )

    await executor.execute_ai_task(task)

    sales_agent_client.execute_task.assert_called_once()

    updated = await task_repository.get_by_id(task.id)
    assert updated.completed is True
