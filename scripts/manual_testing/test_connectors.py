#!/usr/bin/env python3
"""Interactive test script for unified Connector model.

This script tests:
1. Connector CRUD operations (create, read, update, delete)
2. API key management for custom connectors
3. Internal validation endpoints for managed/custom connectors
4. Telegram connector config validation

Usage:
    cd scripts/manual_testing
    python test_connectors.py

Requirements:
    pip install -r requirements.txt
"""

import asyncio
import json
import secrets
import sys

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Configuration
BASE_URL = "http://localhost:8081/api/v1"
SERVICE_API_KEY = "test-api-key"  # pragma: allowlist secret

# Test credentials (superuser)
SUPERUSER_EMAIL = "komarovdemian@yandex.ru"
SUPERUSER_PASSWORD = "1234567890"

# Test company
TEST_COMPANY_NAME = "Connector Test Company"

console = Console()


class ConnectorTestClient:
    def __init__(self):
        self.access_token: str | None = None
        self.user_id: int | None = None
        self.company_id: int | None = None
        self.connectors: list[dict] = []
        self.current_connector_id: int | None = None
        self.current_connector_public_id: str | None = None
        self.api_keys: list[dict] = []
        self.threads: list[dict] = []
        self.current_thread_id: str | None = None

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    @property
    def service_headers(self) -> dict:
        return {"X-Service-Key": SERVICE_API_KEY}

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
                    "description": "Test company for connector feature",
                    "rules": "Test rules",
                    "tone_of_voice": "Professional",
                    "assistant_name": "Test Assistant",
                    "qualification_workflow": "Standard",
                    "qualification_examples": "Examples",
                    "collection_name": f"test_collection_{secrets.token_hex(4)}",
                    "stages_config": [],
                    "category_rules": [],
                },
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    # =========================================================================
    # Connector CRUD (service key auth)
    # =========================================================================

    async def list_connectors(self) -> dict:
        """List all connectors."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.get(
                "/transport/connectors",
                headers=self.service_headers,
            )
            response.raise_for_status()
            return response.json()

    async def get_connector(self, connector_db_id: int) -> dict:
        """Get connector by database ID."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.get(
                f"/transport/connectors/{connector_db_id}",
                headers=self.service_headers,
            )
            response.raise_for_status()
            return response.json()

    async def create_connector(self, payload: dict) -> dict:
        """Create a new connector."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                "/transport/connectors",
                json=payload,
                headers=self.service_headers,
            )
            if response.status_code >= 400:
                return {"error": response.text, "status_code": response.status_code}
            response.raise_for_status()
            return response.json()

    async def update_connector(self, connector_db_id: int, payload: dict) -> dict:
        """Update a connector."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.patch(
                f"/transport/connectors/{connector_db_id}",
                json=payload,
                headers=self.service_headers,
            )
            response.raise_for_status()
            return response.json()

    async def delete_connector(self, connector_db_id: int) -> bool:
        """Delete a connector."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.delete(
                f"/transport/connectors/{connector_db_id}",
                headers=self.service_headers,
            )
            return response.status_code == 204

    # =========================================================================
    # API Key Management
    # =========================================================================

    async def create_api_key(self, connector_db_id: int) -> dict:
        """Create API key for connector."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                f"/transport/connectors/{connector_db_id}/api-keys",
                headers=self.service_headers,
            )
            response.raise_for_status()
            return response.json()

    async def list_api_keys(self, connector_db_id: int) -> list[dict]:
        """List API keys for connector."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.get(
                f"/transport/connectors/{connector_db_id}/api-keys",
                headers=self.service_headers,
            )
            response.raise_for_status()
            return response.json()

    async def delete_api_key(self, connector_db_id: int, key_id: int) -> bool:
        """Delete API key."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.delete(
                f"/transport/connectors/{connector_db_id}/api-keys/{key_id}",
                headers=self.service_headers,
            )
            return response.status_code == 204

    # =========================================================================
    # Internal Validation Endpoints
    # =========================================================================

    async def validate_api_key_token(self, bearer_token: str) -> dict:
        """Validate Bearer token for custom connectors."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.get(
                "/internal/connectors/validate",
                headers={
                    **self.service_headers,
                    "Authorization": f"Bearer {bearer_token}",
                },
            )
            if response.status_code >= 400:
                return {
                    "error": response.json().get("detail", {}).get("error", "unknown"),
                    "status_code": response.status_code,
                }
            return response.json()

    async def get_connector_context(self, connector_id: str) -> dict:
        """Get ConnectorContext for managed connector."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.get(
                f"/internal/connectors/{connector_id}",
                headers=self.service_headers,
            )
            if response.status_code >= 400:
                return {
                    "error": response.json().get("detail", {}).get("error", "unknown"),
                    "status_code": response.status_code,
                }
            return response.json()

    # =========================================================================
    # Thread & Manager Message Testing
    # =========================================================================

    async def list_threads(self, company_id: int, limit: int = 20) -> list[dict]:
        """List threads for a company."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.get(
                f"/companies/{company_id}/threads",
                headers=self.headers,
                params={"limit": limit, "offset": 0},
            )
            if response.status_code >= 400:
                return []
            data = response.json()
            return data.get("items", [])

    async def get_thread(self, company_id: int, thread_id: str) -> dict | None:
        """Get thread details."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.get(
                f"/companies/{company_id}/threads/{thread_id}",
                headers=self.headers,
            )
            if response.status_code >= 400:
                return None
            return response.json()

    async def send_manager_message(
        self, company_id: int, thread_id: str, content: str, pause_assistant: bool = True
    ) -> dict:
        """Send manager message to a thread."""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            response = await client.post(
                f"/companies/{company_id}/threads/{thread_id}/messages",
                headers=self.headers,
                json={
                    "role": "manager",
                    "content": content,
                    "pause_assistant": pause_assistant,
                },
            )
            if response.status_code >= 400:
                return {
                    "error": response.json().get("detail", {}),
                    "status_code": response.status_code,
                }
            return response.json()


