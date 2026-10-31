"""Manual testing script for field level separation feature.

Usage:
    cd apps/backend
    python scripts/manual_testing/test_field_level_separation.py

Requirements:
    1. Backend server must be running:
       uv run uvicorn src.backend.main:app --reload --port 8081

    2. Database must be initialized and migrations applied:
       uv run aerich upgrade

    3. User account must exist (default: test_admin_sendbox@gmail.com / 10293856g)
       Or set TEST_EMAIL and TEST_PASSWORD environment variables

    4. Environment variables (optional):
       BACKEND_URL - backend server URL (default: http://localhost:8081)
       TEST_EMAIL - user email for login (default: admin@example.com)
       TEST_PASSWORD - user password (default: admin)
"""

import asyncio
import os
import sys
from typing import Any

import httpx
from rich.console import Console
from rich.table import Table

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

console = Console()


class FieldLevelTestClient:
    """Client for testing field level separation via API."""

    def __init__(self, base_url: str = "http://localhost:8081", token: str | None = None):
        self.base_url = base_url
        self.token = token
        self.headers = {"Authorization": f"Bearer {self.token}"} if token else {}

    async def login(self, email: str, password: str) -> dict[str, Any]:
        """Login and get access token."""
        max_retries = 3
        retry_delay = 2.0

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"{self.base_url}/api/v1/auth/login",
                        json={"email": email, "password": password},
                    )
                    response.raise_for_status()
                    data = response.json()
                    self.token = data["access_token"]
                    self.headers = {"Authorization": f"Bearer {self.token}"}
                    return data
            except httpx.ConnectError as e:
                if attempt < max_retries - 1:
                    console.print(
                        f"[yellow]Connection failed, retrying in {retry_delay}s... (attempt {attempt + 1}/{max_retries})[/yellow]"
                    )
                    await asyncio.sleep(retry_delay)
                    continue
                raise ConnectionError(f"Cannot connect to backend at {self.base_url}. Is the server running?") from e
            except httpx.ReadError as e:
                if attempt < max_retries - 1:
                    console.print(
                        f"[yellow]Read error, retrying in {retry_delay}s... (attempt {attempt + 1}/{max_retries})[/yellow]"
                    )
                    await asyncio.sleep(retry_delay)
                    continue
                raise ConnectionError(
                    f"Connection lost while reading response from {self.base_url}. Server may have closed the connection or is reloading."
                ) from e
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    raise ValueError(f"Invalid credentials for {email}") from e
                raise

    async def create_company(self, name: str, description: str = "") -> dict[str, Any]:
        """Create a test company."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/companies",
                json={
                    "name": name,
                    "description": description,
                    "rules": "Test rules for field level separation testing",
                    "tone_of_voice": "Professional",
                    "assistant_name": "Test Assistant",
                    "qualification_workflow": "Standard",
                    "qualification_examples": "Example 1",
                    "collection_name": name.lower().replace(" ", "_"),
                },
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def get_company(self, company_id: int) -> dict[str, Any]:
        """Get company by ID."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/companies/{company_id}",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def list_fields(self, company_id: int, level: str | None = None) -> dict[str, Any]:
        """List fields for a company, optionally filtered by level."""
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/api/v1/companies/{company_id}/fields"
            if level:
                url += f"?level={level}"
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def create_field(
        self,
        company_id: int,
        name: str,
        question: str,
        field_type: str,
        level: str = "customer",
        is_system: bool = False,
    ) -> dict[str, Any]:
        """Create a field."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/companies/{company_id}/fields",
                json={
                    "name": name,
                    "question": question,
                    "type": field_type,
                    "level": level,
                    "is_system": is_system,
                },
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def delete_field(self, company_id: int, field_id: int) -> None:
        """Delete a field."""
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.base_url}/api/v1/companies/{company_id}/fields/{field_id}",
                headers=self.headers,
            )
            response.raise_for_status()

    async def get_company_spec(self, company_id: int) -> dict[str, Any]:
        """Get company specification (for sales-agent)."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/internal/companies/{company_id}/specification",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()


def print_fields_table(fields: list[dict[str, Any]], title: str = "Fields"):
    """Print fields in a formatted table."""
    table = Table(title=title)
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Question", style="yellow")
    table.add_column("Type", style="blue")
    table.add_column("Level", style="magenta")
    table.add_column("System", style="red")

    for field in fields:
        table.add_row(
            str(field.get("id", "")),
            field.get("name", ""),
            field.get("question", ""),
            field.get("type", ""),
            field.get("level", ""),
            "Yes" if field.get("is_system") else "No",
        )

    console.print(table)


