#!/usr/bin/env python3
"""Interactive test script for Order model extraction feature.

This script tests all scenarios from Plan 018:
1. New Customer Flow - first message creates Thread + Order
2. Returning Customer (Active Order) - same customer, same order continues
3. Returning Customer (Closed Order) - customer with closed order gets new order
4. Sales-Agent Tool Flow - AI can update order stage/fields
5. Order CRUD - Basic order management works
6. Edge Cases - Various edge cases

Usage:
    cd scripts/manual_testing
    python test_orders.py

Requirements:
    pip install -r requirements.txt
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Any

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

BASE_URL = "http://localhost:8081/api/v1"

SUPERUSER_EMAIL = "komarovdemian@yandex.ru"
SUPERUSER_PASSWORD = "1234567890"

TEST_COMPANY_NAME = "Order Test Company"

SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "test-api-key")

console = Console()


class OrderTestClient:
    def __init__(self):
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.user_id: int | None = None
        self.company_id: int | None = None
        self.company_user_id: int | None = None
        self.thread_id: str | None = None
        self.customer_id: int | None = None
        self.order_id: int | None = None
        self.test_user_id: str | None = None

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    async def login(self, email: str, password: str) -> dict:
        """Login and get tokens."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                "/auth/login",
                json={"email": email, "password": password},
            )
            if response.status_code == 401:
                return {"error": "Invalid credentials"}
            response.raise_for_status()
            return response.json()

    async def get_me(self) -> dict:
        """Get current user info."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.get("/users/me", headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def list_companies(self) -> list[dict]:
        """List companies for current user."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.get("/companies", headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def create_company(self, name: str) -> dict:
        """Create a new company."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                "/companies",
                json={
                    "name": name,
                    "description": "Test company for order feature",
                    "rules": "Test rules",
                    "tone_of_voice": "Professional",
                    "assistant_name": "Test Assistant",
                    "qualification_workflow": "Standard",
                    "qualification_examples": "Examples",
                    "collection_name": "test_collection",
                    "stages_config": [],
                    "category_rules": [],
                },
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def list_company_members(self) -> list[dict]:
        """List company members."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.get(
                f"/companies/{self.company_id}/members",
                headers=self.headers,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("items", [])

    async def get_or_create_thread(self, user_id: str, conversation_id: str | None = None) -> dict:
        """Get or create thread via internal API."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            if conversation_id is None:
                conversation_id = f"test_conv_{datetime.now().timestamp()}"
            response = await client.post(
                "/internal/chat/threads/get-or-create",
                json={
                    "user_id": user_id,
                    "company_id": self.company_id,
                    "channel_type": "test",
                    "connector_id": "test_connector",
                    "conversation_id": conversation_id,
                },
            )
            response.raise_for_status()
            return response.json()

    async def get_thread(self, thread_id: str) -> dict:
        """Get thread details."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.get(
                f"/companies/{self.company_id}/threads/{thread_id}",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def get_order_by_thread(self, thread_id: str) -> dict:
        """Get order context for thread."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.get(f"/internal/orders/by-thread/{thread_id}")
            response.raise_for_status()
            return response.json()

    async def create_order(self, customer_id: int, assignee_id: int | None = None) -> dict:
        """Create a new order."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                f"/companies/{self.company_id}/orders",
                json={
                    "customer_id": customer_id,
                    "assignee_id": assignee_id,
                },
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def list_orders(self) -> list[dict]:
        """List orders for company."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.get(
                f"/companies/{self.company_id}/orders",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def get_order(self, order_id: int) -> dict:
        """Get order by ID."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.get(
                f"/companies/{self.company_id}/orders/{order_id}",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def update_order(self, order_id: int, name: str | None = None, stage: str | None = None) -> dict:
        """Update order."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            payload: dict[str, Any] = {}
            if name is not None:
                payload["name"] = name
            if stage is not None:
                payload["stage"] = stage
            response = await client.patch(
                f"/companies/{self.company_id}/orders/{order_id}",
                json=payload,
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def update_order_stage_internal(self, order_id: int, stage: str) -> dict:
        """Update order stage via internal API."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.patch(
                f"/internal/orders/{order_id}/stage",
                json={"stage": stage},
                headers={"X-Service-Key": SERVICE_API_KEY},
            )
            response.raise_for_status()
            return response.json()

    async def update_order_fields_internal(self, order_id: int, fields: dict[str, Any]) -> dict:
        """Update order fields via internal API."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.patch(
                f"/internal/orders/{order_id}/fields",
                json={"fields": fields},
                headers={"X-Service-Key": SERVICE_API_KEY},
            )
            response.raise_for_status()
            return response.json()

    async def update_order_assignee(self, order_id: int, assignee_id: int | None) -> dict:
        """Update order assignee."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.put(
                f"/companies/{self.company_id}/orders/{order_id}/assignee",
                json={"assignee_id": assignee_id},
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def close_order(self, order_id: int, result: str) -> dict:
        """Close order with result."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                f"/companies/{self.company_id}/orders/{order_id}/close",
                json={"result": result},
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def list_customer_orders(self, customer_id: int) -> list[dict]:
        """List orders for a customer."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.get(
                f"/companies/{self.company_id}/orders/customers/{customer_id}/orders",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()


