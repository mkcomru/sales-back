#!/usr/bin/env python3
"""Sanity check for pagination endpoints.

Creates 2 records of each entity and verifies all paginated list endpoints return 200.

Usage:
    cd scripts/manual_testing
    python test_pagination_sanity.py
"""

import asyncio
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx
from rich.console import Console
from rich.table import Table

BASE_URL = "http://localhost:8081/api/v1"
SUPERUSER_EMAIL = "komarovdemian@yandex.ru"
SUPERUSER_PASSWORD = "1234567890"

console = Console()


@dataclass
class TestResult:
    name: str
    status: str  # "PASS", "FAIL", "SKIP"
    status_code: int | None = None
    error: str | None = None


@dataclass
class TestContext:
    access_token: str = ""
    company_id: int = 0
    category_ids: list[int] = field(default_factory=list)
    product_ids: list[int] = field(default_factory=list)
    field_ids: list[int] = field(default_factory=list)
    faq_ids: list[int] = field(default_factory=list)
    thread_ids: list[str] = field(default_factory=list)
    customer_ids: list[int] = field(default_factory=list)
    results: list[TestResult] = field(default_factory=list)


def headers(ctx: TestContext) -> dict:
    return {"Authorization": f"Bearer {ctx.access_token}"}


async def api_get(client: httpx.AsyncClient, ctx: TestContext, path: str) -> tuple[int, Any]:
    """GET request returning (status_code, json_or_none)."""
    try:
        resp = await client.get(path, headers=headers(ctx))
        return resp.status_code, resp.json() if resp.status_code == 200 else None
    except Exception as e:
        return 0, str(e)


async def api_post(client: httpx.AsyncClient, ctx: TestContext, path: str, json_data: dict) -> tuple[int, Any]:
    """POST request returning (status_code, json_or_none)."""
    try:
        resp = await client.post(path, json=json_data, headers=headers(ctx))
        return resp.status_code, resp.json() if resp.status_code in (200, 201, 202) else None
    except Exception as e:
        return 0, str(e)


async def authenticate(client: httpx.AsyncClient, ctx: TestContext) -> bool:
    """Login and store token."""
    console.print("[bold]Authenticating...[/bold]")
    try:
        resp = await client.post(
            "/auth/login",
            json={"email": SUPERUSER_EMAIL, "password": SUPERUSER_PASSWORD},
        )
        if resp.status_code != 200:
            console.print(f"[red]Login failed: {resp.status_code}[/red]")
            console.print(
                f"[yellow]Create superuser: cd apps/backend && uv run python scripts/create_superuser.py "
                f"--email {SUPERUSER_EMAIL} --password {SUPERUSER_PASSWORD} --superuser[/yellow]"
            )
            return False
        data = resp.json()
        ctx.access_token = data["access_token"]
        console.print("[green]✓ Authenticated[/green]")
        return True
    except Exception as e:
        console.print(f"[red]Auth error: {e}[/red]")
        return False


async def setup_company(client: httpx.AsyncClient, ctx: TestContext) -> bool:
    """Get or create test company."""
    console.print("[bold]Setting up company...[/bold]")

    status, data = await api_get(client, ctx, "/companies")
    if status != 200:
        console.print(f"[red]Failed to list companies: {status}[/red]")
        return False

    existing = next((c for c in data if c["name"] == "Pagination Test Company"), None)
    if existing:
        ctx.company_id = existing["id"]
        console.print(f"[yellow]Using existing company: {ctx.company_id}[/yellow]")
    else:
        status, data = await api_post(
            client,
            ctx,
            "/companies",
            {
                "name": "Pagination Test Company",
                "description": "Test company for pagination sanity check",
                "rules": "Test rules",
                "tone_of_voice": "Professional",
                "assistant_name": "Test Bot",
                "qualification_workflow": "standard",
                "qualification_examples": "examples",
                "collection_name": f"pagination_test_{int(datetime.now().timestamp())}",
            },
        )
        if status != 201:
            console.print(f"[red]Failed to create company: {status}[/red]")
            return False
        ctx.company_id = data["id"]
        console.print(f"[green]✓ Created company: {ctx.company_id}[/green]")

    return True


