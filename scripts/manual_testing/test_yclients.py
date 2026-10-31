#!/usr/bin/env python3
"""Test YClients API client against real API.

Requires env vars:
    YCLIENTS_PARTNER_TOKEN  — partner API token
    YCLIENTS_COMPANY_ID     — target company/branch ID

Usage (MUST run from apps/backend — src-layout requires it for src.backend imports):
    cd apps/backend
    YCLIENTS_PARTNER_TOKEN=xxx YCLIENTS_COMPANY_ID=123 \
        uv run --package manual-testing python ../../scripts/manual_testing/test_yclients.py
"""

import asyncio
import os
import sys

from framework.output import console, error, info, print_scenario_header, print_summary, print_table, success

from src.backend.integrations.yclients.client import YClientsClient, YClientsError
from src.backend.integrations.yclients.config import YClientsConfig, YClientsCredentials


def get_client() -> YClientsClient:
    token = os.environ.get("YCLIENTS_PARTNER_TOKEN")
    company_id = os.environ.get("YCLIENTS_COMPANY_ID")
    if not token or not company_id:
        console.print("[red]Missing env vars: YCLIENTS_PARTNER_TOKEN, YCLIENTS_COMPANY_ID[/red]")
        sys.exit(1)
    return YClientsClient(
        credentials=YClientsCredentials(partner_token=token),
        config=YClientsConfig(yclients_company_id=int(company_id)),
    )


# ------------------------------------------------------------------
# Shared state between scenarios
# ------------------------------------------------------------------

_selected_service_id: int | None = None
_selected_staff_id: int | None = None


# ------------------------------------------------------------------
# Scenarios
# ------------------------------------------------------------------


async def scenario_get_services(client: YClientsClient) -> bool:
    global _selected_service_id
    print_scenario_header("Scenario 1: Get Services", "Fetch bookable services and categories")

    data = await client.get_services()
    info(f"Categories: {len(data.category)}, Services: {len(data.services)}")

    if not data.services:
        error("No services returned — is this company configured?")
        return False

    print_table(
        [
            {
                "id": s.id,
                "title": s.title,
                "category_id": s.category_id,
                "price": f"{s.price_min}–{s.price_max}" if s.price_max else str(s.price_min),
                "duration": f"{s.seance_length // 60}m" if s.seance_length else "—",
            }
            for s in data.services[:15]
        ],
        [("id", "ID"), ("title", "Title"), ("category_id", "Category"), ("price", "Price"), ("duration", "Duration")],
        title="Services (first 15)",
    )

    if data.category:
        print_table(
            [{"id": c.id, "title": c.title} for c in data.category],
            [("id", "ID"), ("title", "Title")],
            title="Categories",
        )

    _selected_service_id = data.services[0].id
    success(f"Selected service_id={_selected_service_id} for further tests")

    console.print("\n[bold green]✓ Scenario 1 PASSED[/bold green]")
    return True


async def scenario_get_staff(client: YClientsClient) -> bool:
    global _selected_staff_id
    print_scenario_header("Scenario 2: Get Staff", "Fetch staff, optionally filtered by service")

    console.print("[yellow]Step 1: All staff[/yellow]")
    all_staff = await client.get_staff()
    info(f"Total staff: {len(all_staff)}")

    if not all_staff:
        error("No staff returned")
        return False

    print_table(
        [
            {
                "id": s.id,
                "name": s.name,
                "specialization": s.specialization,
                "bookable": s.bookable,
                "rating": s.rating,
            }
            for s in all_staff
        ],
        [("id", "ID"), ("name", "Name"), ("specialization", "Spec"), ("bookable", "Bookable"), ("rating", "Rating")],
        title="Staff",
    )

    bookable = [s for s in all_staff if s.bookable]
    if bookable:
        _selected_staff_id = bookable[0].id
        success(f"Selected bookable staff_id={_selected_staff_id} ({bookable[0].name})")
    else:
        _selected_staff_id = all_staff[0].id
        info(f"No bookable staff, using staff_id={_selected_staff_id}")

    if _selected_service_id:
        console.print(f"[yellow]Step 2: Staff filtered by service_id={_selected_service_id}[/yellow]")
        filtered = await client.get_staff(service_ids=[_selected_service_id])
        info(f"Filtered staff: {len(filtered)}")
        for s in filtered:
            console.print(f"  • {s.name} (id={s.id}, bookable={s.bookable})")

    console.print("\n[bold green]✓ Scenario 2 PASSED[/bold green]")
    return True


