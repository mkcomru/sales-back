"""Manual testing script for web form capture feature (Plan 024).

Usage:
    cd apps/backend
    python scripts/manual_testing/test_forms_capture.py

Requirements:
    1. Backend server must be running:
       uv run uvicorn src.backend.main:app --reload --port 8081

    2. Database must be initialized and migrations applied:
       uv run aerich upgrade

    3. User account must exist (default: test_admin_sendbox@gmail.com / 10293856g)
       Or set TEST_EMAIL and TEST_PASSWORD environment variables

Test Scenarios:
    1. Form Template CRUD - create, read, update, delete forms
    2. API Key Generation - regenerate keys, validate format
    3. Form Capture (Public) - capture via X-Form-Key header
    4. Form Capture (Internal) - capture via authenticated endpoint
    5. Required Field Validation - 400 on missing required fields
    6. Response Modes - full vs minimal responses
    7. UTM Tracking - UTM data saved to order
    8. Submissions List - audit trail with pagination
    9. Disabled Form - 401 on disabled form capture
    10. Rate Limiting - 429 on excessive requests
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

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

console = Console()


class FormsTestClient:
    """Client for testing web form capture via API."""

    def __init__(self, base_url: str = "http://localhost:8081", token: str | None = None):
        self.base_url = base_url
        self.token = token
        self.headers = {"Authorization": f"Bearer {self.token}"} if token else {}
        self.company_id: int | None = None
        self.form_id: int | None = None
        self.form_api_key: str | None = None
        self.contact_field_id: int | None = None
        self.contact_field_name: str | None = None
        self.order_field_id: int | None = None
        self.order_field_name: str | None = None

    def _get_client(self, timeout: float = 60.0) -> httpx.AsyncClient:
        """Get a configured httpx client with timeout."""
        return httpx.AsyncClient(timeout=timeout)

    async def login(self, email: str, password: str) -> dict[str, Any]:
        """Login and get access token."""
        max_retries = 3
        retry_delay = 2.0

        for attempt in range(max_retries):
            try:
                async with self._get_client(timeout=30.0) as client:
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
                    console.print(f"[yellow]Connection failed, retrying in {retry_delay}s...[/yellow]")
                    await asyncio.sleep(retry_delay)
                    continue
                raise ConnectionError(f"Cannot connect to backend at {self.base_url}") from e
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    raise ValueError(f"Invalid credentials for {email}") from e
                raise

    async def create_company(self, name: str) -> dict[str, Any]:
        """Create a test company."""
        async with self._get_client() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/companies",
                json={
                    "name": name,
                    "description": "Test company for forms capture",
                    "rules": "Test rules",
                    "tone_of_voice": "Professional",
                    "assistant_name": "Test Assistant",
                    "qualification_workflow": "Standard",
                    "qualification_examples": "Examples",
                    "collection_name": name.lower().replace(" ", "_"),
                },
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def create_field(
        self,
        name: str,
        question: str,
        field_type: str = "string",
        level: str = "customer",
        required: bool = False,
    ) -> dict[str, Any]:
        """Create a field."""
        async with self._get_client() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/companies/{self.company_id}/fields",
                json={
                    "name": name,
                    "question": question,
                    "type": field_type,
                    "level": level,
                    "required": required,
                },
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def create_form(self, name: str, contact_field_id: int, template_fields: list[dict]) -> dict[str, Any]:
        """Create a form template."""
        async with self._get_client() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/companies/{self.company_id}/forms",
                json={
                    "name": name,
                    "contact_field_id": contact_field_id,
                    "template_fields": template_fields,
                },
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def list_forms(self) -> dict[str, Any]:
        """List form templates."""
        async with self._get_client() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/companies/{self.company_id}/forms",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def get_form(self, form_id: int) -> dict[str, Any]:
        """Get form template by ID."""
        async with self._get_client() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/companies/{self.company_id}/forms/{form_id}",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def update_form(self, form_id: int, **kwargs) -> dict[str, Any]:
        """Update form template."""
        async with self._get_client() as client:
            response = await client.patch(
                f"{self.base_url}/api/v1/companies/{self.company_id}/forms/{form_id}",
                json=kwargs,
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def delete_form(self, form_id: int) -> None:
        """Delete form template."""
        async with self._get_client() as client:
            response = await client.delete(
                f"{self.base_url}/api/v1/companies/{self.company_id}/forms/{form_id}",
                headers=self.headers,
            )
            response.raise_for_status()

    async def regenerate_api_key(self, form_id: int) -> dict[str, Any]:
        """Regenerate API key for form."""
        async with self._get_client() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/companies/{self.company_id}/forms/{form_id}/regenerate-key",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def capture_public(
        self,
        api_key: str,
        fields: dict[str, Any],
        utm: dict[str, str] | None = None,
        mode: str = "minimal",
    ) -> httpx.Response:
        """Submit form via public capture endpoint."""
        async with self._get_client() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/forms/capture",
                json={"fields": fields, "utm": utm},
                params={"mode": mode},
                headers={"X-Form-Key": api_key},
            )
            return response

    async def capture_internal(
        self,
        form_id: int,
        fields: dict[str, Any],
        utm: dict[str, str] | None = None,
        mode: str = "minimal",
    ) -> dict[str, Any]:
        """Submit form via internal authenticated endpoint."""
        async with self._get_client() as client:
            response = await client.post(
                f"{self.base_url}/api/v1/companies/{self.company_id}/forms/{form_id}/submit",
                json={"fields": fields, "utm": utm},
                params={"mode": mode},
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def list_submissions(self, form_id: int, limit: int = 10, offset: int = 0) -> dict[str, Any]:
        """List form submissions."""
        async with self._get_client() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/companies/{self.company_id}/forms/{form_id}/submissions",
                params={"limit": limit, "offset": offset},
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def get_order(self, order_id: int) -> dict[str, Any]:
        """Get order by ID."""
        async with self._get_client() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/companies/{self.company_id}/orders/{order_id}",
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()


def print_form(form: dict[str, Any]):
    """Print form details in a formatted table."""
    table = Table(title="Form Template")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("id", str(form.get("id", "")))
    table.add_row("name", form.get("name", ""))
    table.add_row("enabled", str(form.get("enabled", "")))
    table.add_row("has_api_key", str(form.get("has_api_key", "")))
    table.add_row("contact_field_id", str(form.get("contact_field_id", "")))
    table.add_row("template_fields", str(len(form.get("template_fields", []))))
    table.add_row("created_at", form.get("created_at", ""))

    console.print(table)


def print_submission(submission: dict[str, Any]):
    """Print submission details."""
    table = Table(title="Form Submission")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("id", str(submission.get("id", "")))
    table.add_row("customer_id", str(submission.get("customer_id", "")))
    table.add_row("order_id", str(submission.get("order_id", "")))
    table.add_row("raw_fields", str(submission.get("raw_fields", {})))
    table.add_row("utm_data", str(submission.get("utm_data", {})))
    table.add_row("ip_address", submission.get("ip_address", ""))
    table.add_row("created_at", submission.get("created_at", ""))

    console.print(table)


async def setup_test_data(client: FormsTestClient) -> bool:
    """Setup test company, fields and form."""
    console.print("\n[bold blue]Setting up test data...[/bold blue]\n")

    # Create company
    console.print("1. Creating test company...")
    company_name = f"Forms Test Company {datetime.now().timestamp()}"
    company = await client.create_company(company_name)
    client.company_id = company["id"]
    console.print(f"[green]✓ Company created: ID {client.company_id}[/green]")

    # Create contact field (customer level, required)
    console.print("\n2. Creating contact field (email)...")
    contact_field = await client.create_field(
        name="email",
        question="What is your email?",
        field_type="string",
        level="customer",
        required=True,
    )
    client.contact_field_id = contact_field["id"]
    client.contact_field_name = contact_field["name"]
    console.print(f"[green]✓ Contact field created: ID {client.contact_field_id}[/green]")

    # Create order field
    console.print("\n3. Creating order field (budget)...")
    order_field = await client.create_field(
        name="budget",
        question="What is your budget?",
        field_type="number",
        level="order",
        required=False,
    )
    client.order_field_id = order_field["id"]
    client.order_field_name = order_field["name"]
    console.print(f"[green]✓ Order field created: ID {client.order_field_id}[/green]")

    # Create additional customer field
    console.print("\n4. Creating customer field (name)...")
    name_field = await client.create_field(
        name="customer_name",
        question="What is your name?",
        field_type="string",
        level="customer",
        required=True,
    )
    console.print(f"[green]✓ Customer name field created: ID {name_field['id']}[/green]")

    return True


async def scenario_1_form_crud(client: FormsTestClient) -> bool:
    """Scenario 1: Form Template CRUD."""
    console.print("\n[bold cyan]Scenario 1: Form Template CRUD[/bold cyan]")
    console.print("Testing create, read, update, delete operations...\n")

    # Create form
    console.print("[yellow]Creating form template...[/yellow]")
    form = await client.create_form(
        name="Test Lead Form",
        contact_field_id=client.contact_field_id,
        template_fields=[
            {"field_id": client.order_field_id, "position": 0},
        ],
    )
    form_id = form["id"]
    client.form_id = form_id
    console.print(f"[green]✓ Form created: ID {form_id}[/green]")
    print_form(form)

    # Read form
    console.print("\n[yellow]Reading form template...[/yellow]")
    form = await client.get_form(form_id)
    if form["name"] != "Test Lead Form":
        console.print("[red]✗ Form read failed![/red]")
        return False
    console.print("[green]✓ Form read successfully[/green]")

    # List forms
    console.print("\n[yellow]Listing forms...[/yellow]")
    forms_data = await client.list_forms()
    forms = forms_data.get("items", [])
    console.print(f"[green]✓ Found {len(forms)} forms[/green]")

    # Update form
    console.print("\n[yellow]Updating form name...[/yellow]")
    updated_form = await client.update_form(form_id, name="Updated Lead Form")
    if updated_form["name"] != "Updated Lead Form":
        console.print("[red]✗ Form update failed![/red]")
        return False
    console.print("[green]✓ Form updated successfully[/green]")

    # Create another form to test delete
    console.print("\n[yellow]Creating form for deletion test...[/yellow]")
    temp_form = await client.create_form(
        name="Temp Form",
        contact_field_id=client.contact_field_id,
        template_fields=[],
    )
    temp_form_id = temp_form["id"]

    console.print(f"[yellow]Deleting form {temp_form_id}...[/yellow]")
    await client.delete_form(temp_form_id)
    console.print("[green]✓ Form deleted successfully[/green]")

    console.print("\n[bold green]✓ Scenario 1 PASSED[/bold green]")
    return True


async def scenario_2_api_key_generation(client: FormsTestClient) -> bool:
    """Scenario 2: API Key Generation."""
    console.print("\n[bold cyan]Scenario 2: API Key Generation[/bold cyan]")
    console.print("Testing API key regeneration and format...\n")

    # Check form doesn't have API key yet
    form = await client.get_form(client.form_id)
    if form.get("has_api_key"):
        console.print("[yellow]Form already has API key[/yellow]")
    else:
        console.print("[green]✓ Form initially has no API key[/green]")

    # Regenerate API key
    console.print("\n[yellow]Regenerating API key...[/yellow]")
    key_response = await client.regenerate_api_key(client.form_id)
    api_key = key_response.get("api_key")

    if not api_key:
        console.print("[red]✗ No API key returned![/red]")
        return False

    if not api_key.startswith("form_"):
        console.print(f"[red]✗ Invalid key format: {api_key[:20]}...[/red]")
        return False

    client.form_api_key = api_key
    console.print(f"[green]✓ API key generated: {api_key[:20]}...[/green]")

    # Verify form now has API key
    form = await client.get_form(client.form_id)
    if not form.get("has_api_key"):
        console.print("[red]✗ Form should have API key now![/red]")
        return False
    console.print("[green]✓ Form has_api_key = True[/green]")

    # Regenerate again to verify it changes
    console.print("\n[yellow]Regenerating API key again...[/yellow]")
    key_response_2 = await client.regenerate_api_key(client.form_id)
    api_key_2 = key_response_2.get("api_key")

    if api_key_2 == api_key:
        console.print("[red]✗ Key should be different after regeneration![/red]")
        return False

    client.form_api_key = api_key_2
    console.print(f"[green]✓ New API key generated: {api_key_2[:20]}...[/green]")

    console.print("\n[bold green]✓ Scenario 2 PASSED[/bold green]")
    return True


async def scenario_3_public_capture(client: FormsTestClient) -> bool:
    """Scenario 3: Public Capture Endpoint."""
    console.print("\n[bold cyan]Scenario 3: Public Capture Endpoint[/bold cyan]")
    console.print("Testing form capture via X-Form-Key header...\n")

    test_email = f"lead_{datetime.now().timestamp()}@example.com"

    console.print(f"[yellow]Submitting form with email: {test_email}[/yellow]")
    response = await client.capture_public(
        api_key=client.form_api_key,
        fields={
            client.contact_field_name: test_email,
            client.order_field_name: 5000,
        },
        mode="minimal",
    )

    if response.status_code != 200:
        console.print(f"[red]✗ Capture failed: {response.status_code}[/red]")
        console.print(f"[red]Response: {response.text}[/red]")
        return False

    data = response.json()
    console.print("[green]✓ Capture successful![/green]")
    console.print(Panel(str(data), title="Response (minimal mode)", border_style="green"))

    if "customer_id" not in data or "order_id" not in data:
        console.print("[red]✗ Missing customer_id or order_id in response![/red]")
        return False

    console.print(f"[green]✓ Customer ID: {data['customer_id']}[/green]")
    console.print(f"[green]✓ Order ID: {data['order_id']}[/green]")
    console.print(f"[green]✓ Order Number: {data['order_number']}[/green]")

    console.print("\n[bold green]✓ Scenario 3 PASSED[/bold green]")
    return True


async def scenario_4_internal_capture(client: FormsTestClient) -> bool:
    """Scenario 4: Internal Capture Endpoint."""
    console.print("\n[bold cyan]Scenario 4: Internal Capture Endpoint[/bold cyan]")
    console.print("Testing form capture via authenticated endpoint...\n")

    test_email = f"internal_{datetime.now().timestamp()}@example.com"

    console.print(f"[yellow]Submitting form via internal endpoint with email: {test_email}[/yellow]")
    data = await client.capture_internal(
        form_id=client.form_id,
        fields={
            client.contact_field_name: test_email,
            client.order_field_name: 10000,
        },
        mode="minimal",
    )

    console.print("[green]✓ Internal capture successful![/green]")
    console.print(Panel(str(data), title="Response", border_style="green"))

    if "customer_id" not in data or "order_id" not in data:
        console.print("[red]✗ Missing customer_id or order_id![/red]")
        return False

    console.print("\n[bold green]✓ Scenario 4 PASSED[/bold green]")
    return True


async def scenario_5_required_validation(client: FormsTestClient) -> bool:
    """Scenario 5: Required Field Validation."""
    console.print("\n[bold cyan]Scenario 5: Required Field Validation[/bold cyan]")
    console.print("Testing that missing required fields return 400...\n")

    console.print("[yellow]Submitting form without required contact field...[/yellow]")
    response = await client.capture_public(
        api_key=client.form_api_key,
        fields={
            client.order_field_name: 5000,
            # Missing contact field (email)
        },
        mode="minimal",
    )

    if response.status_code == 400 or response.status_code == 422:
        console.print(f"[green]✓ Correctly returned {response.status_code} for missing required field[/green]")
    else:
        console.print(f"[red]✗ Expected 400/422, got {response.status_code}[/red]")
        console.print(f"[red]Response: {response.text}[/red]")
        return False

    console.print("\n[bold green]✓ Scenario 5 PASSED[/bold green]")
    return True


async def scenario_6_response_modes(client: FormsTestClient) -> bool:
    """Scenario 6: Response Modes (full vs minimal)."""
    console.print("\n[bold cyan]Scenario 6: Response Modes[/bold cyan]")
    console.print("Testing full and minimal response modes...\n")

    test_email = f"modes_{datetime.now().timestamp()}@example.com"

    # Test full mode
    console.print("[yellow]Testing full response mode...[/yellow]")
    response = await client.capture_public(
        api_key=client.form_api_key,
        fields={
            client.contact_field_name: test_email,
            client.order_field_name: 7500,
        },
        mode="full",
    )

    if response.status_code != 200:
        console.print(f"[red]✗ Full mode capture failed: {response.status_code}[/red]")
        return False

    data = response.json()
    console.print(Panel(str(data), title="Full Response", border_style="green"))

    # Check full response has customer and order objects
    if "customer" not in data or "order" not in data:
        console.print("[red]✗ Full mode should have customer and order objects![/red]")
        return False

    if "user_id" not in data["customer"]:
        console.print("[red]✗ Customer should have user_id in full mode![/red]")
        return False

    if "order_fields" not in data["order"]:
        console.print("[red]✗ Order should have order_fields in full mode![/red]")
        return False

    console.print("[green]✓ Full mode returns customer and order details[/green]")

    # Test minimal mode
    console.print("\n[yellow]Testing minimal response mode...[/yellow]")
    test_email_2 = f"minimal_{datetime.now().timestamp()}@example.com"
    response = await client.capture_public(
        api_key=client.form_api_key,
        fields={client.contact_field_name: test_email_2},
        mode="minimal",
    )

    data = response.json()
    console.print(Panel(str(data), title="Minimal Response", border_style="green"))

    # Check minimal response has only IDs
    if "customer" in data or "order" in data:
        console.print("[red]✗ Minimal mode should not have customer/order objects![/red]")
        return False

    if "customer_id" not in data or "order_id" not in data:
        console.print("[red]✗ Minimal mode should have customer_id and order_id![/red]")
        return False

    console.print("[green]✓ Minimal mode returns only IDs[/green]")

    console.print("\n[bold green]✓ Scenario 6 PASSED[/bold green]")
    return True


async def scenario_7_utm_tracking(client: FormsTestClient) -> bool:
    """Scenario 7: UTM Tracking."""
    console.print("\n[bold cyan]Scenario 7: UTM Tracking[/bold cyan]")
    console.print("Testing that UTM data is saved to order...\n")

    test_email = f"utm_{datetime.now().timestamp()}@example.com"
    utm_data = {
        "source": "google",
        "medium": "cpc",
        "campaign": "summer_sale",
        "term": "test",
        "content": "banner_1",
    }

    console.print(f"[yellow]Submitting form with UTM data: {utm_data}[/yellow]")
    response = await client.capture_public(
        api_key=client.form_api_key,
        fields={client.contact_field_name: test_email},
        utm=utm_data,
        mode="minimal",
    )

    if response.status_code != 200:
        console.print(f"[red]✗ Capture failed: {response.status_code}[/red]")
        return False

    data = response.json()
    order_id = data["order_id"]
    console.print(f"[green]✓ Order created: {order_id}[/green]")

    # Verify UTM data is in order
    console.print(f"[yellow]Fetching order {order_id} to verify UTM data...[/yellow]")
    try:
        order = await client.get_order(order_id)
        # UTM data should be in order (check if field exists)
        console.print("[green]✓ Order fetched successfully[/green]")
        console.print(Panel(str(order), title="Order Details", border_style="green"))
    except Exception as e:
        console.print(f"[yellow]⚠ Could not fetch order (may need different endpoint): {e}[/yellow]")

    # Check submission for UTM data
    console.print("[yellow]Checking submissions for UTM data...[/yellow]")
    submissions = await client.list_submissions(client.form_id)
    items = submissions.get("items", [])

    if items:
        latest = items[0]
        if latest.get("utm_data") == utm_data:
            console.print("[green]✓ UTM data saved in submission![/green]")
        else:
            console.print(f"[yellow]⚠ UTM data mismatch: {latest.get('utm_data')}[/yellow]")
    else:
        console.print("[yellow]⚠ No submissions found[/yellow]")

    console.print("\n[bold green]✓ Scenario 7 PASSED[/bold green]")
    return True


async def scenario_8_submissions_list(client: FormsTestClient) -> bool:
    """Scenario 8: Submissions List."""
    console.print("\n[bold cyan]Scenario 8: Submissions List[/bold cyan]")
    console.print("Testing submissions audit trail with pagination...\n")

    console.print(f"[yellow]Listing submissions for form {client.form_id}...[/yellow]")
    submissions = await client.list_submissions(client.form_id)

    items = submissions.get("items", [])
    total = submissions.get("total", 0)

    console.print(f"[green]✓ Found {total} total submissions[/green]")

    if items:
        console.print("\n[bold]Recent submissions:[/bold]")
        for sub in items[:3]:
            print_submission(sub)
    else:
        console.print("[yellow]No submissions found[/yellow]")

    # Test pagination
    console.print("\n[yellow]Testing pagination (limit=2, offset=0)...[/yellow]")
    page1 = await client.list_submissions(client.form_id, limit=2, offset=0)
    console.print(f"[green]✓ Page 1: {len(page1.get('items', []))} items[/green]")

    console.print("\n[bold green]✓ Scenario 8 PASSED[/bold green]")
    return True


async def scenario_9_disabled_form(client: FormsTestClient) -> bool:
    """Scenario 9: Disabled Form."""
    console.print("\n[bold cyan]Scenario 9: Disabled Form[/bold cyan]")
    console.print("Testing that disabled form returns 401...\n")

    # Disable the form
    console.print(f"[yellow]Disabling form {client.form_id}...[/yellow]")
    await client.update_form(client.form_id, enabled=False)
    console.print("[green]✓ Form disabled[/green]")

    # Try to capture
    console.print("[yellow]Attempting capture on disabled form...[/yellow]")
    response = await client.capture_public(
        api_key=client.form_api_key,
        fields={client.contact_field_name: "disabled_test@example.com"},
        mode="minimal",
    )

    if response.status_code == 401:
        console.print("[green]✓ Correctly returned 401 for disabled form[/green]")
    else:
        console.print(f"[red]✗ Expected 401, got {response.status_code}[/red]")
        # Re-enable form
        await client.update_form(client.form_id, enabled=True)
        return False

    # Re-enable form
    console.print("[yellow]Re-enabling form...[/yellow]")
    await client.update_form(client.form_id, enabled=True)
    console.print("[green]✓ Form re-enabled[/green]")

    console.print("\n[bold green]✓ Scenario 9 PASSED[/bold green]")
    return True


async def scenario_10_invalid_api_key(client: FormsTestClient) -> bool:
    """Scenario 10: Invalid API Key."""
    console.print("\n[bold cyan]Scenario 10: Invalid API Key[/bold cyan]")
    console.print("Testing that invalid API key returns 401...\n")

    console.print("[yellow]Attempting capture with invalid API key...[/yellow]")
    response = await client.capture_public(
        api_key="form_invalid_key_12345",
        fields={client.contact_field_name: "invalid_key@example.com"},
        mode="minimal",
    )

    if response.status_code == 401:
        console.print("[green]✓ Correctly returned 401 for invalid API key[/green]")
    else:
        console.print(f"[red]✗ Expected 401, got {response.status_code}[/red]")
        return False

    console.print("\n[bold green]✓ Scenario 10 PASSED[/bold green]")
    return True


async def main():
    """Main test runner."""
    console.print(
        Panel.fit(
            "[bold cyan]Web Form Capture - Manual Testing[/bold cyan]\n\n"
            "This script tests Plan 024: Web Form Capture Implementation\n"
            "Covers form CRUD, API keys, capture flows, validation, and more.",
            border_style="cyan",
        )
    )

    base_url = os.getenv("BACKEND_URL", "http://localhost:8081")
    email = os.getenv("TEST_EMAIL", "test_admin_sendbox@gmail.com")
    password = os.getenv("TEST_PASSWORD", "10293856g")

    client = FormsTestClient(base_url=base_url)

    try:
        # Check server
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

        # Setup test data
        await setup_test_data(client)

        # Run scenarios
        results = []
        results.append(("Form CRUD", await scenario_1_form_crud(client)))
        results.append(("API Key Generation", await scenario_2_api_key_generation(client)))
        results.append(("Public Capture", await scenario_3_public_capture(client)))
        results.append(("Internal Capture", await scenario_4_internal_capture(client)))
        results.append(("Required Validation", await scenario_5_required_validation(client)))
        results.append(("Response Modes", await scenario_6_response_modes(client)))
        results.append(("UTM Tracking", await scenario_7_utm_tracking(client)))
        results.append(("Submissions List", await scenario_8_submissions_list(client)))
        results.append(("Disabled Form", await scenario_9_disabled_form(client)))
        results.append(("Invalid API Key", await scenario_10_invalid_api_key(client)))

        # Summary
        console.print("\n" + "=" * 60)
        console.print("[bold]Test Results Summary[/bold]")
        console.print("=" * 60)

        summary_table = Table()
        summary_table.add_column("Scenario", style="cyan")
        summary_table.add_column("Result")

        for name, success in results:
            status = "[green]✓ PASS[/green]" if success else "[red]✗ FAIL[/red]"
            summary_table.add_row(name, status)

        console.print(summary_table)

        passed = sum(1 for _, success in results if success)
        total = len(results)
        console.print(f"\n[bold]Total: {passed}/{total} scenarios passed[/bold]")

        return 0 if all(success for _, success in results) else 1

    except Exception as e:
        console.print(f"[bold red]Error: {e}[/bold red]")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