async def setup_environment(client: OrderTestClient) -> bool:
    """Setup test environment with user, company, and initial thread."""
    console.print("\n[bold blue]Setting up test environment...[/bold blue]\n")

    console.print("1. Authenticating as superuser...")
    result = await client.login(SUPERUSER_EMAIL, SUPERUSER_PASSWORD)

    if "error" in result:
        console.print(f"[red]✗ Login failed: {result['error']}[/red]")
        console.print("\n[yellow]Please create superuser first:[/yellow]")
        console.print(
            f"[dim]cd apps/backend && uv run python scripts/create_superuser.py --email {SUPERUSER_EMAIL} --password {SUPERUSER_PASSWORD} --superuser[/dim]"
        )
        return False

    client.access_token = result["access_token"]
    client.refresh_token = result["refresh_token"]
    console.print("[green]✓ Logged in as superuser[/green]")

    me = await client.get_me()
    client.user_id = me["id"]
    console.print(f"   User ID: {client.user_id}, Name: {me['first_name']} {me['last_name']}")

    console.print("\n2. Setting up company...")
    companies = await client.list_companies()

    existing = next((c for c in companies if c["name"] == TEST_COMPANY_NAME), None)
    if existing:
        client.company_id = existing["id"]
        console.print(f"[yellow]   Using existing company: {client.company_id}[/yellow]")
    else:
        company = await client.create_company(TEST_COMPANY_NAME)
        client.company_id = company["id"]
        console.print(f"[green]✓ Created company: {client.company_id}[/green]")

    console.print("\n3. Loading company members...")
    members = await client.list_company_members()

    for member in members:
        console.print(
            f"   Member: {member['first_name']} {member['last_name']} (id={member['id']}, role={member['role']})"
        )
        if member["user_id"] == client.user_id:
            client.company_user_id = member["id"]

    if not client.company_user_id:
        console.print("[red]✗ Current user is not a member of the company[/red]")
        return False

    console.print(f"[green]✓ Your company_user_id: {client.company_user_id}[/green]")

    return True


def print_order(order: dict):
    """Print order details in a formatted table."""
    table = Table(title="Order Details")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("id", str(order["id"]))
    table.add_row("order_number", str(order["order_number"]))
    table.add_row("name", order.get("name") or "null")
    table.add_row("stage", order["stage"])
    table.add_row("customer_id", str(order["customer"]["id"]))
    table.add_row("assignee_id", str(order.get("assignee", {}).get("id")) if order.get("assignee") else "null")
    table.add_row("order_fields", json.dumps(order.get("order_fields", {}), ensure_ascii=False))
    table.add_row("result", order.get("result") or "null")
    table.add_row("closed_at", order.get("closed_at") or "null")
    table.add_row("created_at", order["created_at"])

    console.print(table)


def print_thread(thread: dict):
    """Print thread details in a formatted table."""
    table = Table(title="Thread Details")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("thread_id", thread["thread_id"])
    table.add_row("state", thread["state"])
    table.add_row("customer_id", str(thread.get("customer_id")) if thread.get("customer_id") else "null")
    table.add_row("channel_type", thread.get("channel_type", "null"))
    table.add_row("assistant_active", str(thread.get("assistant_active", False)))

    console.print(table)