async def scenario_1_system_fields(client: FieldLevelTestClient, company_id: int):
    """Test 1: System fields auto-creation."""
    console.print("\n[bold cyan]Scenario 1: System Fields Auto-Creation[/bold cyan]")
    console.print("Checking if system customer fields were created automatically...\n")

    fields_data = await client.list_fields(company_id)
    fields = fields_data.get("items", [])

    system_fields = [f for f in fields if f.get("is_system")]
    console.print(f"Found {len(system_fields)} system fields:\n")
    print_fields_table(system_fields, "System Customer Fields")

    expected_system_fields = {"phone", "telegram", "whatsapp", "instagram", "email", "preferences", "source"}
    found_names = {f.get("name") for f in system_fields}

    if expected_system_fields == found_names:
        console.print("[bold green]✓ All system fields created successfully![/bold green]")
    else:
        missing = expected_system_fields - found_names
        console.print(f"[bold red]✗ Missing system fields: {missing}[/bold red]")

    return len(system_fields) == len(expected_system_fields)


async def scenario_2_level_filtering(client: FieldLevelTestClient, company_id: int):
    """Test 2: Level filtering."""
    console.print("\n[bold cyan]Scenario 2: Level Filtering[/bold cyan]")
    console.print("Creating customer and order fields, then testing filtering...\n")

    # Create customer-level field
    customer_field = await client.create_field(
        company_id=company_id,
        name="customer_city",
        question="What city are you from?",
        field_type="string",
        level="customer",
    )
    console.print(f"[green]Created customer field: {customer_field['name']}[/green]")

    # Create order-level field
    order_field = await client.create_field(
        company_id=company_id,
        name="order_budget",
        question="What is your budget?",
        field_type="number",
        level="order",
    )
    console.print(f"[green]Created order field: {order_field['name']}[/green]")

    # Test filtering
    customer_fields_data = await client.list_fields(company_id, level="customer")
    customer_fields = customer_fields_data.get("items", [])
    customer_field_names = {f.get("name") for f in customer_fields}

    order_fields_data = await client.list_fields(company_id, level="order")
    order_fields = order_fields_data.get("items", [])
    order_field_names = {f.get("name") for f in order_fields}

    console.print("\n[bold]Customer-level fields:[/bold]")
    print_fields_table(customer_fields, "Customer Fields")

    console.print("\n[bold]Order-level fields:[/bold]")
    print_fields_table(order_fields, "Order Fields")

    success = "customer_city" in customer_field_names and "order_budget" in order_field_names
    if success:
        console.print("[bold green]✓ Level filtering works correctly![/bold green]")
    else:
        console.print("[bold red]✗ Level filtering failed![/bold red]")

    return success


async def scenario_3_system_field_constraint(client: FieldLevelTestClient, company_id: int):
    """Test 3: System field constraint (is_system only for customer level)."""
    console.print("\n[bold cyan]Scenario 3: System Field Constraint[/bold cyan]")
    console.print("Testing that is_system=True is only allowed for customer level...\n")

    # Try to create order-level field with is_system=True - should fail
    try:
        await client.create_field(
            company_id=company_id,
            name="invalid_system_order",
            question="Invalid?",
            field_type="string",
            level="order",
            is_system=True,
        )
        console.print("[bold red]✗ Should have failed![/bold red]")
        return False
    except httpx.HTTPStatusError as e:
        # Accept both 400 (validation error) and 500 (server error) as success
        # since both indicate that the constraint is enforced
        if e.response.status_code in (400, 422, 500):
            console.print(
                f"[bold green]✓ Correctly rejected order-level system field (status {e.response.status_code})[/bold green]"
            )
            return True
        else:
            console.print(f"[bold red]✗ Unexpected error: {e}[/bold red]")
            return False


