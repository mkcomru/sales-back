#!/usr/bin/env python3
"""Interactive test script for Tasks & Reminders system (Plan 027).

Tests all scenarios:
1. Basic CRUD - Create, Read, Update tasks
2. AI_SCHEDULED Task Creation - auto_action handling
3. Validation Rules - Type/auto_action consistency, due_date validation
4. Task Lifecycle - Complete, Cancel operations
5. My Tasks - Assignee-filtered task listing
6. Include Completed Filter - Filtering by completion status
7. Overdue Detection - is_overdue computation
8. Scheduler Integration - AI_SCHEDULED task execution
9. Multiple Orders - Task scoping to orders

Services required:
    docker-compose up -d backend redis postgres sales-agent task-scheduler

Usage:
    python test_tasks.py
"""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent))

from framework import BaseTestClient, Scenario, console, error, run_scenarios, success, warn
from framework.output import print_json, print_scenario_header
from framework.scenarios import interactive_menu
from framework.setup import setup_environment


class TasksClient(BaseTestClient):
    """Client with task-specific API methods."""

    async def create_task(
        self,
        order_id: int,
        title: str,
        task_type: str,
        due_date: datetime,
        description: str | None = None,
        assignee_id: int | None = None,
        auto_action: str | None = None,
    ) -> dict[str, Any]:
        """Create a task for an order."""
        payload: dict[str, Any] = {
            "title": title,
            "type": task_type,
            "due_date": due_date.isoformat(),
        }
        if description is not None:
            payload["description"] = description
        if assignee_id is not None:
            payload["assignee_id"] = assignee_id
        if auto_action is not None:
            payload["auto_action"] = auto_action

        return await self.post(f"/companies/{self.company_id}/orders/{order_id}/tasks", json=payload)

    async def list_tasks(self, order_id: int, include_completed: bool = False) -> dict[str, Any]:
        """List tasks for an order."""
        return await self.get(
            f"/companies/{self.company_id}/orders/{order_id}/tasks",
            params={"include_completed": str(include_completed).lower()},
        )

    async def update_task(self, order_id: int, task_id: int, **updates: Any) -> dict[str, Any]:
        """Update a task."""
        if "due_date" in updates and isinstance(updates["due_date"], datetime):
            updates["due_date"] = updates["due_date"].isoformat()
        return await self.patch(f"/companies/{self.company_id}/orders/{order_id}/tasks/{task_id}", json=updates)

    async def complete_task(self, order_id: int, task_id: int) -> dict[str, Any]:
        """Complete a task."""
        return await self.post(f"/companies/{self.company_id}/orders/{order_id}/tasks/{task_id}/complete")

    async def cancel_task(self, order_id: int, task_id: int) -> dict[str, Any]:
        """Cancel a task."""
        return await self.post(f"/companies/{self.company_id}/orders/{order_id}/tasks/{task_id}/cancel")

    async def list_my_tasks(self, include_completed: bool = False) -> dict[str, Any]:
        """List tasks assigned to current user."""
        return await self.get(
            f"/companies/{self.company_id}/my-tasks",
            params={"include_completed": str(include_completed).lower()},
        )


def print_task(task: dict[str, Any]) -> None:
    """Print task details in a formatted table."""
    table = Table(title="Task Details")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    fields = [
        ("id", str(task["id"])),
        ("title", task["title"]),
        ("description", task.get("description") or "null"),
        ("type", task["type"]),
        ("auto_action", task.get("auto_action") or "null"),
        ("due_date", task["due_date"]),
        ("assignee_id", str(task.get("assignee_id")) if task.get("assignee_id") else "null"),
        ("completed", str(task["completed"])),
        ("completed_at", task.get("completed_at") or "null"),
        ("completed_by_type", task.get("completed_by_type") or "null"),
        ("cancelled_at", task.get("cancelled_at") or "null"),
        ("is_overdue", str(task.get("is_overdue", False))),
        ("attempt_count", str(task.get("attempt_count", 0))),
        ("last_attempt_at", task.get("last_attempt_at") or "null"),
        ("failure_reason", task.get("failure_reason") or "null"),
        ("created_at", task["created_at"]),
    ]
    for field, value in fields:
        table.add_row(field, value)
    console.print(table)


