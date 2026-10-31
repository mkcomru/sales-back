"""Tests for Tasks API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.backend.modules.chat.models import Customer
from src.backend.modules.tasks.models import TaskType
from src.backend.modules.tasks.repository import TaskRepository


@pytest.mark.asyncio
async def test_create_and_list_order_tasks(
    api_client,
    authenticated_user_with_company,
    orders_repo,
):
    """Test creating and listing order tasks."""
    auth_data = authenticated_user_with_company
    company = auth_data["company"]

    customer = await Customer.create(
        user_id="test-customer-api",
        company_id=company.id,
        name="API Test Customer",
        meta={},
    )

    order_number = await orders_repo.get_next_order_number(company.id)
    order = await orders_repo.create_order(
        company_id=company.id,
        customer_id=customer.id,
        order_number=order_number,
        initial_channel="telegram",
    )

    create_response = await api_client.post(
        f"/api/v1/companies/{company.id}/orders/{order.id}/tasks",
        json={
            "title": "Test Task",
            "description": "Test description",
            "type": "manual",
            "due_date": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
        headers=auth_data["headers"],
    )

    assert create_response.status_code == 201
    task_data = create_response.json()
    assert task_data["title"] == "Test Task"
    assert task_data["description"] == "Test description"
    assert task_data["type"] == "manual"
    assert task_data["completed"] is False

    list_response = await api_client.get(
        f"/api/v1/companies/{company.id}/orders/{order.id}/tasks",
        headers=auth_data["headers"],
    )

    assert list_response.status_code == 200
    list_data = list_response.json()
    assert list_data["total"] == 1
    assert len(list_data["items"]) == 1
    assert list_data["items"][0]["id"] == task_data["id"]


@pytest.mark.asyncio
async def test_create_ai_scheduled_task(
    api_client,
    authenticated_user_with_company,
    orders_repo,
):
    """Test creating an AI-scheduled task."""
    from src.backend.modules.chat.models import Customer

    auth_data = authenticated_user_with_company
    company = auth_data["company"]

    customer = await Customer.create(
        user_id="test-customer-api-ai",
        company_id=company.id,
        name="API Test Customer",
        meta={},
    )

    order_number = await orders_repo.get_next_order_number(company.id)
    order = await orders_repo.create_order(
        company_id=company.id,
        customer_id=customer.id,
        order_number=order_number,
        initial_channel="telegram",
    )

    response = await api_client.post(
        f"/api/v1/companies/{company.id}/orders/{order.id}/tasks",
        json={
            "title": "AI Follow-up",
            "type": "ai_scheduled",
            "due_date": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "auto_action": "send_followup_message",
        },
        headers=auth_data["headers"],
    )

    assert response.status_code == 201
    task_data = response.json()
    assert task_data["type"] == "ai_scheduled"
    assert task_data["auto_action"] == "send_followup_message"


@pytest.mark.asyncio
async def test_create_task_validates_ai_scheduled_requires_auto_action(
    api_client,
    authenticated_user_with_company,
    orders_repo,
):
    """Test that AI_SCHEDULED tasks require auto_action."""
    from src.backend.modules.chat.models import Customer

    auth_data = authenticated_user_with_company
    company = auth_data["company"]

    customer = await Customer.create(
        user_id="test-customer-api-validate",
        company_id=company.id,
        name="API Test Customer",
        meta={},
    )

    order_number = await orders_repo.get_next_order_number(company.id)
    order = await orders_repo.create_order(
        company_id=company.id,
        customer_id=customer.id,
        order_number=order_number,
        initial_channel="telegram",
    )

    response = await api_client.post(
        f"/api/v1/companies/{company.id}/orders/{order.id}/tasks",
        json={
            "title": "AI Task",
            "type": "ai_scheduled",
            "due_date": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
        headers=auth_data["headers"],
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_complete_task_flow(
    api_client,
    authenticated_user_with_company,
    orders_repo,
    task_repository: TaskRepository,
):
    """Test completing a task."""
    from src.backend.modules.chat.models import Customer

    auth_data = authenticated_user_with_company
    company = auth_data["company"]

    customer = await Customer.create(
        user_id="test-customer-complete",
        company_id=company.id,
        name="API Test Customer",
        meta={},
    )

    order_number = await orders_repo.get_next_order_number(company.id)
    order = await orders_repo.create_order(
        company_id=company.id,
        customer_id=customer.id,
        order_number=order_number,
        initial_channel="telegram",
    )

    task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Test Task",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.MANUAL,
    )

    complete_response = await api_client.post(
        f"/api/v1/companies/{company.id}/orders/{order.id}/tasks/{task.id}/complete",
        headers=auth_data["headers"],
    )

    assert complete_response.status_code == 200
    task_data = complete_response.json()
    assert task_data["completed"] is True
    assert task_data["completed_at"] is not None
    assert task_data["completed_by_type"] == "user"

    list_response = await api_client.get(
        f"/api/v1/companies/{company.id}/orders/{order.id}/tasks",
        headers=auth_data["headers"],
    )

    assert list_response.status_code == 200
    list_data = list_response.json()
    assert list_data["total"] == 0

    list_response_with_completed = await api_client.get(
        f"/api/v1/companies/{company.id}/orders/{order.id}/tasks?include_completed=true",
        headers=auth_data["headers"],
    )

    assert list_response_with_completed.status_code == 200
    list_data_with_completed = list_response_with_completed.json()
    assert list_data_with_completed["total"] == 1


@pytest.mark.asyncio
async def test_cancel_task(
    api_client,
    authenticated_user_with_company,
    orders_repo,
    task_repository: TaskRepository,
):
    """Test cancelling a task."""
    from src.backend.modules.chat.models import Customer

    auth_data = authenticated_user_with_company
    company = auth_data["company"]

    customer = await Customer.create(
        user_id="test-customer-cancel",
        company_id=company.id,
        name="API Test Customer",
        meta={},
    )

    order_number = await orders_repo.get_next_order_number(company.id)
    order = await orders_repo.create_order(
        company_id=company.id,
        customer_id=customer.id,
        order_number=order_number,
        initial_channel="telegram",
    )

    task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Test Task",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.MANUAL,
    )

    cancel_response = await api_client.post(
        f"/api/v1/companies/{company.id}/orders/{order.id}/tasks/{task.id}/cancel",
        headers=auth_data["headers"],
    )

    assert cancel_response.status_code == 200
    task_data = cancel_response.json()
    assert task_data["cancelled_at"] is not None

    list_response = await api_client.get(
        f"/api/v1/companies/{company.id}/orders/{order.id}/tasks",
        headers=auth_data["headers"],
    )

    assert list_response.status_code == 200
    list_data = list_response.json()
    assert list_data["total"] == 0


@pytest.mark.asyncio
async def test_update_task(
    api_client,
    authenticated_user_with_company,
    orders_repo,
    task_repository: TaskRepository,
):
    """Test updating a task."""
    from src.backend.modules.chat.models import Customer

    auth_data = authenticated_user_with_company
    company = auth_data["company"]

    customer = await Customer.create(
        user_id="test-customer-update",
        company_id=company.id,
        name="API Test Customer",
        meta={},
    )

    order_number = await orders_repo.get_next_order_number(company.id)
    order = await orders_repo.create_order(
        company_id=company.id,
        customer_id=customer.id,
        order_number=order_number,
        initial_channel="telegram",
    )

    task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Test Task",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.MANUAL,
    )

    update_response = await api_client.patch(
        f"/api/v1/companies/{company.id}/orders/{order.id}/tasks/{task.id}",
        json={
            "title": "Updated Title",
            "description": "Updated description",
            "due_date": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
        },
        headers=auth_data["headers"],
    )

    assert update_response.status_code == 200
    task_data = update_response.json()
    assert task_data["title"] == "Updated Title"
    assert task_data["description"] == "Updated description"


@pytest.mark.asyncio
async def test_get_order_task(
    api_client,
    authenticated_user_with_company,
    orders_repo,
    task_repository: TaskRepository,
):
    """Test GET single task for an order."""
    auth_data = authenticated_user_with_company
    company = auth_data["company"]

    customer = await Customer.create(
        user_id="test-customer-get-task",
        company_id=company.id,
        name="API Test Customer",
        meta={},
    )

    order_number = await orders_repo.get_next_order_number(company.id)
    order = await orders_repo.create_order(
        company_id=company.id,
        customer_id=customer.id,
        order_number=order_number,
        initial_channel="telegram",
    )

    task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Single GET",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.MANUAL,
    )

    get_response = await api_client.get(
        f"/api/v1/companies/{company.id}/orders/{order.id}/tasks/{task.id}",
        headers=auth_data["headers"],
    )
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["id"] == task.id
    assert body["title"] == "Single GET"
    assert body["order_id"] == order.id

    wrong_order = await api_client.get(
        f"/api/v1/companies/{company.id}/orders/{order.id + 99999}/tasks/{task.id}",
        headers=auth_data["headers"],
    )
    assert wrong_order.status_code == 404


@pytest.mark.asyncio
async def test_my_tasks_endpoint(
    api_client,
    authenticated_user_with_company,
    orders_repo,
    task_repository: TaskRepository,
):
    """Test listing tasks assigned to current user."""
    from src.backend.modules.chat.models import Customer

    auth_data = authenticated_user_with_company
    company = auth_data["company"]
    assignee_id = auth_data["company_user"].id

    customer = await Customer.create(
        user_id="test-customer-my-tasks",
        company_id=company.id,
        name="API Test Customer",
        meta={},
    )

    order_number = await orders_repo.get_next_order_number(company.id)
    order = await orders_repo.create_order(
        company_id=company.id,
        customer_id=customer.id,
        order_number=order_number,
        initial_channel="telegram",
    )

    assigned_task = await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="My Task",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.MANUAL,
        assignee_id=assignee_id,
    )

    await task_repository.create_order_task(
        company_id=company.id,
        order_id=order.id,
        title="Not My Task",
        due_date=datetime.now(UTC) + timedelta(days=1),
        type=TaskType.MANUAL,
    )

    response = await api_client.get(
        f"/api/v1/companies/{company.id}/my-tasks",
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == assigned_task.id


@pytest.mark.asyncio
async def test_task_permissions_different_company(
    api_client,
    authenticated_user_with_company,
    company_factory,
):
    """Test that users cannot access tasks from other companies."""
    auth_data = authenticated_user_with_company
    other_company = await company_factory()

    response = await api_client.get(
        f"/api/v1/companies/{other_company.id}/orders/1/tasks",
        headers=auth_data["headers"],
    )

    assert response.status_code in (403, 404)


@pytest.mark.asyncio
async def test_task_not_found(
    api_client,
    authenticated_user_with_company,
    orders_repo,
):
    """Test accessing non-existent task returns 404."""
    from src.backend.modules.chat.models import Customer

    auth_data = authenticated_user_with_company
    company = auth_data["company"]

    customer = await Customer.create(
        user_id="test-customer-not-found",
        company_id=company.id,
        name="API Test Customer",
        meta={},
    )

    order_number = await orders_repo.get_next_order_number(company.id)
    order = await orders_repo.create_order(
        company_id=company.id,
        customer_id=customer.id,
        order_number=order_number,
        initial_channel="telegram",
    )

    response = await api_client.post(
        f"/api/v1/companies/{company.id}/orders/{order.id}/tasks/99999/complete",
        headers=auth_data["headers"],
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_pagination(
    api_client,
    authenticated_user_with_company,
    orders_repo,
    task_repository: TaskRepository,
):
    """Test pagination for task listing."""
    from src.backend.modules.chat.models import Customer

    auth_data = authenticated_user_with_company
    company = auth_data["company"]

    customer = await Customer.create(
        user_id="test-customer-pagination",
        company_id=company.id,
        name="API Test Customer",
        meta={},
    )

    order_number = await orders_repo.get_next_order_number(company.id)
    order = await orders_repo.create_order(
        company_id=company.id,
        customer_id=customer.id,
        order_number=order_number,
        initial_channel="telegram",
    )

    for i in range(5):
        await task_repository.create_order_task(
            company_id=company.id,
            order_id=order.id,
            title=f"Task {i}",
            due_date=datetime.now(UTC) + timedelta(days=i + 1),
            type=TaskType.MANUAL,
        )

    response = await api_client.get(
        f"/api/v1/companies/{company.id}/orders/{order.id}/tasks?limit=2&offset=0",
        headers=auth_data["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["limit"] == 2
    assert data["offset"] == 0

    response_page2 = await api_client.get(
        f"/api/v1/companies/{company.id}/orders/{order.id}/tasks?limit=2&offset=2",
        headers=auth_data["headers"],
    )

    assert response_page2.status_code == 200
    data_page2 = response_page2.json()
    assert len(data_page2["items"]) == 2
    assert data_page2["offset"] == 2