async def create_categories(client: httpx.AsyncClient, ctx: TestContext):
    """Create 2 categories."""
    console.print("[dim]Creating categories...[/dim]")
    for i in range(2):
        status, data = await api_post(
            client,
            ctx,
            f"/companies/{ctx.company_id}/categories/",
            {
                "company_id": ctx.company_id,
                "name": f"Test Category {i + 1} - {datetime.now().timestamp()}",
                "description": f"Test category {i + 1}",
                "rules": "category rules",
                "examples": "examples",
                "workflow": "workflow",
            },
        )
        if status == 200 and data:
            ctx.category_ids.append(data["id"])
        elif status != 200:
            console.print(f"[red]  Category creation failed: {status}[/red]")
    console.print(f"[dim]  Created {len(ctx.category_ids)} categories[/dim]")


async def create_products(client: httpx.AsyncClient, ctx: TestContext):
    """Create 2 products (requires category)."""
    console.print("[dim]Creating products...[/dim]")
    if not ctx.category_ids:
        console.print("[yellow]  Skipped - no categories[/yellow]")
        return
    for i in range(2):
        status, data = await api_post(
            client,
            ctx,
            "/products/",
            {
                "name": f"Test Product {i + 1} - {datetime.now().timestamp()}",
                "description": f"Test product {i + 1}",
                "category_id": ctx.category_ids[0],
            },
        )
        if status == 200 and data:
            ctx.product_ids.append(data["id"])
        elif status != 200:
            console.print(f"[red]  Product creation failed: {status}[/red]")
    console.print(f"[dim]  Created {len(ctx.product_ids)} products[/dim]")


async def create_fields(client: httpx.AsyncClient, ctx: TestContext):
    """Create 2 fields."""
    console.print("[dim]Creating fields...[/dim]")
    for i in range(2):
        status, data = await api_post(
            client,
            ctx,
            f"/companies/{ctx.company_id}/fields",
            {
                "name": f"test_field_{i + 1}_{int(datetime.now().timestamp())}",
                "question": f"Test question {i + 1}?",
                "type": "string",
                "required": False,
                "category_id": ctx.category_ids[0] if ctx.category_ids else None,
            },
        )
        if status == 201 and data:
            ctx.field_ids.append(data["id"])
        elif status != 201:
            console.print(f"[red]  Field creation failed: {status}[/red]")
    console.print(f"[dim]  Created {len(ctx.field_ids)} fields[/dim]")


async def create_faqs(client: httpx.AsyncClient, ctx: TestContext):
    """Create 2 FAQs."""
    console.print("[dim]Creating FAQs...[/dim]")
    for i in range(2):
        status, data = await api_post(
            client,
            ctx,
            f"/companies/{ctx.company_id}/faqs",
            {
                "category": "General",
                "question": f"Test FAQ question {i + 1} - {datetime.now().timestamp()}?",
                "answer": f"Test answer {i + 1}",
                "keywords": ["test", f"keyword{i}"],
            },
        )
        if status == 201 and data:
            ctx.faq_ids.append(data["id"])
    console.print(f"[dim]  Created {len(ctx.faq_ids)} FAQs[/dim]")


async def create_threads(client: httpx.AsyncClient, ctx: TestContext):
    """Create 2 threads via internal API."""
    console.print("[dim]Creating threads...[/dim]")
    for i in range(2):
        ts = datetime.now().timestamp()
        status, data = await api_post(
            client,
            ctx,
            "/internal/chat/threads/get-or-create",
            {
                "user_id": f"pagination_test_user_{i}_{ts}",
                "company_id": ctx.company_id,
                "channel_type": "test",
                "connector_id": "test_connector",
                "conversation_id": f"pagination_conv_{i}_{ts}",
            },
        )
        if status == 200 and data:
            ctx.thread_ids.append(data["thread_id"])
    console.print(f"[dim]  Created {len(ctx.thread_ids)} threads[/dim]")