async def scenario_get_services_with_staff(client: YClientsClient) -> bool:
    print_scenario_header("Scenario 3: Services filtered by staff", "Verify seance_length appears with staff_id filter")

    if not _selected_staff_id:
        error("No staff selected from previous scenario")
        return False

    data = await client.get_services(staff_id=_selected_staff_id)
    info(f"Services for staff_id={_selected_staff_id}: {len(data.services)}")

    has_duration = [s for s in data.services if s.seance_length is not None]
    info(f"Services with seance_length: {len(has_duration)}/{len(data.services)}")

    if has_duration:
        print_table(
            [
                {"id": s.id, "title": s.title, "duration": f"{s.seance_length // 60}m"}
                for s in has_duration[:10]
            ],
            [("id", "ID"), ("title", "Title"), ("duration", "Duration")],
            title="Services with duration",
        )
        success("seance_length is returned when staff_id is set")
    else:
        info("No seance_length even with staff filter (may be API-dependent)")

    console.print("\n[bold green]✓ Scenario 3 PASSED[/bold green]")
    return True


async def scenario_get_available_dates(client: YClientsClient) -> bool:
    print_scenario_header("Scenario 4: Available dates", "Get booking days for staff+service")

    if not _selected_staff_id:
        error("No staff selected")
        return False

    service_ids = [_selected_service_id] if _selected_service_id else None
    data = await client.get_available_dates(
        staff_id=_selected_staff_id,
        service_ids=service_ids,
    )

    info(f"booking_days months: {list(data.booking_days.keys())}")
    total_days = sum(len(days) for days in data.booking_days.values())
    info(f"Total available days: {total_days}")

    if data.booking_days:
        for month, days in list(data.booking_days.items())[:3]:
            console.print(f"  Month {month}: days {', '.join(str(d) for d in days)}")
        success("Got booking dates")
    else:
        info("No available dates (staff may have no schedule)")

    console.print("\n[bold green]✓ Scenario 4 PASSED[/bold green]")
    return True


async def scenario_get_available_slots(client: YClientsClient) -> bool:
    print_scenario_header("Scenario 5: Available time slots", "Get concrete time slots for a date")

    if not _selected_staff_id:
        error("No staff selected")
        return False

    service_ids = [_selected_service_id] if _selected_service_id else None

    dates = await client.get_available_dates(
        staff_id=_selected_staff_id,
        service_ids=service_ids,
    )

    target_date = _pick_first_date(dates.booking_days)
    if not target_date:
        info("No available dates to fetch slots for — skipping")
        console.print("\n[bold yellow]⚠ Scenario 5 SKIPPED[/bold yellow]")
        return True

    console.print(f"[yellow]Fetching slots for {target_date}[/yellow]")
    slots = await client.get_available_slots(
        staff_id=_selected_staff_id,
        date=target_date,
        service_ids=service_ids,
    )

    info(f"Available slots: {len(slots)}")
    if slots:
        print_table(
            [
                {"time": s.time, "duration": f"{s.seance_length // 60}m", "ts": s.datetime}
                for s in slots[:15]
            ],
            [("time", "Time"), ("duration", "Duration"), ("ts", "Timestamp")],
            title=f"Slots on {target_date} (first 15)",
        )
        success(f"Got {len(slots)} slots")
    else:
        info("No slots on this date")

    console.print("\n[bold green]✓ Scenario 5 PASSED[/bold green]")
    return True


async def scenario_get_staff_seances(client: YClientsClient) -> bool:
    print_scenario_header("Scenario 6: Staff nearest seances", "Shortcut: nearest date + slots in one call")

    if not _selected_staff_id:
        error("No staff selected")
        return False

    service_ids = [_selected_service_id] if _selected_service_id else None
    data = await client.get_staff_seances(
        staff_id=_selected_staff_id,
        service_ids=service_ids,
    )

    info(f"Nearest seance_date timestamp: {data.seance_date}")
    info(f"Seances count: {len(data.seances)}")

    if data.seances:
        print_table(
            [{"time": s.time, "duration": f"{s.seance_length // 60}m"} for s in data.seances[:10]],
            [("time", "Time"), ("duration", "Duration")],
            title="Nearest seances (first 10)",
        )
        success("Staff seances shortcut works")
    else:
        info("No nearest seances available")

    console.print("\n[bold green]✓ Scenario 6 PASSED[/bold green]")
    return True