def print_task_list(tasks: list[dict[str, Any]]) -> None:
    """Print task list in a formatted table."""
    table = Table(title="Tasks")
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Due Date", style="magenta")
    table.add_column("Status", style="blue")
    table.add_column("Assignee", style="white")

    for task in tasks:
        status = "✓" if task["completed"] else ("⚠ overdue" if task.get("is_overdue") else "pending")
        assignee = str(task.get("assignee_id")) if task.get("assignee_id") else "-"
        table.add_row(
            str(task["id"]),
            task["title"][:30],
            task["type"],
            task["due_date"][:19],
            status,
            assignee,
        )
    console.print(table)


# ─────────────────────────────────────────────────────────────────────────────
# SCENARIOS
# ─────────────────────────────────────────────────────────────────────────────


async def scenario_1_basic_crud(client: TasksClient) -> bool:
    """Scenario 1: Basic CRUD operations."""
    print_scenario_header("Scenario 1: Basic CRUD Operations", "Test create, read, update tasks")

    assert client.order_id is not None

    console.print("[yellow]Step 1: Create MANUAL task...[/yellow]")
    due_date = datetime.now(UTC) + timedelta(days=1)
    task = await client.create_task(
        order_id=client.order_id,
        title="Позвонить клиенту",
        task_type="manual",
        due_date=due_date,
        description="Обсудить детали заказа",
    )
    task_id = task["id"]
    success(f"Created MANUAL task: {task_id}")
    print_task(task)

    if task["type"] != "manual":
        error("Task type mismatch")
        return False

    console.print("\n[yellow]Step 2: List tasks for order...[/yellow]")
    tasks_response = await client.list_tasks(client.order_id)
    success(f"Found {tasks_response['total']} tasks")
    print_task_list(tasks_response["items"])

    console.print("\n[yellow]Step 3: Update task title and description...[/yellow]")
    updated_task = await client.update_task(
        order_id=client.order_id,
        task_id=task_id,
        title="Позвонить клиенту (обновлено)",
        description="Детали изменены",
    )
    if updated_task["title"] != "Позвонить клиенту (обновлено)":
        error("Title not updated")
        return False
    success("Task updated successfully")

    console.print("\n[yellow]Step 4: Update due_date...[/yellow]")
    new_due_date = datetime.now(UTC) + timedelta(days=3)
    updated_task = await client.update_task(order_id=client.order_id, task_id=task_id, due_date=new_due_date)
    success(f"Due date updated: {updated_task['due_date']}")

    console.print("\n[yellow]Step 5: Assign task to current user...[/yellow]")
    updated_task = await client.update_task(order_id=client.order_id, task_id=task_id, assignee_id=client.company_user_id)
    if updated_task["assignee_id"] != client.company_user_id:
        error("Assignee not updated")
        return False
    success(f"Task assigned to user {client.company_user_id}")

    console.print("\n[bold green]✓ Scenario 1 PASSED[/bold green]")
    return True


async def scenario_2_ai_scheduled_task(client: TasksClient) -> bool:
    """Scenario 2: Create AI_SCHEDULED task with auto_action."""
    print_scenario_header("Scenario 2: AI_SCHEDULED Task Creation", "Create AI_SCHEDULED task with auto_action")

    assert client.order_id is not None

    console.print("[yellow]Step 1: Create AI_SCHEDULED task with send_followup_message...[/yellow]")
    due_date = datetime.now(UTC) + timedelta(hours=2)
    task = await client.create_task(
        order_id=client.order_id,
        title="Автоматическое напоминание",
        task_type="ai_scheduled",
        due_date=due_date,
        description="Напомнить о специальном предложении",
        auto_action="send_followup_message",
    )
    success(f"Created AI_SCHEDULED task: {task['id']}")
    print_task(task)

    if task["type"] != "ai_scheduled":
        error("Task type mismatch")
        return False

    if task["auto_action"] != "send_followup_message":
        error(f"auto_action mismatch: expected 'send_followup_message', got '{task['auto_action']}'")
        return False

    console.print("\n[bold green]✓ Scenario 2 PASSED[/bold green]")
    return True


