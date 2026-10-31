"""Common setup utilities for test environment."""

from framework.client import BaseTestClient
from framework.config import config
from framework.output import console, error, info, success, warn


async def setup_environment(
    client: BaseTestClient,
    company_name: str,
    *,
    create_thread: bool = False,
    check_sales_agent: bool = False,
) -> bool:
    """Setup test environment with user, company, and optionally thread/order.

    Args:
        client: Test client instance to configure
        company_name: Name for the test company
        create_thread: If True, creates a thread and gets the associated order
        check_sales_agent: If True, checks sales-agent health

    Returns:
        True if setup succeeded, False otherwise
    """
    console.print("\n[bold blue]Setting up test environment...[/bold blue]\n")

    # Health checks
    console.print("0. Checking service health...")
    backend_ok = await client.check_backend_health()

    if backend_ok:
        success("Backend is healthy (port 8081)")
    else:
        error("Backend is not responding")
        console.print("[yellow]   Run: docker-compose up backend[/yellow]")
        return False

    if check_sales_agent:
        sales_ok = await client.check_sales_agent_health()
        if sales_ok:
            success("Sales-agent is healthy (port 8080)")
        else:
            warn("Sales-agent is not responding (some tests may fail)")

    # Authentication
    console.print("\n1. Authenticating as superuser...")
    result = await client.login()

    if "error" in result:
        error(f"Login failed: {result['error']}")
        console.print("\n[yellow]Please create superuser first:[/yellow]")
        console.print(
            f"[dim]cd apps/backend && uv run python scripts/create_superuser.py "
            f"--email {config.superuser_email} --password {config.superuser_password} --superuser[/dim]"
        )
        return False

    client.access_token = result["access_token"]
    client.refresh_token = result["refresh_token"]
    success("Logged in as superuser")

    me = await client.get_me()
    client.user_id = me["id"]
    info(f"   User ID: {client.user_id}, Name: {me['first_name']} {me['last_name']}")

    # Company setup
    console.print("\n2. Setting up company...")
    companies = await client.list_companies()

    existing = next((c for c in companies if c["name"] == company_name), None)
    if existing:
        client.company_id = existing["id"]
        warn(f"Using existing company: {client.company_id}")
    else:
        company = await client.create_company(company_name)
        client.company_id = company["id"]
        success(f"Created company: {client.company_id}")

    # Company members
    console.print("\n3. Loading company members...")
    members = await client.list_company_members()

    for member in members:
        info(
            f"   Member: {member['first_name']} {member['last_name']} "
            f"(id={member['id']}, role={member['role']})"
        )
        if member["user_id"] == client.user_id:
            client.company_user_id = member["id"]

    if not client.company_user_id:
        error("Current user is not a member of the company")
        return False

    success(f"Your company_user_id: {client.company_user_id}")

    # Optional thread/order creation
    if create_thread:
        console.print("\n4. Creating test thread and order...")
        from datetime import datetime

        user_id = f"test_user_{datetime.now().timestamp()}"
        thread_data = await client.get_or_create_thread(user_id)
        client.thread_id = thread_data["thread_id"]
        success(f"Thread created: {client.thread_id}")

        order_context = await client.get_order_by_thread(client.thread_id)
        client.order_id = order_context["order_id"]
        success(f"Order created: {client.order_id}")

    return True