async def test_endpoint(
    client: httpx.AsyncClient,
    ctx: TestContext,
    name: str,
    path: str,
) -> TestResult:
    """Test a single pagination endpoint."""
    status, data = await api_get(client, ctx, path)
    if status == 200:
        items_count = len(data.get("items", [])) if isinstance(data, dict) else 0
        total = data.get("total", 0) if isinstance(data, dict) else 0
        return TestResult(name=name, status="PASS", status_code=status, error=f"items={items_count}, total={total}")
    else:
        return TestResult(name=name, status="FAIL", status_code=status, error=str(data)[:100])


async def run_pagination_tests(client: httpx.AsyncClient, ctx: TestContext):
    """Run all pagination endpoint tests."""
    console.print("\n[bold blue]Testing pagination endpoints...[/bold blue]\n")

    tests = [
        ("FAQs", f"/companies/{ctx.company_id}/faqs"),
        ("Members", f"/companies/{ctx.company_id}/members"),
        ("Categories", f"/companies/{ctx.company_id}/categories/"),
        ("Fields", f"/companies/{ctx.company_id}/fields"),
        ("Threads", f"/companies/{ctx.company_id}/threads"),
    ]

    # Test category fields if we have a category
    if ctx.category_ids:
        tests.append(("Category Fields", f"/companies/{ctx.company_id}/categories/{ctx.category_ids[0]}/fields"))

    # Test field options if we have a field
    if ctx.field_ids:
        tests.append(("Field Options", f"/companies/{ctx.company_id}/fields/{ctx.field_ids[0]}/options"))

    # Test thread messages if we have a thread
    if ctx.thread_ids:
        tests.append(("Thread Messages", f"/companies/{ctx.company_id}/threads/{ctx.thread_ids[0]}/messages"))

    # Test product fields if we have a product
    if ctx.product_ids:
        tests.append(("Product Fields", f"/companies/{ctx.company_id}/products/{ctx.product_ids[0]}/fields"))

    for name, path in tests:
        result = await test_endpoint(client, ctx, name, path)
        ctx.results.append(result)

        status_icon = "[green]✓[/green]" if result.status == "PASS" else "[red]✗[/red]"
        console.print(f"  {status_icon} {name}: {result.status_code} - {result.error}")


def print_summary(ctx: TestContext):
    """Print test summary table."""
    console.print("\n")

    table = Table(title="Pagination Sanity Check Results")
    table.add_column("Endpoint", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Code", style="dim")
    table.add_column("Details")

    for r in ctx.results:
        status_style = "green" if r.status == "PASS" else "red"
        table.add_row(r.name, f"[{status_style}]{r.status}[/{status_style}]", str(r.status_code or "-"), r.error or "")

    console.print(table)

    passed = sum(1 for r in ctx.results if r.status == "PASS")
    failed = sum(1 for r in ctx.results if r.status == "FAIL")
    total = len(ctx.results)

    console.print(f"\n[bold]Summary: {passed}/{total} passed, {failed} failed[/bold]")

    if failed == 0:
        console.print("[bold green]All pagination endpoints working correctly![/bold green]")
    else:
        console.print("[bold red]Some endpoints failed - check logs above[/bold red]")


async def main():
    console.print("\n[bold cyan]═══ Pagination Endpoints Sanity Check ═══[/bold cyan]\n")

    ctx = TestContext()

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # Auth
        if not await authenticate(client, ctx):
            sys.exit(1)

        # Setup company
        if not await setup_company(client, ctx):
            sys.exit(1)

        # Create test data
        console.print("\n[bold]Creating test data (2 of each entity)...[/bold]")
        await create_categories(client, ctx)
        await create_products(client, ctx)
        await create_fields(client, ctx)
        await create_faqs(client, ctx)
        await create_threads(client, ctx)

        # Run tests
        await run_pagination_tests(client, ctx)

        # Summary
        print_summary(ctx)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