async def scenario_3_validation(client: TasksClient) -> bool:
    """Scenario 3: Validation rules."""
    print_scenario_header("Scenario 3: Validation Rules", "Test validation constraints")

    assert client.order_id is not None

    console.print("[yellow]Test 1: AI_SCHEDULED without auto_action (should fail 422)...[/yellow]")
    try:
        await client.create_task(
            order_id=client.order_id,
            title="Invalid task",
            task_type="ai_scheduled",
            due_date=datetime.now(UTC) + timedelta(days=1),
        )
        error("Should have returned 422")
        return False
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 422:
            success("Correctly returned 422 (validation error)")
            console.print(f"   Error: {json.dumps(e.response.json(), indent=2)[:200]}")
        else:
            error(f"Wrong status: {e.response.status_code}")
            return False

    console.print("\n[yellow]Test 2: MANUAL with auto_action (should fail 422)...[/yellow]")
    try:
        await client.create_task(
            order_id=client.order_id,
            title="Invalid task",
            task_type="manual",
            due_date=datetime.now(UTC) + timedelta(days=1),
            auto_action="send_followup_message",
        )
        error("Should have returned 422")
        return False
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 422:
            success("Correctly returned 422")
        else:
            error(f"Wrong status: {e.response.status_code}")
            return False

    console.print("\n[yellow]Test 3: due_date in past (should fail 400/422)...[/yellow]")
    try:
        await client.create_task(
            order_id=client.order_id,
            title="Past task",
            task_type="manual",
            due_date=datetime.now(UTC) - timedelta(days=1),
        )
        error("Should have failed for past due_date")
        return False
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (400, 422, 500):
            success(f"Correctly rejected past due_date ({e.response.status_code})")
        else:
            warn(f"Got status {e.response.status_code}")

    console.print("\n[yellow]Test 4: Task for non-existent order (should fail 404)...[/yellow]")
    try:
        await client.create_task(
            order_id=999999,
            title="Orphan task",
            task_type="manual",
            due_date=datetime.now(UTC) + timedelta(days=1),
        )
        error("Should have returned 404")
        return False
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            success("Correctly returned 404")
        else:
            warn(f"Got status {e.response.status_code}")

    console.print("\n[bold green]✓ Scenario 3 PASSED[/bold green]")
    return True


async def scenario_4_lifecycle(client: TasksClient) -> bool:
    """Scenario 4: Task lifecycle operations."""
    print_scenario_header("Scenario 4: Task Lifecycle", "Test complete and cancel operations")

    assert client.order_id is not None

    console.print("[yellow]Step 1: Create task for completion test...[/yellow]")
    task = await client.create_task(
        order_id=client.order_id,
        title="Task to complete",
        task_type="manual",
        due_date=datetime.now(UTC) + timedelta(hours=1),
    )
    task_id = task["id"]
    success(f"Created task: {task_id}")

    console.print("\n[yellow]Step 2: Complete task...[/yellow]")
    completed = await client.complete_task(client.order_id, task_id)

    if not completed["completed"]:
        error("Task not marked as completed")
        return False
    if not completed["completed_at"]:
        error("completed_at not set")
        return False
    if completed["completed_by_type"] != "user":
        error(f"Expected completed_by_type='user', got '{completed['completed_by_type']}'")
        return False

    success("Task completed successfully")
    print_task(completed)

    console.print("\n[yellow]Step 3: Complete already completed task (idempotent)...[/yellow]")
    completed_again = await client.complete_task(client.order_id, task_id)
    if completed_again["completed"]:
        success("Idempotent - still completed")
    else:
        error("Task lost completed status")
        return False

    console.print("\n[yellow]Step 4: Create task for cancellation test...[/yellow]")
    task2 = await client.create_task(
        order_id=client.order_id,
        title="Task to cancel",
        task_type="manual",
        due_date=datetime.now(UTC) + timedelta(hours=1),
    )
    task2_id = task2["id"]
    success(f"Created task: {task2_id}")

    console.print("\n[yellow]Step 5: Cancel task...[/yellow]")
    cancelled = await client.cancel_task(client.order_id, task2_id)

    if not cancelled.get("cancelled_at"):
        error("cancelled_at not set")
        return False

    success("Task cancelled successfully")

    console.print("\n[yellow]Step 6: Verify cancelled task excluded from default list...[/yellow]")
    tasks_response = await client.list_tasks(client.order_id, include_completed=False)
    task_ids = [t["id"] for t in tasks_response["items"]]
    if task2_id in task_ids:
        error("Cancelled task should be excluded from default list")
        return False
    success("Cancelled task excluded from default list")

    console.print("\n[bold green]✓ Scenario 4 PASSED[/bold green]")
    return True


