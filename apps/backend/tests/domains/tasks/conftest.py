"""Task test fixtures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from common.models import TaskAutoAction

from src.backend.modules.chat.models import Customer
from src.backend.modules.companies.models import Company
from src.backend.modules.orders.models import Order
from src.backend.modules.orders.repository import OrdersRepository
from src.backend.modules.orders.service import OrderService
from src.backend.modules.tasks.models import CompletedByType, Task, TaskType
from src.backend.modules.tasks.repository import TaskRepository
from src.backend.modules.tasks.service import TaskService
from src.backend.modules.users.models import CompanyUser, User, UserRole


@pytest.fixture
def orders_repo() -> OrdersRepository:
    """Create orders repository instance."""
    return OrdersRepository()


@pytest.fixture
def task_repository() -> TaskRepository:
    """Create task repository instance."""
    return TaskRepository()


@pytest.fixture
def task_service(task_repository: TaskRepository) -> TaskService:
    """Create task service instance."""
    return TaskService(task_repository, OrderService())


@pytest.fixture
async def order_with_customer(company) -> tuple[Order, Customer, Company]:
    """Create order with customer and company."""
    customer = await Customer.create(
        user_id="test-customer-tasks",
        company_id=company.id,
        name="Test Customer",
        meta={},
    )
    orders_repo = OrdersRepository()
    order_number = await orders_repo.get_next_order_number(company.id)
    order = await orders_repo.create_order(
        company_id=company.id,
        customer_id=customer.id,
        order_number=order_number,
        initial_channel="telegram",
    )
    return order, customer, company


@pytest.fixture
async def assignee_user(company) -> CompanyUser:
    """Create assignee user for tasks."""
    user = await User.create(
        first_name="Assignee",
        last_name="User",
        email="assignee@test.com",
        hashed_password="hashed",  # pragma: allowlist secret
        is_active=True,
        is_superuser=False,
    )
    company_user = await CompanyUser.create(
        user_id=user.id,
        company_id=company.id,
        role=UserRole.ADMIN,
    )
    return company_user


@pytest.fixture
async def task_for_order(
    order_with_customer: tuple[Order, Customer, Company],
    task_repository: TaskRepository,
) -> tuple[Task, Order, Company]:
    """Create a task for an order."""
    order, _, company = order_with_customer
    task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Test Task",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.MANUAL,
    )
    return task, order, company


@pytest.fixture
async def ai_task_for_order(
    order_with_customer: tuple[Order, Customer, Company],
    task_repository: TaskRepository,
) -> tuple[Task, Order, Company]:
    """Create an AI-scheduled task for an order."""
    order, _, company = order_with_customer
    task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="AI Follow-up Task",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.AI_SCHEDULED,
        auto_action=TaskAutoAction.SEND_FOLLOWUP_MESSAGE.value,
    )
    return task, order, company


@pytest.fixture
async def due_task(
    order_with_customer: tuple[Order, Customer, Company],
    task_repository: TaskRepository,
) -> tuple[Task, Order, Company]:
    """Create a task that is due (past due_date)."""
    order, _, company = order_with_customer
    task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Due Task",
        due_date=datetime.now(UTC) - timedelta(hours=1),
        type=TaskType.AI_SCHEDULED,
        auto_action=TaskAutoAction.SEND_FOLLOWUP_MESSAGE.value,
    )
    return task, order, company


@pytest.fixture
async def completed_task(
    order_with_customer: tuple[Order, Customer, Company],
    task_repository: TaskRepository,
) -> tuple[Task, Order, Company]:
    """Create a completed task."""
    order, _, company = order_with_customer
    task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Completed Task",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.MANUAL,
    )
    await task_repository.complete_task(task.id, CompletedByType.USER)
    return task, order, company


@pytest.fixture
async def cancelled_task(
    order_with_customer: tuple[Order, Customer, Company],
    task_repository: TaskRepository,
) -> tuple[Task, Order, Company]:
    """Create a cancelled task."""
    order, _, company = order_with_customer
    task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Cancelled Task",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.MANUAL,
    )
    await task_repository.cancel_task(task.id)
    return task, order, company