def generate_bot_token() -> str:
    """Generate a fake but realistic-looking Telegram bot token."""
    bot_id = secrets.randbelow(9999999999) + 1000000000
    token_part = secrets.token_urlsafe(35)[:35]
    return f"{bot_id}:{token_part}"


async def setup_environment(client: ConnectorTestClient) -> bool:
    """Setup test environment."""

    console.print("\n[bold blue]Setting up test environment...[/bold blue]\n")

    # Step 1: Login
    console.print("1. Authenticating...")
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
    console.print("[green]✓ Logged in[/green]")

    me = await client.get_me()
    client.user_id = me["id"]
    console.print(f"   User: {me['first_name']} {me['last_name']} (id={client.user_id})")

    # Step 2: Get or create company
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

    # Step 3: List existing connectors
    console.print("\n3. Loading existing connectors...")
    connectors_data = await client.list_connectors()
    client.connectors = connectors_data.get("connectors", [])

    if client.connectors:
        console.print(f"   Found {len(client.connectors)} connector(s)")
        for conn in client.connectors:
            console.print(f"   - [{conn['type']}] {conn['connector_id']} (id={conn['id']}, enabled={conn['enabled']})")
    else:
        console.print("   No connectors found")

    return True


def display_connector_table(connectors: list[dict]):
    """Display connectors in a table."""
    table = Table(title="Connectors")
    table.add_column("ID", style="cyan")
    table.add_column("Connector ID", style="green")
    table.add_column("Type", style="magenta")
    table.add_column("Channel", style="yellow")
    table.add_column("Debounce", style="dim")
    table.add_column("Managed", style="blue")
    table.add_column("Enabled", style="white")

    for conn in connectors:
        table.add_row(
            str(conn["id"]),
            conn["connector_id"],
            conn["type"],
            conn["channel_type"],
            f"{conn.get('debounce_window_seconds', 45)}s",
            "✓" if conn["managed"] else "✗",
            "✓" if conn["enabled"] else "✗",
        )

    console.print(table)


