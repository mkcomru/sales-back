#!/usr/bin/env python3
"""Interactive test script for thread assignee feature.

This script:
1. Authenticates with predefined credentials
2. Sets up test company and members
3. Creates a test thread
4. Connects to WebSocket for real-time events
5. Provides interactive menu for assignee operations

Usage:
    cd scripts/manual_testing
    python test_assignee.py

Requirements:
    pip install -r requirements.txt
"""

import asyncio
import json
import sys
from datetime import datetime

import httpx
import websockets
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Configuration
BASE_URL = "http://localhost:8081/api/v1"
WS_URL = "ws://localhost:8081/api/v1"

# Test credentials (superuser)
SUPERUSER_EMAIL = "komarovdemian@yandex.ru"
SUPERUSER_PASSWORD = "1234567890"

# Second user for testing
SECOND_USER_EMAIL = "second_assignee@example.com"
SECOND_USER_PASSWORD = "testpassword123"

# Test company
TEST_COMPANY_NAME = "Assignee Test Company"

console = Console()


class AssigneeTestClient:
    def __init__(self):
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.user_id: int | None = None
        self.company_id: int | None = None
        self.company_user_id: int | None = None
        self.second_user_id: int | None = None
        self.second_company_user_id: int | None = None
        self.thread_id: str | None = None
        self.ws_events: list[dict] = []
        self.ws_task: asyncio.Task | None = None

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

    async def signup(
        self, email: str, password: str, first_name: str, last_name: str, is_superuser: bool = False
    ) -> dict:
        """Create a new user (requires superuser auth)."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                "/auth/signup",
                json={
                    "email": email,
                    "password": password,
                    "first_name": first_name,
                    "last_name": last_name,
                    "is_superuser": is_superuser,
                },
                headers=self.headers,
            )
            if response.status_code == 409:
                return {"error": "User already exists"}
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
                    "description": "Test company for assignee feature",
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
            return response.json()

    async def list_threads(self) -> list[dict]:
        """List threads for the company."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.get(
                f"/companies/{self.company_id}/threads",
                headers=self.headers,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("items", [])

    async def get_thread(self, thread_id: str) -> dict:
        """Get thread details."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.get(
                f"/companies/{self.company_id}/threads/{thread_id}",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def update_assignee(self, thread_id: str, assignee_id: int | None) -> dict:
        """Update thread assignee."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.put(
                f"/companies/{self.company_id}/threads/{thread_id}/assignee",
                json={"assignee_id": assignee_id},
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def create_internal_thread(self) -> dict:
        """Create a thread via internal API."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                "/internal/chat/threads/get-or-create",
                json={
                    "user_id": f"test_user_{datetime.now().timestamp()}",
                    "company_id": self.company_id,
                    "channel_type": "test",
                    "connector_id": "test_connector",
                    "conversation_id": f"test_conv_{datetime.now().timestamp()}",
                },
            )
            response.raise_for_status()
            return response.json()

    async def websocket_listener(self):
        """Listen to WebSocket events."""
        ws_endpoint = f"{WS_URL}/companies/{self.company_id}/threads/{self.thread_id}/ws?token={self.access_token}"

        console.print(f"[yellow]Connecting to WebSocket: {ws_endpoint[:80]}...[/yellow]")

        try:
            async with websockets.connect(ws_endpoint) as ws:
                console.print("[green]✓ WebSocket connected![/green]")

                async for message in ws:
                    try:
                        event = json.loads(message)
                        self.ws_events.append(event)

                        # Display event
                        event_type = event.get("event_type", "unknown")
                        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

                        console.print(
                            Panel(
                                json.dumps(event, indent=2, ensure_ascii=False, default=str),
                                title=f"[cyan]{timestamp}[/cyan] WebSocket Event: [bold magenta]{event_type}[/bold magenta]",
                                border_style="blue",
                            )
                        )
                    except json.JSONDecodeError:
                        console.print(f"[red]Invalid JSON: {message}[/red]")

        except websockets.exceptions.ConnectionClosed as e:
            console.print(f"[red]WebSocket closed: {e}[/red]")
        except Exception as e:
            console.print(f"[red]WebSocket error: {e}[/red]")

    async def start_websocket(self):
        """Start WebSocket listener in background."""
        if self.ws_task:
            self.ws_task.cancel()
            try:
                await self.ws_task
            except asyncio.CancelledError:
                pass

        self.ws_task = asyncio.create_task(self.websocket_listener())

    async def stop_websocket(self):
        """Stop WebSocket listener."""
        if self.ws_task:
            self.ws_task.cancel()
            try:
                await self.ws_task
            except asyncio.CancelledError:
                pass


async def setup_environment(client: AssigneeTestClient) -> bool:
    """Setup test environment with users, company, and thread."""

    console.print("\n[bold blue]Setting up test environment...[/bold blue]\n")

    # Step 1: Try to login as superuser, if fails - need to create manually
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

    # Get user info
    me = await client.get_me()
    client.user_id = me["id"]
    console.print(f"   User ID: {client.user_id}, Name: {me['first_name']} {me['last_name']}")

    # Step 2: Create/get second user
    console.print("\n2. Setting up second user...")
    result = await client.signup(
        email=SECOND_USER_EMAIL,
        password=SECOND_USER_PASSWORD,
        first_name="Second",
        last_name="Manager",
        is_superuser=False,
    )
    if "error" in result:
        console.print("[yellow]   Second user already exists[/yellow]")
    else:
        client.second_user_id = result["id"]
        console.print(f"[green]✓ Created second user: {result['id']}[/green]")

    # Step 3: Get or create company
    console.print("\n3. Setting up company...")
    companies = await client.list_companies()

    existing = next((c for c in companies if c["name"] == TEST_COMPANY_NAME), None)
    if existing:
        client.company_id = existing["id"]
        console.print(f"[yellow]   Using existing company: {client.company_id}[/yellow]")
    else:
        company = await client.create_company(TEST_COMPANY_NAME)
        client.company_id = company["id"]
        console.print(f"[green]✓ Created company: {client.company_id}[/green]")

    # Step 4: Try to add second user to company (login as them, access company)
    console.print("\n4. Attempting to add second user to company...")
    try:
        second_login = await client.login(SECOND_USER_EMAIL, SECOND_USER_PASSWORD)
        if "error" not in second_login:
            # Temporarily use second user's token to access company (auto-creates membership for superusers)
            original_token = client.access_token
            client.access_token = second_login["access_token"]
            try:
                await client.list_company_members()  # This triggers auto-add for superusers
                console.print("[green]✓ Second user accessed company[/green]")
            except Exception:
                console.print("[yellow]   Second user cannot access company (not a superuser)[/yellow]")
            client.access_token = original_token
    except Exception as e:
        console.print(f"[yellow]   Could not setup second user: {e}[/yellow]")

    # Step 5: List company members
    console.print("\n5. Loading company members...")
    members = await client.list_company_members()

    for member in members:
        console.print(
            f"   Member: {member['first_name']} {member['last_name']} (id={member['id']}, role={member['role']})"
        )
        if member["user_id"] == client.user_id:
            client.company_user_id = member["id"]
        elif member["email"] == SECOND_USER_EMAIL:
            client.second_company_user_id = member["id"]

    if not client.company_user_id:
        console.print("[red]✗ Current user is not a member of the company[/red]")
        return False

    console.print(f"[green]✓ Your company_user_id: {client.company_user_id}[/green]")

    if client.second_company_user_id:
        console.print(f"[green]✓ Second member company_user_id: {client.second_company_user_id}[/green]")
    else:
        console.print("[yellow]   Second user not in company (create as superuser for multi-user testing)[/yellow]")

    # Step 6: Get or create thread
    console.print("\n6. Setting up test thread...")
    threads = await client.list_threads()

    if threads:
        client.thread_id = threads[0]["thread_id"]
        console.print(f"[yellow]   Using existing thread: {client.thread_id}[/yellow]")
    else:
        thread = await client.create_internal_thread()
        client.thread_id = thread["thread_id"]
        console.print(f"[green]✓ Created thread: {client.thread_id}[/green]")

    # Step 7: Show current thread state
    console.print("\n7. Current thread state:")
    thread_detail = await client.get_thread(client.thread_id)

    table = Table(title="Thread Details")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("thread_id", thread_detail["thread_id"])
    table.add_row("state", thread_detail["state"])
    table.add_row("assignee_id", str(thread_detail.get("assignee_id")))
    table.add_row(
        "assignee",
        json.dumps(thread_detail.get("assignee"), ensure_ascii=False) if thread_detail.get("assignee") else "null",
    )
    table.add_row("assistant_active", str(thread_detail["assistant_active"]))

    console.print(table)

    return True


async def interactive_menu(client: AssigneeTestClient):
    """Run interactive menu."""

    console.print("\n[bold green]Starting WebSocket listener...[/bold green]")
    await client.start_websocket()

    # Give WebSocket time to connect
    await asyncio.sleep(1)

    while True:
        console.print("\n" + "=" * 60)
        console.print("[bold]Assignee Test Menu[/bold]")
        console.print("=" * 60)
        console.print(f"Thread: [cyan]{client.thread_id}[/cyan]")
        console.print(f"Your company_user_id: [cyan]{client.company_user_id}[/cyan]")
        if client.second_company_user_id:
            console.print(f"Second member id: [cyan]{client.second_company_user_id}[/cyan]")
        console.print("-" * 60)
        console.print("\\[1] Assign to ME")
        console.print("\\[2] Unassign (set to NOBODY)")
        if client.second_company_user_id:
            console.print("\\[3] Assign to SECOND member")
        console.print("\\[4] Show current thread state")
        console.print("\\[5] List all company members")
        console.print("\\[6] Show captured WebSocket events")
        console.print("\\[7] Clear WebSocket events")
        console.print("\\[q] Quit")
        console.print("-" * 60)

        try:
            choice = await asyncio.get_event_loop().run_in_executor(None, input, "Choice: ")
        except EOFError:
            break

        choice = choice.strip().lower()

        if choice == "1":
            console.print(f"\n[yellow]Assigning thread to ME (company_user_id={client.company_user_id})...[/yellow]")
            try:
                result = await client.update_assignee(client.thread_id, client.company_user_id)
                console.print(
                    Panel(
                        json.dumps(result, indent=2, ensure_ascii=False, default=str),
                        title="[green]API Response[/green]",
                        border_style="green",
                    )
                )
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        elif choice == "2":
            console.print("\n[yellow]Unassigning thread (setting to null)...[/yellow]")
            try:
                result = await client.update_assignee(client.thread_id, None)
                console.print(
                    Panel(
                        json.dumps(result, indent=2, ensure_ascii=False, default=str),
                        title="[green]API Response[/green]",
                        border_style="green",
                    )
                )
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        elif choice == "3" and client.second_company_user_id:
            console.print(
                f"\n[yellow]Assigning thread to SECOND member (company_user_id={client.second_company_user_id})...[/yellow]"
            )
            try:
                result = await client.update_assignee(client.thread_id, client.second_company_user_id)
                console.print(
                    Panel(
                        json.dumps(result, indent=2, ensure_ascii=False, default=str),
                        title="[green]API Response[/green]",
                        border_style="green",
                    )
                )
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        elif choice == "4":
            console.print("\n[yellow]Fetching current thread state...[/yellow]")
            try:
                thread = await client.get_thread(client.thread_id)
                console.print(
                    Panel(
                        json.dumps(thread, indent=2, ensure_ascii=False, default=str),
                        title="[cyan]Thread State[/cyan]",
                        border_style="cyan",
                    )
                )
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        elif choice == "5":
            console.print("\n[yellow]Fetching company members...[/yellow]")
            try:
                members = await client.list_company_members()
                console.print(
                    Panel(
                        json.dumps(members, indent=2, ensure_ascii=False, default=str),
                        title="[cyan]Company Members[/cyan]",
                        border_style="cyan",
                    )
                )
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        elif choice == "6":
            if client.ws_events:
                console.print(f"\n[cyan]Captured {len(client.ws_events)} WebSocket events:[/cyan]")
                for i, event in enumerate(client.ws_events):
                    console.print(
                        Panel(
                            json.dumps(event, indent=2, ensure_ascii=False, default=str),
                            title=f"Event #{i + 1}: {event.get('event_type', 'unknown')}",
                            border_style="blue",
                        )
                    )
            else:
                console.print("[yellow]No WebSocket events captured yet[/yellow]")

        elif choice == "7":
            client.ws_events.clear()
            console.print("[green]✓ WebSocket events cleared[/green]")

        elif choice == "q":
            console.print("\n[yellow]Stopping WebSocket and exiting...[/yellow]")
            await client.stop_websocket()
            break

        # Small delay for WebSocket events to arrive
        await asyncio.sleep(0.5)


async def main():
    console.print(
        Panel.fit(
            "[bold cyan]Thread Assignee Feature Test[/bold cyan]\n\n"
            "This script tests the PUT /threads/{thread_id}/assignee endpoint\n"
            "and verifies WebSocket events are properly broadcast.",
            border_style="cyan",
        )
    )

    client = AssigneeTestClient()

    if not await setup_environment(client):
        sys.exit(1)

    await interactive_menu(client)

    console.print("\n[bold green]Done![/bold green]")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