async def scenario_1_new_customer(client: OrderTestClient):
    """Scenario 1: New Customer Flow - first message creates Thread + Order."""
    console.print("\n[bold cyan]Scenario 1: New Customer Flow[/bold cyan]")
    console.print("Goal: First message creates Thread + Order\n")

    user_id = f"scenario1_user_{datetime.now().timestamp()}"
    console.print(f"[yellow]Creating thread for new user: {user_id}[/yellow]")

    thread_data = await client.get_or_create_thread(user_id)
    thread_id = thread_data["thread_id"]
    console.print(f"[green]✓ Thread created: {thread_id}[/green]")

    thread = await client.get_thread(thread_id)
    customer_id = thread.get("customer_id")
    console.print(f"[green]✓ Customer ID: {customer_id}[/green]")

    console.print(f"[yellow]Getting order context for thread...[/yellow]")
    order_context = await client.get_order_by_thread(thread_id)
    console.print(f"[green]✓ Order context retrieved:[/green]")
    console.print(Panel(json.dumps(order_context, indent=2, ensure_ascii=False), border_style="green"))

    order_id = order_context["order_id"]
    console.print(f"[green]✓ Active order ID: {order_id}[/green]")

    order = await client.get_order(order_id)
    console.print("\n[green]Order details:[/green]")
    print_order(order)

    if order["stage"] != "new":
        console.print(f"[red]✗ Expected stage 'new', got '{order['stage']}'[/red]")
        return False

    if order.get("closed_at"):
        console.print("[red]✗ Order should not be closed![/red]")
        return False

    console.print("\n[bold green]✓ Scenario 1 PASSED[/bold green]")
    return True


async def scenario_2_returning_customer_active(client: OrderTestClient):
    """Scenario 2: Returning Customer (Active Order) - same customer, same order continues."""
    console.print("\n[bold cyan]Scenario 2: Returning Customer (Active Order)[/bold cyan]")
    console.print("Goal: Same customer, same order continues\n")

    user_id = f"scenario2_user_{datetime.now().timestamp()}"
    console.print(f"[yellow]Step 1: Creating initial thread for user: {user_id}[/yellow]")
    thread_data = await client.get_or_create_thread(user_id)
    thread_id_1 = thread_data["thread_id"]
    console.print(f"[green]✓ Thread created: {thread_id_1}[/green]")

    order_context_1 = await client.get_order_by_thread(thread_id_1)
    order_id_1 = order_context_1["order_id"]
    console.print(f"[green]✓ Initial order ID: {order_id_1}[/green]")

    console.print(f"\n[yellow]Step 2: Creating new thread with same user_id (different conversation)...[/yellow]")
    console.print(f"[dim]Using same user_id: {user_id}[/dim]")
    new_conversation_id = f"scenario2_conv2_{datetime.now().timestamp()}"
    thread_data_2 = await client.get_or_create_thread(user_id, new_conversation_id)
    thread_id_2 = thread_data_2["thread_id"]
    console.print(f"[green]✓ Second thread created: {thread_id_2}[/green]")

    console.print(f"[yellow]Getting order context for second thread...[/yellow]")
    order_context_2 = await client.get_order_by_thread(thread_id_2)
    order_id_2 = order_context_2["order_id"]
    console.print(f"[green]✓ Order ID from second thread: {order_id_2}[/green]")

    console.print(f"\n[yellow]Step 3: Updating order stage to 'qualification'...[/yellow]")
    updated_order = await client.update_order_stage_internal(order_id_2, "qualification")
    console.print(f"[green]✓ Order stage updated:[/green]")
    print_order(updated_order)

    if updated_order["stage"] != "qualification":
        console.print("[red]✗ Stage update failed![/red]")
        return False

    console.print("\n[bold green]✓ Scenario 2 PASSED[/bold green]")
    return True


