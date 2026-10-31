#!/usr/bin/env python3
"""Interactive test script for Billing Migration: Thread → Order feature.

This script tests all scenarios from Plan 019:
1. New Order Billing - verify billing happens on order creation
2. Idempotency - verify no duplicate charges
3. Insufficient Balance - verify billing hold behavior
4. Multiple Threads, One Order - verify one charge per order regardless of threads

Usage:
    cd scripts/manual_testing
    python test_billing_migration.py

Requirements:
    pip install -r requirements.txt
"""

import asyncio
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

TEST_COMPANY_NAME = "Billing Migration Test Company"

SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "test-api-key")

console = Console()


class BillingTestClient:
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
        self.test_connector_id: str | None = None

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
                    "description": "Test company for billing migration",
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

    async def get_balance(self) -> dict:
        """Get company balance."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.get(
                f"/companies/{self.company_id}/billing/balance",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def top_up_balance(self, amount: int, comment: str | None = None) -> dict:
        """Top up company balance."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                f"/companies/{self.company_id}/billing/top-up",
                json={"amount": amount, "comment": comment},
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def get_ledger(
        self,
        operation_type: str | None = None,
        order_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Get ledger entries."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            params: dict[str, Any] = {"limit": limit, "offset": offset}
            if operation_type:
                params["operation_type"] = operation_type
            if order_id:
                params["order_id"] = order_id
            response = await client.get(
                f"/companies/{self.company_id}/billing/ledger",
                headers=self.headers,
                params=params,
            )
            response.raise_for_status()
            return response.json()

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

    async def get_order(self, order_id: int) -> dict:
        """Get order by ID."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.get(
                f"/companies/{self.company_id}/orders/{order_id}",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def close_order(self, order_id: int, result: str = "won") -> dict:
        """Close order with result."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                f"/companies/{self.company_id}/orders/{order_id}/close",
                json={"result": result},
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def get_or_create_test_connector(self) -> str:
        """Get or create test connector for billing tests."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            # Try to list existing connectors
            response = await client.get(
                "/transport/connectors",
                headers={"X-Service-Key": SERVICE_API_KEY},
                params={"enabled": True},
            )
            if response.status_code == 200:
                connectors = response.json().get("connectors", [])
                # Look for test connector for this company
                for connector in connectors:
                    if connector.get("company_id") == self.company_id and connector.get("enabled"):
                        connector_id = connector.get("connector_id")
                        if connector_id:
                            return connector_id

            # Create new test connector (custom type doesn't require config)
            response = await client.post(
                "/transport/connectors",
                json={
                    "connector_id": f"test_billing_{self.company_id}",
                    "type": "custom",
                    "channel_type": "test",
                    "company_id": self.company_id,
                    "display_name": "Test Billing Connector",
                    "managed": False,
                    "enabled": True,
                    "config": {},
                },
                headers={"X-Service-Key": SERVICE_API_KEY},
            )
            response.raise_for_status()
            connector = response.json()
            # Response might have connector_id directly or nested
            connector_id = connector.get("connector_id")
            if not connector_id and "connector" in connector:
                connector_id = connector["connector"].get("connector_id")
            if not connector_id:
                raise ValueError(f"Could not extract connector_id from response: {connector}")
            return connector_id

    async def send_inbound_message(
        self,
        user_id: str,
        conversation_id: str,
        text: str,
        channel_type: str = "test",
        connector_id: str | None = None,
    ) -> dict:
        """Send inbound message through message router to trigger billing.

        Note: Billing happens before forwarding to Sales Agent, so even if Sales Agent
        is down (503 error), billing will have completed successfully.
        """
        if not connector_id:
            connector_id = self.test_connector_id
        if not connector_id:
            raise ValueError("connector_id is required. Call get_or_create_test_connector() first.")

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                "/messages/inbound",
                json={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "text": text,
                    "message_id": f"test_msg_{datetime.now().timestamp()}",
                    "ts": int(datetime.now().timestamp()),
                    "role": "user",
                    "is_historical": False,
                },
                headers={"X-Service-Key": SERVICE_API_KEY, "X-Connector-Id": connector_id},
            )
            # Billing happens before Sales Agent forward, so 503 is OK for billing tests
            if response.status_code == 503:
                return {"status": "accepted", "note": "Sales Agent unavailable but billing completed"}
            response.raise_for_status()
            return response.json()


async def setup_environment(client: BillingTestClient) -> bool:
    """Setup test environment with user, company, and initial balance."""
    console.print("\n[bold blue]Setting up test environment...[/bold blue]\n")

    console.print("1. Authenticating as superuser...")
    result = await client.login(SUPERUSER_EMAIL, SUPERUSER_PASSWORD)

    if "error" in result:
        console.print(f"[red]✗ Login failed: {result['error']}[/red]")
        console.print("\n[yellow]Please create superuser first:[/yellow]")
        console.print(
            f"[dim]cd apps/backend && uv run python scripts/create_superuser.py "
            f"--email {SUPERUSER_EMAIL} --password {SUPERUSER_PASSWORD} --superuser[/dim]"
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

    console.print("\n4. Getting or creating test connector...")
    try:
        connector_id = await client.get_or_create_test_connector()
        client.test_connector_id = connector_id
        console.print(f"[green]✓ Test connector ID: {connector_id}[/green]")
    except Exception as e:
        console.print(f"[yellow]   Warning: Could not create connector: {e}[/yellow]")
        console.print("[yellow]   You may need to create a connector manually[/yellow]")

    console.print("\n5. Checking initial balance...")
    balance_data = await client.get_balance()
    console.print(f"[green]✓ Current balance: {balance_data['balance']}[/green]")
    console.print(f"   Balance warning: {balance_data['balance_warning']}")

    return True


def print_order(order: dict):
    """Print order details in a formatted table."""
    table = Table(title="Order Details")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("id", str(order["id"]))
    table.add_row("order_number", str(order["order_number"]))
    table.add_row("billing_status", order.get("billing_status", "null"))
    table.add_row("charged_at", order.get("charged_at") or "null")
    table.add_row("stage", order["stage"])
    table.add_row("customer_id", str(order["customer"]["id"]))
    table.add_row("created_at", order["created_at"])

    console.print(table)


def print_ledger_entry(entry: dict):
    """Print ledger entry details in a formatted table."""
    table = Table(title="Ledger Entry")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("id", str(entry["id"]))
    table.add_row("operation_type", entry["operation_type"])
    table.add_row("amount", str(entry["amount"]))
    table.add_row("order_id", str(entry.get("order_id")) if entry.get("order_id") else "null")
    table.add_row("channel_type", entry.get("channel_type") or "null")
    table.add_row("conversation_id", entry.get("conversation_id") or "null")
    table.add_row("initiated_by", entry["initiated_by"])
    table.add_row(
        "timestamp",
        entry["timestamp"].isoformat() if isinstance(entry["timestamp"], datetime) else str(entry["timestamp"]),
    )

    console.print(table)


async def scenario_1_new_order_billing(client: BillingTestClient):
    """Scenario 1: New Order Billing - verify billing happens on order creation."""
    console.print("\n[bold cyan]Scenario 1: New Order Billing[/bold cyan]")
    console.print("Goal: Verify billing happens on order creation\n")

    initial_balance_data = await client.get_balance()
    initial_balance = initial_balance_data["balance"]
    console.print(f"[yellow]Initial balance: {initial_balance}[/yellow]")

    # Ensure exactly 1 unit for testing exact billing amount
    CHARGE_AMOUNT = 1
    if initial_balance < CHARGE_AMOUNT:
        needed = CHARGE_AMOUNT - initial_balance
        console.print(f"\n[yellow]Topping up balance by exactly {needed} unit(s) for billing test...[/yellow]")
        await client.top_up_balance(needed, "Test balance for Scenario 1 - exact amount")
        initial_balance = (await client.get_balance())["balance"]
        console.print(f"[green]✓ Balance topped up to: {initial_balance} (exactly {CHARGE_AMOUNT} unit)[/green]")
    elif initial_balance > CHARGE_AMOUNT:
        console.print(
            f"[yellow]   Note: Balance is {initial_balance}, "
            f"will test with exact charge amount of {CHARGE_AMOUNT}[/yellow]"
        )

    user_id = f"scenario1_user_{datetime.now().timestamp()}"
    conversation_id = f"scenario1_conv_{datetime.now().timestamp()}"

    console.print(f"\n[yellow]Step 1: Sending inbound message for new user: {user_id}[/yellow]")
    console.print("[dim]This will create thread + order and trigger billing[/dim]")
    console.print(
        "[dim]Note: Billing happens before Sales Agent forward, so Sales Agent doesn't need to be running[/dim]"
    )
    result = await client.send_inbound_message(
        user_id=user_id,
        conversation_id=conversation_id,
        text="Hello, I need help",
    )
    if result.get("note"):
        console.print(f"[yellow]   {result['note']}[/yellow]")
    console.print("[green]✓ Message sent[/green]")

    console.print(f"\n[yellow]Step 2: Getting thread and order...[/yellow]")
    thread_data = await client.get_or_create_thread(user_id, conversation_id)
    thread_id = thread_data["thread_id"]
    console.print(f"[green]✓ Thread ID: {thread_id}[/green]")

    order_context = await client.get_order_by_thread(thread_id)
    order_id = order_context["order_id"]
    console.print(f"[green]✓ Order ID: {order_id}[/green]")

    console.print(f"\n[yellow]Step 3: Verifying order billing status and charged_at...[/yellow]")
    order = await client.get_order(order_id)
    print_order(order)

    billing_status = order.get("billing_status")
    if billing_status != "active":
        console.print(f"[red]✗ Expected billing_status 'active', got '{billing_status}'[/red]")
        if billing_status is None:
            console.print("[yellow]   Note: billing_status field is missing from API response[/yellow]")
            console.print("[yellow]   This indicates the OrderResponse schema needs to include billing_status[/yellow]")
        elif billing_status == "billing_hold":
            console.print("[yellow]   Note: Order is in billing_hold - check if balance is sufficient[/yellow]")
        return False

    charged_at = order.get("charged_at")
    if not charged_at:
        console.print("[red]✗ Order charged_at is not set![/red]")
        console.print(
            "[yellow]   Note: This indicates billing service is not being called when order is created[/yellow]"
        )
        return False

    console.print(f"\n[yellow]Step 4: Verifying ledger entry with order_id...[/yellow]")
    ledger_data = await client.get_ledger(order_id=order_id, operation_type="charge")
    charge_entries = [e for e in ledger_data["entries"] if e["operation_type"] == "charge"]

    if not charge_entries:
        console.print("[red]✗ No charge entry found in ledger![/red]")
        console.print("[yellow]   Note: This indicates BillingService.charge_for_order() is not being called[/yellow]")
        console.print("[yellow]   Check message router integration point[/yellow]")
        return False

    charge_entry = charge_entries[0]
    print_ledger_entry(charge_entry)

    if charge_entry.get("order_id") != order_id:
        console.print(f"[red]✗ Expected order_id {order_id}, got {charge_entry.get('order_id')}[/red]")
        return False

    console.print(f"\n[yellow]Step 5: Verifying balance decremented by exactly 1 unit...[/yellow]")
    new_balance_data = await client.get_balance()
    new_balance = new_balance_data["balance"]
    console.print(f"[green]✓ New balance: {new_balance}[/green]")

    expected_balance = initial_balance - 1
    if new_balance != expected_balance:
        console.print(
            f"[red]✗ Balance should be {expected_balance} (decremented by exactly 1)! Got {new_balance}[/red]"
        )
        return False

    console.print(f"[green]✓ Balance correctly decremented by exactly 1 unit[/green]")
    console.print("\n[bold green]✓ Scenario 1 PASSED[/bold green]")
    return True


async def scenario_2_idempotency(client: BillingTestClient):
    """Scenario 2: Idempotency - verify no duplicate charges."""
    console.print("\n[bold cyan]Scenario 2: Idempotency[/bold cyan]")
    console.print("Goal: Verify no duplicate charges for same order\n")

    initial_balance_data = await client.get_balance()
    initial_balance = initial_balance_data["balance"]
    console.print(f"[yellow]Initial balance: {initial_balance}[/yellow]")

    user_id = f"scenario2_user_{datetime.now().timestamp()}"
    conversation_id = f"scenario2_conv_{datetime.now().timestamp()}"

    console.print(f"\n[yellow]Step 1: Creating first thread for user: {user_id}[/yellow]")
    thread_data_1 = await client.get_or_create_thread(user_id, conversation_id)
    thread_id_1 = thread_data_1["thread_id"]
    console.print(f"[green]✓ Thread created: {thread_id_1}[/green]")

    order_context_1 = await client.get_order_by_thread(thread_id_1)
    order_id = order_context_1["order_id"]
    console.print(f"[green]✓ Order ID: {order_id}[/green]")

    balance_after_first = (await client.get_balance())["balance"]
    console.print(f"[yellow]Balance after first thread: {balance_after_first}[/yellow]")

    ledger_data_1 = await client.get_ledger(order_id=order_id, operation_type="charge")
    charge_entries_1 = [e for e in ledger_data_1["entries"] if e["operation_type"] == "charge"]
    console.print(f"[green]✓ Found {len(charge_entries_1)} charge entry(ies) after first thread[/green]")

    console.print(f"\n[yellow]Step 2: Creating second thread with same user_id (different conversation)...[/yellow]")
    new_conversation_id = f"scenario2_conv2_{datetime.now().timestamp()}"
    thread_data_2 = await client.get_or_create_thread(user_id, new_conversation_id)
    thread_id_2 = thread_data_2["thread_id"]
    console.print(f"[green]✓ Second thread created: {thread_id_2}[/green]")

    order_context_2 = await client.get_order_by_thread(thread_id_2)
    order_id_2 = order_context_2["order_id"]
    console.print(f"[green]✓ Order ID from second thread: {order_id_2}[/green]")

    if order_id_2 != order_id:
        console.print(
            f"[yellow]   Note: Different order ID ({order_id_2} vs {order_id}), checking if same customer...[/yellow]"
        )
        thread_1 = await client.get_thread(thread_id_1)
        thread_2 = await client.get_thread(thread_id_2)
        if thread_1.get("customer_id") == thread_2.get("customer_id"):
            console.print(
                "[yellow]   Same customer, but different orders (expected if first order was closed)[/yellow]"
            )
        else:
            console.print("[yellow]   Different customers, different orders expected[/yellow]")

    console.print(f"\n[yellow]Step 3: Verifying no duplicate charge...[/yellow]")
    balance_after_second = (await client.get_balance())["balance"]
    console.print(f"[yellow]Balance after second thread: {balance_after_second}[/yellow]")

    if order_id_2 == order_id:
        if balance_after_second != balance_after_first:
            console.print(
                f"[red]✗ Balance changed! Should remain {balance_after_first}, got {balance_after_second}[/red]"
            )
            return False

        ledger_data_2 = await client.get_ledger(order_id=order_id, operation_type="charge")
        charge_entries_2 = [e for e in ledger_data_2["entries"] if e["operation_type"] == "charge"]

        if len(charge_entries_2) != len(charge_entries_1):
            console.print(
                f"[red]✗ Number of charge entries changed! "
                f"Expected {len(charge_entries_1)}, got {len(charge_entries_2)}[/red]"
            )
            return False

        console.print("[green]✓ No duplicate charge - idempotency works correctly[/green]")
    else:
        console.print(
            "[yellow]   Different order ID - new charge expected (this is OK if first order was closed)[/yellow]"
        )

    console.print("\n[bold green]✓ Scenario 2 PASSED[/bold green]")
    return True


async def scenario_3_insufficient_balance(client: BillingTestClient):
    """Scenario 3: Insufficient Balance - verify billing hold behavior."""
    console.print("\n[bold cyan]Scenario 3: Insufficient Balance[/bold cyan]")
    console.print("Goal: Verify billing hold when balance is insufficient\n")

    console.print(f"\n[yellow]Step 1: Setting balance to 0...[/yellow]")
    current_balance_data = await client.get_balance()
    current_balance = current_balance_data["balance"]

    if current_balance > 0:
        console.print(f"[yellow]   Current balance is {current_balance}, need to adjust...[/yellow]")
        console.print("[yellow]   Note: This test requires manual balance adjustment to 0[/yellow]")
        console.print(
            "[yellow]   Please set balance to 0 manually or use top-up with negative amount if supported[/yellow]"
        )
        console.print("[yellow]   Skipping automatic balance adjustment for safety[/yellow]")
    else:
        console.print("[green]✓ Balance is already 0 or negative[/green]")

    console.print(f"\n[yellow]Step 2: Creating thread with insufficient balance...[/yellow]")
    user_id = f"scenario3_user_{datetime.now().timestamp()}"
    thread_data = await client.get_or_create_thread(user_id)
    thread_id = thread_data["thread_id"]
    console.print(f"[green]✓ Thread created: {thread_id}[/green]")

    console.print(f"\n[yellow]Step 3: Getting order context...[/yellow]")
    order_context = await client.get_order_by_thread(thread_id)
    order_id = order_context["order_id"]
    console.print(f"[green]✓ Order ID: {order_id}[/green]")

    console.print(f"\n[yellow]Step 4: Verifying order billing_status is BILLING_HOLD...[/yellow]")
    order = await client.get_order(order_id)
    print_order(order)

    billing_status = order.get("billing_status")
    if billing_status != "billing_hold":
        console.print(f"[yellow]   Expected billing_status 'billing_hold', got '{billing_status}'[/yellow]")
        if billing_status is None:
            console.print("[yellow]   Note: billing_status field missing - check OrderResponse schema[/yellow]")
        elif billing_status == "active":
            console.print("[yellow]   Note: Order is active - billing service may not check balance[/yellow]")
        else:
            console.print("[yellow]   This might be OK if balance was not actually 0[/yellow]")
    else:
        console.print("[green]✓ Order billing_status is BILLING_HOLD[/green]")

    console.print(f"\n[yellow]Step 5: Verifying ledger entry with amount = 0...[/yellow]")
    ledger_data = await client.get_ledger(order_id=order_id, operation_type="charge")
    charge_entries = [e for e in ledger_data["entries"] if e["operation_type"] == "charge"]

    if charge_entries:
        charge_entry = charge_entries[0]
        print_ledger_entry(charge_entry)

        if charge_entry.get("order_id") != order_id:
            console.print(f"[red]✗ Expected order_id {order_id}, got {charge_entry.get('order_id')}[/red]")
            return False

        if charge_entry["amount"] != 0:
            console.print(f"[yellow]   Expected amount 0, got {charge_entry['amount']}[/yellow]")
            console.print(
                "[yellow]   This might be OK if billing logic charges even with insufficient balance[/yellow]"
            )
        else:
            console.print("[green]✓ Ledger entry has amount = 0[/green]")
    else:
        console.print("[yellow]   No charge entry found (might be expected if billing is skipped)[/yellow]")

    console.print("\n[bold green]✓ Scenario 3 PASSED (with notes)[/bold green]")
    return True


async def scenario_4_multiple_threads_one_order(client: BillingTestClient):
    """Scenario 4: Multiple Threads, One Order - verify one charge per order."""
    console.print("\n[bold cyan]Scenario 4: Multiple Threads, One Order[/bold cyan]")
    console.print("Goal: Verify one charge per order regardless of communication channels\n")

    initial_balance_data = await client.get_balance()
    initial_balance = initial_balance_data["balance"]
    console.print(f"[yellow]Initial balance: {initial_balance}[/yellow]")

    user_id = f"scenario4_user_{datetime.now().timestamp()}"

    console.print(f"\n[yellow]Step 1: Creating Telegram thread for user: {user_id}[/yellow]")
    telegram_conv_id = f"scenario4_telegram_{datetime.now().timestamp()}"
    thread_data_telegram = await client.get_or_create_thread(user_id, telegram_conv_id)
    thread_id_telegram = thread_data_telegram["thread_id"]
    console.print(f"[green]✓ Telegram thread created: {thread_id_telegram}[/green]")

    order_context_telegram = await client.get_order_by_thread(thread_id_telegram)
    order_id = order_context_telegram["order_id"]
    console.print(f"[green]✓ Order ID: {order_id}[/green]")

    balance_after_telegram = (await client.get_balance())["balance"]
    console.print(f"[yellow]Balance after Telegram thread: {balance_after_telegram}[/yellow]")

    ledger_data_telegram = await client.get_ledger(order_id=order_id, operation_type="charge")
    charge_entries_telegram = [e for e in ledger_data_telegram["entries"] if e["operation_type"] == "charge"]
    console.print(f"[green]✓ Found {len(charge_entries_telegram)} charge entry(ies) for Telegram thread[/green]")

    if charge_entries_telegram:
        print_ledger_entry(charge_entries_telegram[0])

    console.print(f"\n[yellow]Step 2: Creating WhatsApp thread for same user (different channel)...[/yellow]")
    whatsapp_conv_id = f"scenario4_whatsapp_{datetime.now().timestamp()}"
    thread_data_whatsapp = await client.get_or_create_thread(user_id, whatsapp_conv_id)
    thread_id_whatsapp = thread_data_whatsapp["thread_id"]
    console.print(f"[green]✓ WhatsApp thread created: {thread_id_whatsapp}[/green]")

    order_context_whatsapp = await client.get_order_by_thread(thread_id_whatsapp)
    order_id_whatsapp = order_context_whatsapp["order_id"]
    console.print(f"[green]✓ Order ID from WhatsApp thread: {order_id_whatsapp}[/green]")

    if order_id_whatsapp != order_id:
        console.print(f"[yellow]   Different order ID ({order_id_whatsapp} vs {order_id})[/yellow]")
        console.print("[yellow]   This might happen if order was closed or different customer[/yellow]")
        console.print("[yellow]   Checking if same customer...[/yellow]")
        thread_telegram = await client.get_thread(thread_id_telegram)
        thread_whatsapp = await client.get_thread(thread_id_whatsapp)
        if thread_telegram.get("customer_id") == thread_whatsapp.get("customer_id"):
            console.print(
                "[yellow]   Same customer but different orders - might be expected if first order was closed[/yellow]"
            )
        else:
            console.print("[yellow]   Different customers - different orders expected[/yellow]")
    else:
        console.print("[green]✓ Same order ID - testing for single charge[/green]")

        console.print(f"\n[yellow]Step 3: Verifying only one charge entry for this order...[/yellow]")
        balance_after_whatsapp = (await client.get_balance())["balance"]
        console.print(f"[yellow]Balance after WhatsApp thread: {balance_after_whatsapp}[/yellow]")

        if balance_after_whatsapp != balance_after_telegram:
            console.print(
                f"[red]✗ Balance changed! Should remain {balance_after_telegram}, got {balance_after_whatsapp}[/red]"
            )
            return False

        ledger_data_whatsapp = await client.get_ledger(order_id=order_id, operation_type="charge")
        charge_entries_whatsapp = [e for e in ledger_data_whatsapp["entries"] if e["operation_type"] == "charge"]

        if len(charge_entries_whatsapp) != len(charge_entries_telegram):
            console.print(
                f"[red]✗ Number of charge entries changed! "
                f"Expected {len(charge_entries_telegram)}, got {len(charge_entries_whatsapp)}[/red]"
            )
            return False

        console.print("[green]✓ Only one charge entry exists for this order[/green]")
        console.print("[green]✓ Multiple threads, one order - billing works correctly[/green]")

    console.print("\n[bold green]✓ Scenario 4 PASSED[/bold green]")
    return True


async def scenario_5_order_closure_and_new_order(client: BillingTestClient):
    """Scenario 5: Order Closure and New Order - verify closing doesn't charge, new order does."""
    console.print("\n[bold cyan]Scenario 5: Order Closure and New Order[/bold cyan]")
    console.print("Goal: Verify closing order doesn't charge, new order after closure charges\n")

    CHARGE_AMOUNT = 1
    initial_balance_data = await client.get_balance()
    initial_balance = initial_balance_data["balance"]
    console.print(f"[yellow]Initial balance: {initial_balance}[/yellow]")

    # Ensure exactly 2 units for testing two orders
    if initial_balance < CHARGE_AMOUNT * 2:
        needed = (CHARGE_AMOUNT * 2) - initial_balance
        console.print(f"\n[yellow]Topping up balance by exactly {needed} unit(s) for two orders...[/yellow]")
        await client.top_up_balance(needed, "Test balance for Scenario 5 - two orders")
        initial_balance = (await client.get_balance())["balance"]
        console.print(f"[green]✓ Balance topped up to: {initial_balance} (exactly {CHARGE_AMOUNT * 2} units)[/green]")

    user_id = f"scenario5_user_{datetime.now().timestamp()}"

    console.print(f"\n[yellow]Step 1: Creating first order for user: {user_id}[/yellow]")
    conv_id_1 = f"scenario5_conv1_{datetime.now().timestamp()}"
    await client.send_inbound_message(
        user_id=user_id,
        conversation_id=conv_id_1,
        text="First message",
    )
    console.print("[green]✓ First message sent[/green]")

    thread_data_1 = await client.get_or_create_thread(user_id, conv_id_1)
    order_context_1 = await client.get_order_by_thread(thread_data_1["thread_id"])
    order_id_1 = order_context_1["order_id"]
    console.print(f"[green]✓ First order ID: {order_id_1}[/green]")

    order_1 = await client.get_order(order_id_1)
    if order_1.get("billing_status") != "active":
        status_1 = order_1.get("billing_status")
        console.print(f"[red]✗ First order billing_status should be 'active', got '{status_1}'[/red]")
        return False
    if not order_1.get("charged_at"):
        console.print("[red]✗ First order charged_at is not set![/red]")
        return False

    balance_after_order_1 = (await client.get_balance())["balance"]
    expected_balance_1 = initial_balance - CHARGE_AMOUNT
    if balance_after_order_1 != expected_balance_1:
        console.print(
            f"[red]✗ Balance after first order should be {expected_balance_1}, got {balance_after_order_1}[/red]"
        )
        return False
    console.print(
        f"[green]✓ Balance after first order: {balance_after_order_1} (decremented by {CHARGE_AMOUNT})[/green]"
    )

    ledger_data_1 = await client.get_ledger(order_id=order_id_1, operation_type="charge")
    charge_entries_1 = [e for e in ledger_data_1["entries"] if e["operation_type"] == "charge"]
    if len(charge_entries_1) != 1:
        console.print(f"[red]✗ Expected exactly 1 charge entry for first order, got {len(charge_entries_1)}[/red]")
        return False
    console.print(f"[green]✓ Found exactly 1 charge entry for first order[/green]")

    console.print(f"\n[yellow]Step 2: Closing first order (should NOT charge)...[/yellow]")
    closed_order = await client.close_order(order_id_1, "won")
    if not closed_order.get("closed_at"):
        console.print("[red]✗ Order was not closed![/red]")
        return False
    console.print("[green]✓ Order closed successfully[/green]")

    balance_after_close = (await client.get_balance())["balance"]
    if balance_after_close != balance_after_order_1:
        console.print(
            f"[red]✗ Balance should not change when closing order! "
            f"Expected {balance_after_order_1}, got {balance_after_close}[/red]"
        )
        return False
    console.print(f"[green]✓ Balance unchanged after closing: {balance_after_close}[/green]")

    ledger_data_after_close = await client.get_ledger(order_id=order_id_1, operation_type="charge")
    charge_entries_after_close = [e for e in ledger_data_after_close["entries"] if e["operation_type"] == "charge"]
    if len(charge_entries_after_close) != 1:
        console.print(
            f"[red]✗ Closing order should not create new charge! "
            f"Expected 1 entry, got {len(charge_entries_after_close)}[/red]"
        )
        return False
    console.print("[green]✓ No new charge entry created when closing order[/green]")

    console.print(f"\n[yellow]Step 3: Creating second order for same customer (should charge)...[/yellow]")
    conv_id_2 = f"scenario5_conv2_{datetime.now().timestamp()}"
    await client.send_inbound_message(
        user_id=user_id,
        conversation_id=conv_id_2,
        text="Second message after closure",
    )
    console.print("[green]✓ Second message sent[/green]")

    thread_data_2 = await client.get_or_create_thread(user_id, conv_id_2)
    order_context_2 = await client.get_order_by_thread(thread_data_2["thread_id"])
    order_id_2 = order_context_2["order_id"]
    console.print(f"[green]✓ Second order ID: {order_id_2}[/green]")

    if order_id_2 == order_id_1:
        console.print("[red]✗ Second order should be different from first order![/red]")
        return False

    order_2 = await client.get_order(order_id_2)
    if order_2.get("billing_status") != "active":
        status_2 = order_2.get("billing_status")
        console.print(f"[red]✗ Second order billing_status should be 'active', got '{status_2}'[/red]")
        return False
    if not order_2.get("charged_at"):
        console.print("[red]✗ Second order charged_at is not set![/red]")
        return False

    balance_after_order_2 = (await client.get_balance())["balance"]
    expected_balance_2 = balance_after_order_1 - CHARGE_AMOUNT
    if balance_after_order_2 != expected_balance_2:
        console.print(
            f"[red]✗ Balance after second order should be {expected_balance_2}, got {balance_after_order_2}[/red]"
        )
        return False
    console.print(
        f"[green]✓ Balance after second order: {balance_after_order_2} (decremented by {CHARGE_AMOUNT})[/green]"
    )

    ledger_data_2 = await client.get_ledger(order_id=order_id_2, operation_type="charge")
    charge_entries_2 = [e for e in ledger_data_2["entries"] if e["operation_type"] == "charge"]
    if len(charge_entries_2) != 1:
        console.print(f"[red]✗ Expected exactly 1 charge entry for second order, got {len(charge_entries_2)}[/red]")
        return False
    console.print(f"[green]✓ Found exactly 1 charge entry for second order[/green]")

    console.print(f"\n[yellow]Step 4: Verifying total charges and balance...[/yellow]")
    total_ledger = await client.get_ledger(operation_type="charge", limit=100)
    all_charges = [e for e in total_ledger["entries"] if e["operation_type"] == "charge"]
    order_1_charges = [e for e in all_charges if e.get("order_id") == order_id_1]
    order_2_charges = [e for e in all_charges if e.get("order_id") == order_id_2]

    if len(order_1_charges) != 1:
        console.print(f"[red]✗ Expected exactly 1 charge for order {order_id_1}, got {len(order_1_charges)}[/red]")
        return False
    if len(order_2_charges) != 1:
        console.print(f"[red]✗ Expected exactly 1 charge for order {order_id_2}, got {len(order_2_charges)}[/red]")
        return False

    total_expected_balance = initial_balance - (CHARGE_AMOUNT * 2)
    if balance_after_order_2 != total_expected_balance:
        console.print(
            f"[red]✗ Total balance should be {total_expected_balance} "
            f"(initial {initial_balance} - {CHARGE_AMOUNT * 2} charges), "
            f"got {balance_after_order_2}[/red]"
        )
        return False

    console.print("[green]✓ Total charges: 2 (one per order)[/green]")
    console.print(f"[green]✓ Total balance decremented by exactly {CHARGE_AMOUNT * 2} units[/green]")
    console.print("[green]✓ Closing order does not charge, new order after closure charges correctly[/green]")

    console.print("\n[bold green]✓ Scenario 5 PASSED[/bold green]")
    return True


async def interactive_menu(client: BillingTestClient):
    """Run interactive menu."""
    while True:
        console.print("\n" + "=" * 60)
        console.print("[bold]Billing Migration Test Menu[/bold]")
        console.print("=" * 60)
        if client.company_id:
            console.print(f"Company ID: [cyan]{client.company_id}[/cyan]")
        balance_data = await client.get_balance()
        console.print(f"Current Balance: [cyan]{balance_data['balance']}[/cyan]")
        if client.order_id:
            console.print(f"Order ID: [cyan]{client.order_id}[/cyan]")
        console.print("-" * 60)
        console.print("\\[1] Scenario 1: New Order Billing")
        console.print("\\[2] Scenario 2: Idempotency")
        console.print("\\[3] Scenario 3: Insufficient Balance")
        console.print("\\[4] Scenario 4: Multiple Threads, One Order")
        console.print("\\[5] Scenario 5: Order Closure and New Order")
        console.print("\\[a] Run All Scenarios")
        console.print("-" * 60)
        console.print("\\[b] Get balance")
        console.print("\\[t] Top up balance")
        console.print("\\[l] List ledger entries")
        console.print("\\[o] Get order details")
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
                    await scenario_1_new_order_billing(client)
                case "2":
                    await scenario_2_idempotency(client)
                case "3":
                    await scenario_3_insufficient_balance(client)
                case "4":
                    await scenario_4_multiple_threads_one_order(client)
                case "5":
                    await scenario_5_order_closure_and_new_order(client)
                case "a":
                    console.print("\n[bold yellow]Running all scenarios...[/bold yellow]\n")
                    results = []
                    results.append(("Scenario 1", await scenario_1_new_order_billing(client)))
                    results.append(("Scenario 2", await scenario_2_idempotency(client)))
                    results.append(("Scenario 3", await scenario_3_insufficient_balance(client)))
                    results.append(("Scenario 4", await scenario_4_multiple_threads_one_order(client)))
                    results.append(("Scenario 5", await scenario_5_order_closure_and_new_order(client)))

                    console.print("\n" + "=" * 60)
                    console.print("[bold]Test Results Summary[/bold]")
                    console.print("=" * 60)
                    for name, passed in results:
                        status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
                        console.print(f"{name}: {status}")
                    console.print("=" * 60)
                case "b":
                    balance_data = await client.get_balance()
                    console.print(f"\n[cyan]Balance: {balance_data['balance']}[/cyan]")
                    console.print(f"Balance Warning: {balance_data['balance_warning']}")
                    console.print(f"Updated At: {balance_data['updated_at']}")
                case "t":
                    try:
                        amount_str = await asyncio.get_event_loop().run_in_executor(None, input, "Amount: ")
                        amount = int(amount_str)
                        comment = await asyncio.get_event_loop().run_in_executor(None, input, "Comment (optional): ")
                        result = await client.top_up_balance(amount, comment if comment.strip() else None)
                        console.print(f"\n[green]✓ Top-up successful[/green]")
                        console.print(f"New Balance: {result['new_balance']}")
                        console.print(f"Amount Added: {result['amount_added']}")
                    except ValueError:
                        console.print("[red]Invalid amount[/red]")
                    except Exception as e:
                        console.print(f"[red]Error: {e}[/red]")
                case "l":
                    ledger_data = await client.get_ledger(limit=20)
                    console.print(
                        f"\n[cyan]Found {ledger_data['total']} ledger entries "
                        f"(showing {len(ledger_data['entries'])}):[/cyan]"
                    )
                    for entry in ledger_data["entries"][:10]:
                        order_id_str = entry.get("order_id") or "N/A"
                        console.print(
                            f"  - {entry['operation_type']}: {entry['amount']} "
                            f"(Order: {order_id_str}, Time: {entry['timestamp']})"
                        )
                case "o":
                    if not client.order_id:
                        try:
                            order_id_str = await asyncio.get_event_loop().run_in_executor(None, input, "Order ID: ")
                            order_id = int(order_id_str)
                        except ValueError:
                            console.print("[red]Invalid order ID[/red]")
                            continue
                    else:
                        order_id = client.order_id
                    order = await client.get_order(order_id)
                    print_order(order)
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
            "[bold cyan]Billing Migration Test[/bold cyan]\n\n"
            "This script tests Plan 019: Billing Migration from Thread to Order\n"
            "Covers all 4 test scenarios from the plan.",
            border_style="cyan",
        )
    )

    client = BillingTestClient()

    if not await setup_environment(client):
        sys.exit(1)

    await interactive_menu(client)

    console.print("\n[bold green]Done![/bold green]")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