async def interactive_menu(client: ConnectorTestClient):
    """Run interactive menu."""

    while True:
        console.print("\n" + "=" * 70)
        console.print("[bold]Unified Connector Test Menu[/bold]")
        console.print("=" * 70)
        console.print(f"Company ID: [cyan]{client.company_id}[/cyan]")
        if client.current_connector_id:
            console.print(
                f"Selected connector: [cyan]{client.current_connector_public_id}[/cyan] "
                f"(db_id={client.current_connector_id})"
            )
        if client.current_thread_id:
            console.print(f"Selected thread: [cyan]{client.current_thread_id}[/cyan]")
        console.print("-" * 70)
        console.print("[bold]CRUD Operations:[/bold]")
        console.print("  \\[1] List all connectors")
        console.print("  \\[2] Create TELEGRAM connector (managed)")
        console.print("  \\[3] Create CUSTOM connector (unmanaged)")
        console.print("  \\[4] Get connector details")
        console.print("  \\[5] Update connector")
        console.print("  \\[6] Delete connector")
        console.print("-" * 70)
        console.print("[bold]API Key Management:[/bold]")
        console.print("  \\[7] Create API key for connector")
        console.print("  \\[8] List API keys")
        console.print("  \\[9] Delete API key")
        console.print("-" * 70)
        console.print("[bold]Internal Validation:[/bold]")
        console.print("  \\[v] Validate Bearer token (custom connector)")
        console.print("  \\[c] Get ConnectorContext (managed connector)")
        console.print("-" * 70)
        console.print("[bold]Thread & Manager Messages:[/bold]")
        console.print("  \\[t] List threads for company")
        console.print("  \\[g] Get thread details")
        console.print("  \\[m] Send manager message (disable assistant)")
        console.print("  \\[r] Send manager message (keep assistant)")
        console.print("-" * 70)
        console.print("  \\[s] Select connector by ID")
        console.print("  \\[q] Quit")
        console.print("-" * 70)

        try:
            choice = await asyncio.get_event_loop().run_in_executor(None, input, "Choice: ")
        except EOFError:
            break

        choice = choice.strip().lower()

        # =====================================================================
        # CRUD Operations
        # =====================================================================

        if choice == "1":
            console.print("\n[yellow]Listing connectors...[/yellow]")
            try:
                data = await client.list_connectors()
                client.connectors = data.get("connectors", [])
                if client.connectors:
                    display_connector_table(client.connectors)
                else:
                    console.print("[dim]No connectors found[/dim]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        elif choice == "2":
            console.print("\n[bold]Create Telegram Connector (managed)[/bold]")
            try:
                connector_id = await asyncio.get_event_loop().run_in_executor(
                    None, input, f"Connector ID (e.g., tg-bot-{secrets.token_hex(3)}): "
                )
                connector_id = connector_id.strip() or f"tg-bot-{secrets.token_hex(3)}"

                display_name = await asyncio.get_event_loop().run_in_executor(
                    None, input, "Display name (default: Test Telegram Bot): "
                )
                display_name = display_name.strip() or "Test Telegram Bot"

                bot_token = await asyncio.get_event_loop().run_in_executor(
                    None, input, "Bot token (leave empty for fake): "
                )
                bot_token = bot_token.strip() or generate_bot_token()

                debounce_input = await asyncio.get_event_loop().run_in_executor(
                    None, input, "Debounce window seconds (default: 45, range 1-300): "
                )
                debounce_seconds = int(debounce_input.strip()) if debounce_input.strip().isdigit() else 45

                payload = {
                    "connector_id": connector_id,
                    "company_id": client.company_id,
                    "type": "telegram",
                    "channel_type": "telegram",
                    "display_name": display_name,
                    "managed": True,
                    "config": {
                        "bot_token": bot_token,
                        "mode": "auto",
                    },
                    "enabled": True,
                    "debounce_window_seconds": debounce_seconds,
                }

                console.print("\n[dim]Creating connector with payload:[/dim]")
                console.print(Panel(json.dumps(payload, indent=2), border_style="dim"))

                result = await client.create_connector(payload)
                if "error" in result:
                    console.print(f"[red]Error: {result['error']}[/red]")
                else:
                    client.current_connector_id = result["id"]
                    client.current_connector_public_id = result["connector_id"]
                    console.print(
                        Panel(
                            json.dumps(result, indent=2, default=str),
                            title="[green]Created Connector[/green]",
                            border_style="green",
                        )
                    )
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        elif choice == "3":
            console.print("\n[bold]Create Custom Connector (unmanaged)[/bold]")
            try:
                connector_id = await asyncio.get_event_loop().run_in_executor(
                    None, input, f"Connector ID (e.g., custom-{secrets.token_hex(3)}): "
                )
                connector_id = connector_id.strip() or f"custom-{secrets.token_hex(3)}"

                display_name = await asyncio.get_event_loop().run_in_executor(
                    None, input, "Display name (default: Custom Connector): "
                )
                display_name = display_name.strip() or "Custom Connector"

                channel_type = await asyncio.get_event_loop().run_in_executor(
                    None, input, "Channel type (default: custom): "
                )
                channel_type = channel_type.strip() or "custom"

                debounce_input = await asyncio.get_event_loop().run_in_executor(
                    None, input, "Debounce window seconds (default: 45, range 1-300): "
                )
                debounce_seconds = int(debounce_input.strip()) if debounce_input.strip().isdigit() else 45

                payload = {
                    "connector_id": connector_id,
                    "company_id": client.company_id,
                    "type": "custom",
                    "channel_type": channel_type,
                    "display_name": display_name,
                    "managed": False,
                    "config": {},
                    "enabled": True,
                    "debounce_window_seconds": debounce_seconds,
                }

                result = await client.create_connector(payload)
                if "error" in result:
                    console.print(f"[red]Error: {result['error']}[/red]")
                else:
                    client.current_connector_id = result["id"]
                    client.current_connector_public_id = result["connector_id"]
                    console.print(
                        Panel(
                            json.dumps(result, indent=2, default=str),
                            title="[green]Created Custom Connector[/green]",
                            border_style="green",
                        )
                    )
                    console.print(
                        "\n[yellow]Tip: Create an API key for this connector to test Bearer token auth[/yellow]"
                    )
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        elif choice == "4":
            if not client.current_connector_id:
                console.print("[yellow]No connector selected. Use \\[s] to select one.[/yellow]")
                continue
            console.print(f"\n[yellow]Getting connector {client.current_connector_id}...[/yellow]")
            try:
                result = await client.get_connector(client.current_connector_id)
                console.print(
                    Panel(
                        json.dumps(result, indent=2, default=str),
                        title="[cyan]Connector Details[/cyan]",
                        border_style="cyan",
                    )
                )
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        elif choice == "5":
            if not client.current_connector_id:
                console.print("[yellow]No connector selected. Use \\[s] to select one.[/yellow]")
                continue
            console.print(f"\n[bold]Update connector {client.current_connector_id}[/bold]")
            try:
                console.print("Enter fields to update (leave empty to skip):")

                display_name = await asyncio.get_event_loop().run_in_executor(None, input, "New display name: ")
                enabled = await asyncio.get_event_loop().run_in_executor(None, input, "Enabled (true/false): ")
                debounce = await asyncio.get_event_loop().run_in_executor(None, input, "Debounce window seconds: ")

                payload = {}
                if display_name.strip():
                    payload["display_name"] = display_name.strip()
                if enabled.strip().lower() in ("true", "false"):
                    payload["enabled"] = enabled.strip().lower() == "true"
                if debounce.strip().isdigit():
                    payload["debounce_window_seconds"] = int(debounce.strip())

                if not payload:
                    console.print("[yellow]No updates specified[/yellow]")
                    continue

                result = await client.update_connector(client.current_connector_id, payload)
                console.print(
                    Panel(
                        json.dumps(result, indent=2, default=str),
                        title="[green]Updated Connector[/green]",
                        border_style="green",
                    )
                )
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        elif choice == "6":
            if not client.current_connector_id:
                console.print("[yellow]No connector selected. Use \\[s] to select one.[/yellow]")
                continue
            console.print(f"\n[bold red]Delete connector {client.current_connector_id}?[/bold red]")
            confirm = await asyncio.get_event_loop().run_in_executor(None, input, "Type 'yes' to confirm: ")
            if confirm.strip().lower() == "yes":
                try:
                    success = await client.delete_connector(client.current_connector_id)
                    if success:
                        console.print("[green]✓ Connector deleted[/green]")
                        client.current_connector_id = None
                        client.current_connector_public_id = None
                    else:
                        console.print("[red]Failed to delete connector[/red]")
                except Exception as e:
                    console.print(f"[red]Error: {e}[/red]")

        # =====================================================================
        # API Key Management
        # =====================================================================

        elif choice == "7":
            if not client.current_connector_id:
                console.print("[yellow]No connector selected. Use \\[s] to select one.[/yellow]")
                continue
            console.print(f"\n[yellow]Creating API key for connector {client.current_connector_id}...[/yellow]")
            try:
                result = await client.create_api_key(client.current_connector_id)
                client.api_keys.append(result)
                console.print(
                    Panel(
                        json.dumps(result, indent=2, default=str),
                        title="[green]Created API Key[/green]",
                        border_style="green",
                    )
                )
                console.print(
                    f"\n[bold yellow]⚠ SAVE THIS KEY! It won't be shown again:[/bold yellow]\n"
                    f"[bold white]{result['raw_key']}[/bold white]"
                )
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        elif choice == "8":
            if not client.current_connector_id:
                console.print("[yellow]No connector selected. Use \\[s] to select one.[/yellow]")
                continue
            console.print(f"\n[yellow]Listing API keys for connector {client.current_connector_id}...[/yellow]")
            try:
                keys = await client.list_api_keys(client.current_connector_id)
                if keys:
                    table = Table(title="API Keys")
                    table.add_column("ID", style="cyan")
                    table.add_column("Enabled", style="green")
                    table.add_column("Created At", style="yellow")
                    for key in keys:
                        table.add_row(
                            str(key["id"]),
                            "✓" if key["enabled"] else "✗",
                            key["created_at"],
                        )
                    console.print(table)
                else:
                    console.print("[dim]No API keys found[/dim]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        elif choice == "9":
            if not client.current_connector_id:
                console.print("[yellow]No connector selected. Use \\[s] to select one.[/yellow]")
                continue
            try:
                key_id = await asyncio.get_event_loop().run_in_executor(None, input, "Enter API key ID to delete: ")
                key_id = int(key_id.strip())
                success = await client.delete_api_key(client.current_connector_id, key_id)
                if success:
                    console.print("[green]✓ API key deleted[/green]")
                else:
                    console.print("[red]Failed to delete API key[/red]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        # =====================================================================
        # Internal Validation
        # =====================================================================

        elif choice == "v":
            console.print("\n[bold]Validate Bearer Token (custom connector auth)[/bold]")
            try:
                token = await asyncio.get_event_loop().run_in_executor(None, input, "Enter Bearer token (sk_xxx): ")
                token = token.strip()
                if not token:
                    console.print("[yellow]No token provided[/yellow]")
                    continue

                result = await client.validate_api_key_token(token)
                if "error" in result:
                    console.print(
                        Panel(
                            json.dumps(result, indent=2),
                            title=f"[red]Validation Failed ({result.get('status_code', '?')})[/red]",
                            border_style="red",
                        )
                    )
                else:
                    console.print(
                        Panel(
                            json.dumps(result, indent=2, default=str),
                            title="[green]ConnectorContext[/green]",
                            border_style="green",
                        )
                    )
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        elif choice == "c":
            console.print("\n[bold]Get ConnectorContext (managed connector auth)[/bold]")
            try:
                connector_id = client.current_connector_public_id
                if not connector_id:
                    connector_id = await asyncio.get_event_loop().run_in_executor(None, input, "Enter connector_id: ")
                    connector_id = connector_id.strip()

                if not connector_id:
                    console.print("[yellow]No connector_id provided[/yellow]")
                    continue

                result = await client.get_connector_context(connector_id)
                if "error" in result:
                    console.print(
                        Panel(
                            json.dumps(result, indent=2),
                            title=f"[red]Not Found ({result.get('status_code', '?')})[/red]",
                            border_style="red",
                        )
                    )
                else:
                    console.print(
                        Panel(
                            json.dumps(result, indent=2, default=str),
                            title="[green]ConnectorContext[/green]",
                            border_style="green",
                        )
                    )
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        # =====================================================================
        # Utilities
        # =====================================================================

        elif choice == "s":
            try:
                db_id = await asyncio.get_event_loop().run_in_executor(None, input, "Enter connector database ID: ")
                db_id = int(db_id.strip())
                result = await client.get_connector(db_id)
                client.current_connector_id = result["id"]
                client.current_connector_public_id = result["connector_id"]
                console.print(f"[green]✓ Selected connector: {result['connector_id']}[/green]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        # =====================================================================
        # Thread & Manager Message Testing
        # =====================================================================

        elif choice == "t":
            if not client.company_id:
                console.print("[yellow]No company selected[/yellow]")
                continue
            console.print(f"\n[yellow]Listing threads for company {client.company_id}...[/yellow]")
            try:
                threads = await client.list_threads(client.company_id)
                client.threads = threads
                if threads:
                    table = Table(title="Threads")
                    table.add_column("Thread ID", style="cyan")
                    table.add_column("Channel", style="magenta")
                    table.add_column("State", style="yellow")
                    table.add_column("Assistant", style="green")
                    table.add_column("Last Message", style="dim")
                    for thread in threads[:20]:  # Limit display
                        assistant_status = "✓ Active" if thread.get("assistant_active") else "✗ Disabled"
                        last_msg = thread.get("last_message_preview", "")[:40]
                        if len(last_msg) > 40:
                            last_msg = last_msg[:37] + "..."
                        table.add_row(
                            thread.get("thread_id", "N/A"),
                            thread.get("channel_type", "N/A"),
                            thread.get("state", "N/A"),
                            assistant_status,
                            last_msg or "(no messages)",
                        )
                    console.print(table)
                    console.print(f"\n[dim]Found {len(threads)} thread(s). Use \\[g] to get details.[/dim]")
                else:
                    console.print("[dim]No threads found[/dim]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        elif choice == "g":
            if not client.company_id:
                console.print("[yellow]No company selected[/yellow]")
                continue
            console.print("\n[bold]Get Thread Details[/bold]")
            try:
                thread_id = client.current_thread_id
                if not thread_id:
                    thread_id = await asyncio.get_event_loop().run_in_executor(None, input, "Enter thread_id: ")
                    thread_id = thread_id.strip()

                if not thread_id:
                    console.print("[yellow]No thread_id provided[/yellow]")
                    continue

                result = await client.get_thread(client.company_id, thread_id)
                if result is None:
                    console.print("[red]Thread not found[/red]")
                else:
                    client.current_thread_id = thread_id
                    console.print(
                        Panel(
                            json.dumps(result, indent=2, default=str),
                            title="[cyan]Thread Details[/cyan]",
                            border_style="cyan",
                        )
                    )
                    console.print(f"\n[dim]Assistant Active: {result.get('assistant_active', False)}[/dim]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        elif choice == "m":
            if not client.company_id:
                console.print("[yellow]No company selected[/yellow]")
                continue
            console.print("\n[bold]Send Manager Message (Disable Assistant)[/bold]")
            try:
                thread_id = client.current_thread_id
                if not thread_id:
                    thread_id = await asyncio.get_event_loop().run_in_executor(None, input, "Enter thread_id: ")
                    thread_id = thread_id.strip()

                if not thread_id:
                    console.print("[yellow]No thread_id provided[/yellow]")
                    continue

                content = await asyncio.get_event_loop().run_in_executor(None, input, "Enter message content: ")
                content = content.strip()

                if not content:
                    console.print("[yellow]No content provided[/yellow]")
                    continue

                console.print("\n[yellow]Sending manager message...[/yellow]")
                result = await client.send_manager_message(client.company_id, thread_id, content, pause_assistant=True)

                if "error" in result:
                    console.print(
                        Panel(
                            json.dumps(result, indent=2),
                            title=f"[red]Failed ({result.get('status_code', '?')})[/red]",
                            border_style="red",
                        )
                    )
                else:
                    console.print(
                        Panel(
                            json.dumps(result, indent=2, default=str),
                            title="[green]Message Sent[/green]",
                            border_style="green",
                        )
                    )
                    console.print("\n[bold yellow]✓ Assistant should be disabled for this thread[/bold yellow]")
                    console.print("[dim]Next user message should not trigger AI response[/dim]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        elif choice == "r":
            if not client.company_id:
                console.print("[yellow]No company selected[/yellow]")
                continue
            console.print("\n[bold]Send Manager Message (Keep Assistant Active)[/bold]")
            try:
                thread_id = client.current_thread_id
                if not thread_id:
                    thread_id = await asyncio.get_event_loop().run_in_executor(None, input, "Enter thread_id: ")
                    thread_id = thread_id.strip()

                if not thread_id:
                    console.print("[yellow]No thread_id provided[/yellow]")
                    continue

                content = await asyncio.get_event_loop().run_in_executor(None, input, "Enter message content: ")
                content = content.strip()

                if not content:
                    console.print("[yellow]No content provided[/yellow]")
                    continue

                console.print("\n[yellow]Sending manager message (assistant stays active)...[/yellow]")
                result = await client.send_manager_message(client.company_id, thread_id, content, pause_assistant=False)

                if "error" in result:
                    console.print(
                        Panel(
                            json.dumps(result, indent=2),
                            title=f"[red]Failed ({result.get('status_code', '?')})[/red]",
                            border_style="red",
                        )
                    )
                else:
                    console.print(
                        Panel(
                            json.dumps(result, indent=2, default=str),
                            title="[green]Message Sent[/green]",
                            border_style="green",
                        )
                    )
                    console.print("\n[bold yellow]✓ Assistant remains active for this thread[/bold yellow]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        elif choice == "q":
            console.print("\n[yellow]Exiting...[/yellow]")
            break


async def main():
    console.print(
        Panel.fit(
            "[bold cyan]Unified Connector Model Test[/bold cyan]\n\n"
            "Tests Plan 009: Sales Envelope Abstraction\n"
            "Tests Plan 010: Backend Router\n"
            "- Connector CRUD operations\n"
            "- API key management\n"
            "- Internal validation endpoints\n"
            "- Manager message routing\n"
            "- Assistant disable/enable",
            border_style="cyan",
        )
    )

    client = ConnectorTestClient()

    if not await setup_environment(client):
        sys.exit(1)

    await interactive_menu(client)

    console.print("\n[bold green]Done![/bold green]")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