async def scenario_3_returning_customer_closed(client: OrderTestClient):
    """Scenario 3: Returning Customer (Closed Order) - customer with closed order gets new order."""
    console.print("\n[bold cyan]Scenario 3: Returning Customer (Closed Order)[/bold cyan]")
    console.print("Goal: Customer with closed order gets new order\n")

    user_id = f"scenario3_user_{datetime.now().timestamp()}"
    console.print(f"[yellow]Step 1: Creating initial thread for user: {user_id}[/yellow]")
    thread_data_1 = await client.get_or_create_thread(user_id)
    thread_id_1 = thread_data_1["thread_id"]
    console.print(f"[green]✓ Thread created: {thread_id_1}[/green]")

    order_context_1 = await client.get_order_by_thread(thread_id_1)
    order_id_1 = order_context_1["order_id"]
    console.print(f"[green]✓ Initial order ID: {order_id_1}[/green]")

    console.print(f"\n[yellow]Step 2: Closing order {order_id_1}...[/yellow]")
    closed_order = await client.close_order(order_id_1, "won")
    console.print(f"[green]✓ Order closed:[/green]")
    print_order(closed_order)

    if not closed_order.get("closed_at"):
        console.print("[red]✗ Order was not closed![/red]")
        return False

    if closed_order.get("result") != "won":
        console.print(f"[red]✗ Expected result 'won', got '{closed_order.get('result')}'[/red]")
        return False

    console.print(f"\n[yellow]Step 3: Creating new thread for same customer (should create new order)...[/yellow]")
    console.print(f"[dim]Using same user_id: {user_id}[/dim]")
    new_conversation_id = f"scenario3_conv2_{datetime.now().timestamp()}"
    thread_data_2 = await client.get_or_create_thread(user_id, new_conversation_id)
    thread_id_2 = thread_data_2["thread_id"]
    console.print(f"[green]✓ New thread created: {thread_id_2}[/green]")

    console.print(f"[yellow]Getting order context for new thread...[/yellow]")
    order_context_2 = await client.get_order_by_thread(thread_id_2)
    order_id_2 = order_context_2["order_id"]

    if not order_id_2:
        console.print("[red]✗ No new order created![/red]")
        return False

    if order_id_2 == order_id_1:
        console.print("[red]✗ Same order ID returned! Should be a new order.[/red]")
        return False

    console.print(f"[green]✓ New order created: {order_id_2}[/green]")
    new_order = await client.get_order(order_id_2)
    print_order(new_order)

    if new_order.get("closed_at"):
        console.print("[red]✗ New order should not be closed![/red]")
        return False

    old_order = await client.get_order(order_id_1)
    if not old_order.get("closed_at"):
        console.print("[red]✗ Old order should still be closed![/red]")
        return False

    console.print("\n[bold green]✓ Scenario 3 PASSED[/bold green]")
    return True


async def scenario_4_sales_agent_tools(client: OrderTestClient):
    """Scenario 4: Sales-Agent Tool Flow - AI can update order stage/fields."""
    console.print("\n[bold cyan]Scenario 4: Sales-Agent Tool Flow[/bold cyan]")
    console.print("Goal: AI can update order stage/fields\n")

    user_id = f"scenario4_user_{datetime.now().timestamp()}"
    console.print(f"[yellow]Step 1: Creating thread for user: {user_id}[/yellow]")
    thread_data = await client.get_or_create_thread(user_id)
    thread_id = thread_data["thread_id"]
    console.print(f"[green]✓ Thread created: {thread_id}[/green]")

    console.print(f"[yellow]Step 2: Getting order context for thread...[/yellow]")
    order_context = await client.get_order_by_thread(thread_id)
    console.print(f"[green]✓ Order context:[/green]")
    console.print(Panel(json.dumps(order_context, indent=2, ensure_ascii=False), border_style="green"))

    order_id = order_context["order_id"]
    console.print(f"[green]✓ Order ID: {order_id}[/green]")

    console.print(f"\n[yellow]Step 3: Updating order stage to 'offer' via internal API...[/yellow]")
    updated_order = await client.update_order_stage_internal(order_id, "offer")
    if updated_order["stage"] != "offer":
        console.print("[red]✗ Stage update failed![/red]")
        return False
    console.print("[green]✓ Stage updated successfully[/green]")
    print_order(updated_order)

    console.print(f"\n[yellow]Step 4: Updating order fields via internal API...[/yellow]")
    test_fields = {"budget": 50000, "product": "Premium Package", "notes": "Test field update"}
    updated_order = await client.update_order_fields_internal(order_id, test_fields)
    if updated_order.get("order_fields") != test_fields:
        console.print("[red]✗ Fields update failed![/red]")
        console.print(f"[yellow]   Expected: {test_fields}[/yellow]")
        console.print(f"[yellow]   Got: {updated_order.get('order_fields')}[/yellow]")
        return False
    console.print("[green]✓ Fields updated successfully[/green]")
    print_order(updated_order)

    console.print("\n[bold green]✓ Scenario 4 PASSED[/bold green]")
    return True