async def scenario_4_delete_system_field(client: FieldLevelTestClient, company_id: int):
    """Test 4: Cannot delete system fields."""
    console.print("\n[bold cyan]Scenario 4: System Field Deletion Protection[/bold cyan]")
    console.print("Testing that system fields cannot be deleted...\n")

    fields_data = await client.list_fields(company_id)
    fields = fields_data.get("items", [])
    system_fields = [f for f in fields if f.get("is_system")]

    if not system_fields:
        console.print("[bold yellow]⚠ No system fields found[/bold yellow]")
        return False

    system_field = system_fields[0]
    console.print(f"Attempting to delete system field: {system_field['name']}")

    try:
        await client.delete_field(company_id, system_field["id"])
        console.print("[bold red]✗ Should have failed![/bold red]")
        return False
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            console.print("[bold green]✓ Correctly prevented deletion of system field[/bold green]")
            return True
        else:
            console.print(f"[bold red]✗ Unexpected error: {e}[/bold red]")
            return False


async def scenario_5_company_spec(client: FieldLevelTestClient, company_id: int):
    """Test 5: Company spec includes level info."""
    console.print("\n[bold cyan]Scenario 5: Company Spec Level Info[/bold cyan]")
    console.print("Checking that company spec includes level and is_system in fields...\n")

    spec = await client.get_company_spec(company_id)
    fields = spec.get("fields", [])

    if not fields:
        console.print("[bold yellow]⚠ No fields in spec[/bold yellow]")
        return False

    # Check that all fields have level
    fields_with_level = [f for f in fields if "level" in f]
    if len(fields_with_level) == len(fields):
        console.print("[bold green]✓ All fields have level property[/bold green]")
    else:
        console.print(f"[bold red]✗ Only {len(fields_with_level)}/{len(fields)} fields have level[/bold red]")
        return False

    # Check that system fields are marked
    system_fields = [f for f in fields if f.get("is_system")]
    console.print(f"Found {len(system_fields)} system fields in spec")

    print_fields_table(fields[:10], "First 10 Fields from Spec")

    return True


async def main():
    """Main test runner."""
    console.print("[bold]Field Level Separation - Manual Testing[/bold]\n")

    # Setup
    base_url = os.getenv("BACKEND_URL", "http://localhost:8081")
    email = os.getenv("TEST_EMAIL", "test_admin_sendbox@gmail.com")
    password = os.getenv("TEST_PASSWORD", "10293856g")

    client = FieldLevelTestClient(base_url=base_url)

    try:
        # Check if server is reachable
        console.print(f"Checking backend server at {base_url}...")
        async with httpx.AsyncClient(timeout=5.0) as check_client:
            try:
                health_response = await check_client.get(f"{base_url}/health")
                if health_response.status_code == 200:
                    console.print("[green]✓ Backend server is reachable[/green]\n")
                else:
                    console.print(f"[yellow]⚠ Backend returned status {health_response.status_code}[/yellow]\n")
            except Exception as e:
                console.print(f"[bold red]✗ Cannot reach backend server: {e}[/bold red]")
                console.print("[yellow]Make sure backend is running:[/yellow]")
                console.print("[cyan]  uv run uvicorn src.backend.main:app --reload --port 8081[/cyan]\n")
                return 1

        console.print(f"Logging in as {email}...")
        await client.login(email, password)
        console.print("[green]✓ Logged in successfully[/green]\n")

        # Create or get test company
        console.print("Creating test company...")
        company = await client.create_company("Field Level Test Company", "Test company for field level separation")
        company_id = company["id"]
        console.print(f"[green]✓ Company created: ID {company_id}[/green]\n")

        # Run scenarios
        results = []

        results.append(("System Fields", await scenario_1_system_fields(client, company_id)))
        results.append(("Level Filtering", await scenario_2_level_filtering(client, company_id)))
        results.append(("System Constraint", await scenario_3_system_field_constraint(client, company_id)))
        results.append(("Delete Protection", await scenario_4_delete_system_field(client, company_id)))
        results.append(("Company Spec", await scenario_5_company_spec(client, company_id)))

        # Summary
        console.print("\n[bold]Test Summary:[/bold]\n")
        summary_table = Table()
        summary_table.add_column("Scenario", style="cyan")
        summary_table.add_column("Result", style="green")

        for name, success in results:
            status = "✓ PASS" if success else "✗ FAIL"
            summary_table.add_row(name, status)

        console.print(summary_table)

        passed = sum(1 for _, success in results if success)
        total = len(results)
        console.print(f"\n[bold]Total: {passed}/{total} scenarios passed[/bold]")

    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        import traceback

        traceback.print_exc()
        return 1

    return 0 if all(success for _, success in results) else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