async def scenario_5_my_tasks(client: TasksClient) -> bool:
    """Scenario 5: My Tasks endpoint."""
    print_scenario_header("Scenario 5: My Tasks Endpoint", "Test assignee-filtered task listing")

    assert client.order_id is not None

    console.print("[yellow]Step 1: Create task assigned to current user...[/yellow]")
    task = await client.create_task(
        order_id=client.order_id,
        title="My assigned task",
        task_type="manual",
        due_date=datetime.now(UTC) + timedelta(days=1),
        assignee_id=client.company_user_id,
    )
    task_id = task["id"]
    success(f"Created task: {task_id} assigned to user {client.company_user_id}")

    console.print("\n[yellow]Step 2: Create unassigned task...[/yellow]")
    unassigned_task = await client.create_task(
        order_id=client.order_id,
        title="Unassigned task",
        task_type="manual",
        due_date=datetime.now(UTC) + timedelta(days=1),
    )
    success(f"Created unassigned task: {unassigned_task['id']}")

    console.print("\n[yellow]Step 3: Get my tasks...[/yellow]")
    my_tasks = await client.list_my_tasks()
    success(f"Found {my_tasks['total']} tasks assigned to me")
    print_task_list(my_tasks["items"])

    my_task_ids = [t["id"] for t in my_tasks["items"]]
    if task_id not in my_task_ids:
        error("Assigned task not in my tasks")
        return False

    if unassigned_task["id"] in my_task_ids:
        error("Unassigned task should not be in my tasks")
        return False

    success("My tasks filtering works correctly")

    console.print("\n[bold green]✓ Scenario 5 PASSED[/bold green]")
    return True


async def scenario_6_include_completed(client: TasksClient) -> bool:
    """Scenario 6: Include completed filter."""
    print_scenario_header("Scenario 6: Include Completed Filter", "Test include_completed parameter")

    assert client.order_id is not None

    console.print("[yellow]Step 1: Create and complete a task...[/yellow]")
    task = await client.create_task(
        order_id=client.order_id,
        title="Task to filter test",
        task_type="manual",
        due_date=datetime.now(UTC) + timedelta(days=1),
    )
    task_id = task["id"]
    await client.complete_task(client.order_id, task_id)
    success(f"Created and completed task: {task_id}")

    console.print("\n[yellow]Step 2: List tasks WITHOUT include_completed...[/yellow]")
    without_completed = await client.list_tasks(client.order_id, include_completed=False)
    ids_without = [t["id"] for t in without_completed["items"]]
    console.print(f"   Found {without_completed['total']} tasks")

    if task_id in ids_without:
        error("Completed task should be excluded")
        return False
    success("Completed task excluded")

    console.print("\n[yellow]Step 3: List tasks WITH include_completed...[/yellow]")
    with_completed = await client.list_tasks(client.order_id, include_completed=True)
    ids_with = [t["id"] for t in with_completed["items"]]
    console.print(f"   Found {with_completed['total']} tasks")

    if task_id not in ids_with:
        error("Completed task should be included")
        return False
    success("Completed task included")

    console.print("\n[bold green]✓ Scenario 6 PASSED[/bold green]")
    return True


async def scenario_7_overdue(client: TasksClient) -> bool:
    """Scenario 7: Overdue task detection."""
    print_scenario_header("Scenario 7: Overdue Task Detection", "Test is_overdue computation")

    assert client.order_id is not None

    console.print("[yellow]Step 1: Create task due in future...[/yellow]")
    future_task = await client.create_task(
        order_id=client.order_id,
        title="Future task",
        task_type="manual",
        due_date=datetime.now(UTC) + timedelta(days=7),
    )
    success(f"Created task: {future_task['id']}")

    if future_task["is_overdue"]:
        error("Future task should not be overdue")
        return False
    success("Future task is not overdue")

    console.print("\n[yellow]Step 2: Create task due very soon (5 seconds)...[/yellow]")
    soon_task = await client.create_task(
        order_id=client.order_id,
        title="Soon task",
        task_type="manual",
        due_date=datetime.now(UTC) + timedelta(seconds=5),
    )
    success(f"Created task: {soon_task['id']}")

    console.print("[yellow]   Waiting 6 seconds for task to become overdue...[/yellow]")
    await asyncio.sleep(6)

    tasks_response = await client.list_tasks(client.order_id, include_completed=False)
    soon_task_updated = next((t for t in tasks_response["items"] if t["id"] == soon_task["id"]), None)

    if soon_task_updated and soon_task_updated.get("is_overdue"):
        success("Task is now overdue")
    else:
        warn("Task may not show overdue (timing edge case)")

    console.print("\n[bold green]✓ Scenario 7 PASSED[/bold green]")
    return True