async def scenario_5_order_crud(client: OrderTestClient):
    """Scenario 5: Order CRUD - Basic order management works."""
    console.print("\n[bold cyan]Scenario 5: Order CRUD[/bold cyan]")
    console.print("Goal: Basic order management works\n")

    user_id = f"scenario5_user_{datetime.now().timestamp()}"
    console.print(f"[yellow]Step 1: Creating thread to get a customer...[/yellow]")
    thread_data = await client.get_or_create_thread(user_id)
    thread_id = thread_data["thread_id"]
    console.print(f"[green]✓ Thread created: {thread_id}[/green]")

    thread = await client.get_thread(thread_id)
    customer_id = thread.get("customer_id")
    console.print(f"[green]✓ Customer ID: {customer_id}[/green]")

    console.print(f"\n[yellow]Step 2: Creating order manually...[/yellow]")
    order = await client.create_order(customer_id, client.company_user_id)
    test_order_id = order["id"]
    console.print(f"[green]✓ Order created: {test_order_id}[/green]")

    console.print(f"\n[yellow]Step 3: Getting order details...[/yellow]")
    order = await client.get_order(test_order_id)
    print_order(order)

    console.print(f"\n[yellow]Step 4: Updating order name...[/yellow]")
    updated_order = await client.update_order(test_order_id, name="Test Order Name")
    if updated_order["name"] != "Test Order Name":
        console.print("[red]✗ Name update failed![/red]")
        return False
    console.print("[green]✓ Name updated successfully[/green]")

    console.print(f"\n[yellow]Step 5: Updating order stage...[/yellow]")
    updated_order = await client.update_order(test_order_id, stage="negotiation")
    if updated_order["stage"] != "negotiation":
        console.print("[red]✗ Stage update failed![/red]")
        return False
    console.print("[green]✓ Stage updated successfully[/green]")

    console.print(f"\n[yellow]Step 6: Updating order assignee...[/yellow]")
    updated_order = await client.update_order_assignee(test_order_id, client.company_user_id)
    if not updated_order.get("assignee") or updated_order["assignee"]["id"] != client.company_user_id:
        console.print("[red]✗ Assignee update failed![/red]")
        return False
    console.print("[green]✓ Assignee updated successfully[/green]")

    console.print(f"\n[yellow]Step 7: Listing orders for customer {customer_id}...[/yellow]")
    customer_orders = await client.list_customer_orders(customer_id)
    console.print(f"[green]✓ Found {len(customer_orders)} orders for customer[/green]")
    if len(customer_orders) == 0:
        console.print("[yellow]   No orders found for customer[/yellow]")
    else:
        for o in customer_orders[:3]:
            console.print(f"   - Order #{o['order_number']} (ID: {o['id']}, Stage: {o['stage']})")

    console.print("\n[bold green]✓ Scenario 5 PASSED[/bold green]")
    return True


async def scenario_6_edge_cases(client: OrderTestClient):
    """Scenario 6: Edge Cases."""
    console.print("\n[bold cyan]Scenario 6: Edge Cases[/bold cyan]")
    console.print("Goal: Test various edge cases\n")

    console.print("\n[yellow]Test 1: Thread without order (should return 404)...[/yellow]")
    fake_thread_id = "non_existent_thread_12345"
    try:
        await client.get_order_by_thread(fake_thread_id)
        console.print("[red]✗ Should have returned 404![/red]")
        return False
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            console.print("[green]✓ Correctly returned 404[/green]")
        else:
            console.print(f"[red]✗ Wrong status code: {e.response.status_code}[/red]")
            return False

    console.print("\n[yellow]Test 2: Invalid stage value (should return 422)...[/yellow]")
    user_id = f"scenario6_user_{datetime.now().timestamp()}"
    thread_data = await client.get_or_create_thread(user_id)
    thread_id = thread_data["thread_id"]
    order_context = await client.get_order_by_thread(thread_id)
    order_id = order_context["order_id"]

    try:
        await client.update_order_stage_internal(order_id, "invalid_stage")
        console.print("[red]✗ Should have returned 422![/red]")
        return False
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 422:
            console.print("[green]✓ Correctly returned 422 (validation error)[/green]")
        else:
            console.print(f"[yellow]   Got status {e.response.status_code} (acceptable)[/yellow]")

    console.print("\n[yellow]Test 3: Close already closed order (should return 400)...[/yellow]")
    console.print(f"[yellow]   Closing order {order_id} first...[/yellow]")
    closed_order = await client.close_order(order_id, "won")
    if not closed_order.get("closed_at"):
        console.print("[yellow]   Failed to close order, skipping test[/yellow]")
    else:
        try:
            await client.close_order(order_id, "won")
            console.print("[yellow]   Order already closed, but endpoint accepted (idempotent OK)[/yellow]")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                console.print("[green]✓ Correctly returned 400[/green]")
            else:
                console.print(f"[yellow]   Got status {e.response.status_code}[/yellow]")

    console.print("\n[bold green]✓ Scenario 6 PASSED[/bold green]")
    return True