async def scenario_check_booking(client: YClientsClient) -> bool:
    print_scenario_header("Scenario 7: Check booking (dry run)", "Validate booking params without creating")

    if not _selected_staff_id or not _selected_service_id:
        info("No staff/service selected — skipping")
        console.print("\n[bold yellow]⚠ Scenario 7 SKIPPED[/bold yellow]")
        return True

    service_ids = [_selected_service_id]
    dates = await client.get_available_dates(
        staff_id=_selected_staff_id,
        service_ids=service_ids,
    )

    target_date = _pick_first_date(dates.booking_days)
    if not target_date:
        info("No available dates — skipping")
        console.print("\n[bold yellow]⚠ Scenario 7 SKIPPED[/bold yellow]")
        return True

    slots = await client.get_available_slots(
        staff_id=_selected_staff_id,
        date=target_date,
        service_ids=service_ids,
    )

    if not slots:
        info("No slots available — skipping")
        console.print("\n[bold yellow]⚠ Scenario 7 SKIPPED[/bold yellow]")
        return True

    from src.backend.integrations.yclients.schemas import YClientsCheckAppointment, YClientsCheckRequest

    slot = slots[0]
    check_request = YClientsCheckRequest(
        appointments=[
            YClientsCheckAppointment(
                id=1,
                services=service_ids,
                staff_id=_selected_staff_id,
                datetime=slot.datetime,
            )
        ]
    )

    console.print(
        f"[yellow]Checking: staff={_selected_staff_id}, "
        f"service={_selected_service_id}, time={slot.time}[/yellow]"
    )

    try:
        await client.check_booking(check_request)
        success("Booking check passed — slot is available")
    except YClientsError as e:
        error(f"Booking check failed: {e.message} (code={e.code})")
        return False
    except Exception as e:
        if "401" in str(e):
            info("book_check requires a user token — skipping (partner token is not enough)")
            console.print("\n[bold yellow]⚠ Scenario 7 SKIPPED[/bold yellow]")
            return True
        raise

    console.print("\n[bold green]✓ Scenario 7 PASSED[/bold green]")
    return True


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _pick_first_date(booking_days: dict[str, list[str]]) -> str | None:
    """Pick the first available date from booking_days dict."""
    from datetime import date

    today = date.today()
    for month, days in sorted(booking_days.items()):
        if not days:
            continue
        year = today.year if int(month) >= today.month else today.year + 1
        day = str(days[0]).zfill(2)
        return f"{year}-{str(month).zfill(2)}-{day}"
    return None


# ------------------------------------------------------------------
# Runner
# ------------------------------------------------------------------

SCENARIOS = [
    ("Get Services", scenario_get_services),
    ("Get Staff", scenario_get_staff),
    ("Services by Staff", scenario_get_services_with_staff),
    ("Available Dates", scenario_get_available_dates),
    ("Available Slots", scenario_get_available_slots),
    ("Staff Seances", scenario_get_staff_seances),
    ("Check Booking", scenario_check_booking),
]


async def main() -> int:
    from rich.panel import Panel

    console.print(Panel.fit(
        "[bold cyan]YClients API Client Test[/bold cyan]\n\n"
        "Direct test of YClientsClient against the real YClients API.\n"
        "Does NOT go through the backend — tests the HTTP client layer.",
        border_style="cyan",
    ))

    client = get_client()
    info(f"Company ID: {client.company_id}")

    results: list[tuple[str, bool]] = []

    async with client:
        for name, func in SCENARIOS:
            try:
                passed = await func(client)
                results.append((name, passed))
            except YClientsError as e:
                error(f"{name} failed: {e}")
                results.append((name, False))
            except Exception as e:
                error(f"{name} crashed: {e}")
                import traceback
                traceback.print_exc()
                results.append((name, False))

    print_summary(results)
    return 0 if all(passed for _, passed in results) else 1


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(130)