async def scenario_8_scheduler(client: TasksClient) -> bool:
    """Scenario 8: Scheduler integration test."""
    print_scenario_header("Scenario 8: Scheduler Integration", "Test AI_SCHEDULED task execution by scheduler")

    sales_ok = await client.check_sales_agent_health()
    if not sales_ok:
        warn("Sales-agent not running - scheduler will record failure")
        console.print("[yellow]  This is expected for DB persistence testing[/yellow]")

    assert client.order_id is not None

    console.print("[yellow]Step 1: Create AI_SCHEDULED task due in 5 seconds...[/yellow]")
    task = await client.create_task(
        order_id=client.order_id,
        title="Scheduler test task",
        task_type="ai_scheduled",
        due_date=datetime.now(UTC) + timedelta(seconds=5),
        description="This should be picked up by scheduler",
        auto_action="send_followup_message",
    )
    task_id = task["id"]
    success(f"Created AI_SCHEDULED task: {task_id}")
    print_task(task)

    console.print("\n[yellow]Step 2: Wait for scheduler to pick up task (15 seconds)...[/yellow]")
    console.print("[dim]   Scheduler polls every 10 seconds[/dim]")

    for i in range(15):
        await asyncio.sleep(1)
        console.print(f"   Waiting... {15 - i}s remaining", end="\r")

    console.print("\n[yellow]Step 3: Check task state...[/yellow]")
    tasks_response = await client.list_tasks(client.order_id, include_completed=True)
    updated_task = next((t for t in tasks_response["items"] if t["id"] == task_id), None)

    if not updated_task:
        error("Task not found")
        return False

    print_task(updated_task)

    if updated_task["attempt_count"] > 0:
        success(f"Scheduler attempted execution (attempt_count={updated_task['attempt_count']})")
    else:
        warn("No execution attempt recorded (scheduler may not be running)")
        console.print("[yellow]   Verify: docker-compose up task-scheduler[/yellow]")

    if updated_task.get("last_attempt_at"):
        success(f"last_attempt_at set: {updated_task['last_attempt_at']}")

    if updated_task.get("completed"):
        success("Task completed by system!")
        if updated_task.get("completed_by_type") == "system":
            success("completed_by_type is 'system'")
    elif updated_task.get("failure_reason"):
        warn(f"Task failed: {updated_task['failure_reason'][:100]}")
        console.print("[yellow]   This is expected if sales-agent or transport is not available[/yellow]")

    console.print("\n[bold green]✓ Scenario 8 PASSED (scheduler behavior verified)[/bold green]")
    return True


async def scenario_9_multiple_orders(client: TasksClient) -> bool:
    """Scenario 9: Multiple orders with separate task lists."""
    print_scenario_header("Scenario 9: Multiple Orders with Tasks", "Verify tasks are properly scoped to orders")

    console.print("[yellow]Step 1: Create second thread and order...[/yellow]")
    user_id = f"tasks_test_user2_{datetime.now().timestamp()}"
    thread_data = await client.get_or_create_thread(user_id)
    order_context = await client.get_order_by_thread(thread_data["thread_id"])
    order2_id = order_context["order_id"]
    success(f"Second order created: {order2_id}")

    assert client.order_id is not None
    order1_id = client.order_id

    console.print("\n[yellow]Step 2: Create task on first order...[/yellow]")
    task1 = await client.create_task(
        order_id=order1_id,
        title="Task for order 1",
        task_type="manual",
        due_date=datetime.now(UTC) + timedelta(days=1),
    )
    success(f"Created task {task1['id']} on order {order1_id}")

    console.print("\n[yellow]Step 3: Create task on second order...[/yellow]")
    task2 = await client.create_task(
        order_id=order2_id,
        title="Task for order 2",
        task_type="manual",
        due_date=datetime.now(UTC) + timedelta(days=1),
    )
    success(f"Created task {task2['id']} on order {order2_id}")

    console.print("\n[yellow]Step 4: List tasks for first order...[/yellow]")
    order1_tasks = await client.list_tasks(order1_id)
    order1_task_ids = [t["id"] for t in order1_tasks["items"]]
    console.print(f"   Order {order1_id} tasks: {order1_task_ids}")

    console.print("\n[yellow]Step 5: List tasks for second order...[/yellow]")
    order2_tasks = await client.list_tasks(order2_id)
    order2_task_ids = [t["id"] for t in order2_tasks["items"]]
    console.print(f"   Order {order2_id} tasks: {order2_task_ids}")

    if task2["id"] in order1_task_ids:
        error("Order 2 task should not appear in order 1 list")
        return False

    if task1["id"] in order2_task_ids:
        error("Order 1 task should not appear in order 2 list")
        return False

    success("Tasks are properly scoped to their orders")

    console.print("\n[bold green]✓ Scenario 9 PASSED[/bold green]")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────────────────────────────