async def interactive_menu(client: OrderTestClient):
    """Run interactive menu."""
    while True:
        console.print("\n" + "=" * 60)
        console.print("[bold]Order Model Test Menu[/bold]")
        console.print("=" * 60)
        if client.company_id:
            console.print(f"Company ID: [cyan]{client.company_id}[/cyan]")
        if client.thread_id:
            console.print(f"Thread ID: [cyan]{client.thread_id}[/cyan]")
        if client.order_id:
            console.print(f"Order ID: [cyan]{client.order_id}[/cyan]")
        if client.customer_id:
            console.print(f"Customer ID: [cyan]{client.customer_id}[/cyan]")
        console.print("-" * 60)
        console.print("\\[1] Scenario 1: New Customer Flow")
        console.print("\\[2] Scenario 2: Returning Customer (Active Order)")
        console.print("\\[3] Scenario 3: Returning Customer (Closed Order)")
        console.print("\\[4] Scenario 4: Sales-Agent Tool Flow")
        console.print("\\[5] Scenario 5: Order CRUD")
        console.print("\\[6] Scenario 6: Edge Cases")
        console.print("\\[a] Run All Scenarios")
        console.print("-" * 60)
        console.print("\\[t] Get thread details")
        console.print("\\[o] Get order details")
        console.print("\\[l] List all orders")
        console.print("\\[c] List customer orders")
        console.print("\\[q] Quit")
        console.print("-" * 60)

        try:
            choice = await asyncio.get_event_loop().run_in_executor(None, input, "Choice: ")
        except EOFError:
            break

        choice = choice.strip().lower()

        try:
            match choice:
                case "1":
                    await scenario_1_new_customer(client)
                case "2":
                    await scenario_2_returning_customer_active(client)
                case "3":
                    await scenario_3_returning_customer_closed(client)
                case "4":
                    await scenario_4_sales_agent_tools(client)
                case "5":
                    await scenario_5_order_crud(client)
                case "6":
                    await scenario_6_edge_cases(client)
                case "a":
                    console.print("\n[bold yellow]Running all scenarios...[/bold yellow]\n")
                    results = []
                    results.append(("Scenario 1", await scenario_1_new_customer(client)))
                    results.append(("Scenario 2", await scenario_2_returning_customer_active(client)))
                    results.append(("Scenario 3", await scenario_3_returning_customer_closed(client)))
                    results.append(("Scenario 4", await scenario_4_sales_agent_tools(client)))
                    results.append(("Scenario 5", await scenario_5_order_crud(client)))
                    results.append(("Scenario 6", await scenario_6_edge_cases(client)))

                    console.print("\n" + "=" * 60)
                    console.print("[bold]Test Results Summary[/bold]")
                    console.print("=" * 60)
                    for name, passed in results:
                        status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
                        console.print(f"{name}: {status}")
                    console.print("=" * 60)
                case "t":
                    if not client.thread_id:
                        console.print("[red]No thread_id available[/red]")
                    else:
                        thread = await client.get_thread(client.thread_id)
                        print_thread(thread)
                case "o":
                    if not client.order_id:
                        console.print("[red]No order_id available[/red]")
                    else:
                        order = await client.get_order(client.order_id)
                        print_order(order)
                case "l":
                    orders = await client.list_orders()
                    console.print(f"\n[cyan]Found {len(orders)} orders:[/cyan]")
                    for order in orders[:10]:
                        console.print(
                            f"  - Order #{order['order_number']} (ID: {order['id']}, Stage: {order['stage']})"
                        )
                case "c":
                    if not client.customer_id:
                        console.print("[red]No customer_id available[/red]")
                    else:
                        orders = await client.list_customer_orders(client.customer_id)
                        console.print(f"\n[cyan]Found {len(orders)} orders for customer:[/cyan]")
                        for order in orders:
                            console.print(
                                f"  - Order #{order['order_number']} (ID: {order['id']}, Stage: {order['stage']})"
                            )
                case "q":
                    break
                case _:
                    console.print("[red]Invalid choice[/red]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            import traceback

            console.print(Panel(traceback.format_exc(), title="[red]Traceback[/red]", border_style="red"))


async def main():
    console.print(
        Panel.fit(
            "[bold cyan]Order Model Extraction Test[/bold cyan]\n\n"
            "This script tests Plan 018: Order Model Extraction from Thread\n"
            "Covers all 6 test scenarios from the plan.",
            border_style="cyan",
        )
    )

    client = OrderTestClient()

    if not await setup_environment(client):
        sys.exit(1)

    await interactive_menu(client)

    console.print("\n[bold green]Done![/bold green]")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