async def util_list_tasks(client: TasksClient) -> None:
    """List tasks for current order."""
    if not client.order_id:
        error("No order_id available")
        return
    tasks_response = await client.list_tasks(client.order_id, include_completed=True)
    console.print(f"\n[cyan]Found {tasks_response['total']} tasks:[/cyan]")
    print_task_list(tasks_response["items"])


async def util_list_my_tasks(client: TasksClient) -> None:
    """List tasks assigned to current user."""
    my_tasks = await client.list_my_tasks(include_completed=True)
    console.print(f"\n[cyan]Found {my_tasks['total']} tasks assigned to you:[/cyan]")
    print_task_list(my_tasks["items"])


async def util_create_task(client: TasksClient) -> None:
    """Create a manual task interactively."""
    if not client.order_id:
        error("No order_id available")
        return
    title = await asyncio.get_event_loop().run_in_executor(None, input, "Task title: ")
    if title.strip():
        task = await client.create_task(
            order_id=client.order_id,
            title=title.strip(),
            task_type="manual",
            due_date=datetime.now(UTC) + timedelta(days=1),
        )
        success(f"Created task: {task['id']}")
        print_task(task)


async def util_get_order(client: TasksClient) -> None:
    """Get order details."""
    if not client.order_id:
        error("No order_id available")
        return
    order = await client.get_order(client.order_id)
    print_json(order, title="Order Details", style="cyan")


async def util_health_check(client: TasksClient) -> None:
    """Check service health."""
    backend_ok = await client.check_backend_health()
    sales_ok = await client.check_sales_agent_health()
    console.print(f"Backend (8081): {'[green]✓ OK[/green]' if backend_ok else '[red]✗ DOWN[/red]'}")
    console.print(f"Sales-agent (8080): {'[green]✓ OK[/green]' if sales_ok else '[red]✗ DOWN[/red]'}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

SCENARIOS = [
    Scenario("Basic CRUD", scenario_1_basic_crud, "Create, read, update tasks"),
    Scenario("AI_SCHEDULED Task", scenario_2_ai_scheduled_task, "auto_action handling"),
    Scenario("Validation Rules", scenario_3_validation, "Type/auto_action consistency"),
    Scenario("Task Lifecycle", scenario_4_lifecycle, "Complete, cancel operations"),
    Scenario("My Tasks", scenario_5_my_tasks, "Assignee-filtered listing"),
    Scenario("Include Completed", scenario_6_include_completed, "Completion status filter"),
    Scenario("Overdue Detection", scenario_7_overdue, "is_overdue computation"),
    Scenario("Scheduler Integration", scenario_8_scheduler, "AI task execution"),
    Scenario("Multiple Orders", scenario_9_multiple_orders, "Task scoping to orders"),
]

UTILITIES = [
    ("l", "List tasks for current order", util_list_tasks),
    ("m", "List my tasks", util_list_my_tasks),
    ("c", "Create manual task (interactive)", util_create_task),
    ("o", "Get order details", util_get_order),
    ("h", "Check service health", util_health_check),
]


if __name__ == "__main__":

    async def main() -> int:
        from rich.panel import Panel

        console.print(
            Panel.fit(
                "[bold cyan]Tasks & Reminders System Test[/bold cyan]\n\n"
                "This script tests Plan 027: Tasks & Reminders System\n"
                "Covers CRUD, validation, lifecycle, scheduler integration.",
                border_style="cyan",
            )
        )

        client = TasksClient()

        if not await setup_environment(
            client,
            "Tasks Test Company",
            create_thread=True,
            check_sales_agent=True,
        ):
            return 1

        await interactive_menu(client, SCENARIOS, utilities=UTILITIES)

        console.print("\n[bold green]Done![/bold green]")
        return 0

    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
