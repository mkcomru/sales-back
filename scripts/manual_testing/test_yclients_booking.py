#!/usr/bin/env python3
"""Interactive YClients booking flow test.

Tests the full booking pipeline: services → staff → dates → slots → check → record.
Supports both automatic (run all) and interactive (pick items) modes.

Requires env vars:
    YCLIENTS_PARTNER_TOKEN  — partner API token
    YCLIENTS_COMPANY_ID     — target company/branch ID

Usage (MUST run from apps/backend — src-layout requires it for src.backend imports):
    cd apps/backend
    YCLIENTS_PARTNER_TOKEN=xxx YCLIENTS_COMPANY_ID=123 \
        uv run --package manual-testing python ../../scripts/manual_testing/test_yclients_booking.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import date

from framework.output import console, error, info, print_scenario_header, print_summary, print_table, success, warn
from framework.scenarios import Scenario, interactive_menu, run_all_scenarios

from src.backend.integrations.yclients.client import YClientsClient, YClientsError
from src.backend.integrations.yclients.config import YClientsConfig, YClientsCredentials
from src.backend.integrations.yclients.schemas import (
    YClientsCheckAppointment,
    YClientsCheckRequest,
    YClientsSeance,
    YClientsService,
    YClientsStaff,
)

# ------------------------------------------------------------------
# State accumulated across scenarios
# ------------------------------------------------------------------


class BookingState:
    services: list[YClientsService] = []
    staff: list[YClientsStaff] = []
    selected_service: YClientsService | None = None
    selected_staff: YClientsStaff | None = None
    selected_date: str | None = None
    slots: list[YClientsSeance] = []
    selected_slot: YClientsSeance | None = None
    booking_record_id: int | None = None
    booking_record_hash: str | None = None


state = BookingState()


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


def _prompt(msg: str) -> str:
    return input(msg).strip()


def _pick_index(items: list, label: str) -> int:
    while True:
        raw = _prompt(f"\nВыберите {label} (номер): ")
        if not raw.isdigit():
            console.print("[red]Введите число[/red]")
            continue
        idx = int(raw) - 1
        if 0 <= idx < len(items):
            return idx
        console.print(f"[red]Допустимый диапазон: 1–{len(items)}[/red]")


def _print_state() -> None:
    parts: list[str] = []
    if state.selected_service:
        parts.append(f"Услуга: [cyan]{state.selected_service.title}[/cyan] ({state.selected_service.id})")
    if state.selected_staff:
        parts.append(f"Мастер: [cyan]{state.selected_staff.name}[/cyan] ({state.selected_staff.id})")
    if state.selected_date:
        parts.append(f"Дата: [cyan]{state.selected_date}[/cyan]")
    if state.selected_slot:
        parts.append(f"Слот: [cyan]{state.selected_slot.time}[/cyan]")
    if state.booking_record_id:
        parts.append(f"Запись: [cyan]{state.booking_record_id}[/cyan]")

    if parts:
        console.print("[bold]Текущее состояние:[/bold]")
        for p in parts:
            console.print(f"  {p}")
    else:
        console.print("[dim]Состояние: ничего не выбрано[/dim]")


# ------------------------------------------------------------------
# Scenarios
# ------------------------------------------------------------------


async def scenario_services(client: YClientsClient) -> bool:
    print_scenario_header("1. Услуги", "Получить список услуг для онлайн-записи")

    data = await client.get_services()
    state.services = data.services
    info(f"Категорий: {len(data.category)}, Услуг: {len(data.services)}")

    if not data.services:
        error("Нет услуг — проверьте настройку компании")
        return False

    rows = [
        {
            "n": i + 1,
            "id": s.id,
            "title": s.title[:40],
            "price": f"{s.price_min}–{s.price_max}" if s.price_max else str(s.price_min),
            "duration": f"{s.seance_length // 60}m" if s.seance_length else "—",
        }
        for i, s in enumerate(data.services)
    ]
    print_table(
        rows,
        [("n", "#"), ("id", "ID"), ("title", "Название"), ("price", "Цена"), ("duration", "Длит.")],
        title="Услуги",
    )

    idx = _pick_index(data.services, "услугу")
    state.selected_service = data.services[idx]
    success(f"Выбрана услуга: {state.selected_service.title} (id={state.selected_service.id})")

    console.print("\n[bold green]✓ Сценарий 1 PASSED[/bold green]")
    return True


async def scenario_staff(client: YClientsClient) -> bool:
    print_scenario_header("2. Мастера", "Получить список мастеров для выбранной услуги")

    service_ids = [state.selected_service.id] if state.selected_service else None
    all_staff = await client.get_staff(service_ids=service_ids)
    bookable = [s for s in all_staff if s.bookable]
    state.staff = bookable or all_staff

    if not state.staff:
        error("Нет мастеров")
        return False

    info(f"Всего мастеров: {len(all_staff)}, доступных для записи: {len(bookable)}")

    rows = [
        {"n": i + 1, "id": s.id, "name": s.name, "spec": s.specialization or "—", "bookable": s.bookable}
        for i, s in enumerate(state.staff)
    ]
    print_table(
        rows,
        [("n", "#"), ("id", "ID"), ("name", "Имя"), ("spec", "Специализация"), ("bookable", "Bookable")],
        title="Мастера",
    )

    idx = _pick_index(state.staff, "мастера")
    state.selected_staff = state.staff[idx]
    success(f"Выбран мастер: {state.selected_staff.name} (id={state.selected_staff.id})")

    console.print("\n[bold green]✓ Сценарий 2 PASSED[/bold green]")
    return True


async def scenario_dates(client: YClientsClient) -> bool:
    print_scenario_header("3. Доступные даты", "Получить даты для записи к мастеру на услугу")

    if not state.selected_staff:
        error("Мастер не выбран")
        return False

    service_ids = [state.selected_service.id] if state.selected_service else None
    data = await client.get_available_dates(staff_id=state.selected_staff.id, service_ids=service_ids)

    flat_dates = _flatten_booking_days(data.booking_days)
    if not flat_dates:
        error("Нет доступных дат")
        return False

    info(f"Доступных дат: {len(flat_dates)}")
    display = flat_dates[:20]
    rows = [{"n": i + 1, "date": d} for i, d in enumerate(display)]
    print_table(rows, [("n", "#"), ("date", "Дата")], title="Доступные даты (первые 20)")

    idx = _pick_index(display, "дату")
    state.selected_date = display[idx]
    success(f"Выбрана дата: {state.selected_date}")

    console.print("\n[bold green]✓ Сценарий 3 PASSED[/bold green]")
    return True


async def scenario_slots(client: YClientsClient) -> bool:
    print_scenario_header("4. Доступные слоты", f"Слоты на {state.selected_date}")

    if not state.selected_staff or not state.selected_date:
        error("Мастер или дата не выбраны")
        return False

    service_ids = [state.selected_service.id] if state.selected_service else None
    slots = await client.get_available_slots(
        staff_id=state.selected_staff.id,
        date=state.selected_date,
        service_ids=service_ids,
    )
    state.slots = slots

    if not slots:
        error("Нет свободных слотов на эту дату")
        return False

    info(f"Слотов: {len(slots)}")
    rows = [
        {"n": i + 1, "time": s.time, "duration": f"{s.seance_length // 60}m", "dt": s.datetime}
        for i, s in enumerate(slots)
    ]
    print_table(
        rows,
        [("n", "#"), ("time", "Время"), ("duration", "Длит."), ("dt", "datetime (для API)")],
        title="Слоты",
    )

    idx = _pick_index(slots, "слот")
    state.selected_slot = slots[idx]
    success(f"Выбран слот: {state.selected_slot.time} (datetime={state.selected_slot.datetime})")

    console.print("\n[bold green]✓ Сценарий 4 PASSED[/bold green]")
    return True


async def scenario_check(client: YClientsClient) -> bool:
    print_scenario_header("5. Проверка слота (book_check)", "Валидация без создания записи")

    if not state.selected_staff or not state.selected_service or not state.selected_slot:
        error("Нет выбранного мастера/услуги/слота")
        return False

    check_request = YClientsCheckRequest(
        appointments=[
            YClientsCheckAppointment(
                id=1,
                services=[state.selected_service.id],
                staff_id=state.selected_staff.id,
                datetime=state.selected_slot.datetime,
            )
        ]
    )

    info(
        f"Проверка: мастер={state.selected_staff.name}, "
        f"услуга={state.selected_service.title}, время={state.selected_slot.time}"
    )

    try:
        await client.check_booking(check_request)
        success("book_check прошёл — слот доступен")
    except YClientsError as e:
        error(f"book_check отказ: {e.message} (code={e.code})")
        return False

    console.print("\n[bold green]✓ Сценарий 5 PASSED[/bold green]")
    return True


async def scenario_record(client: YClientsClient) -> bool:
    print_scenario_header("6. Создание записи (book_record)", "Реальная запись через API")

    if not state.selected_staff or not state.selected_service or not state.selected_slot:
        error("Нет выбранного мастера/услуги/слота")
        return False

    warn("ВНИМАНИЕ: это создаст реальную запись в YClients!")
    confirm = _prompt("Продолжить? (yes/no): ")
    if confirm.lower() not in ("yes", "y", "да"):
        info("Отменено пользователем")
        console.print("\n[bold yellow]⚠ Сценарий 6 SKIPPED[/bold yellow]")
        return True

    phone = _prompt("Телефон клиента (напр. +79001234567): ") or "+79001234567"
    fullname = _prompt("Имя клиента (напр. Тест Тестов): ") or "Тест Тестов"

    info(f"Создание записи: {fullname}, {phone}")
    info(
        f"  мастер={state.selected_staff.name}, "
        f"услуга={state.selected_service.title}, "
        f"время={state.selected_slot.time}"
    )

    try:
        results = await client.create_booking(
            phone=phone,
            fullname=fullname,
            appointments=[
                {
                    "service_ids": [state.selected_service.id],
                    "staff_id": state.selected_staff.id,
                    "datetime": state.selected_slot.datetime,
                }
            ],
        )
    except YClientsError as e:
        error(f"book_record отказ: {e.message} (code={e.code})")
        return False

    for r in results:
        state.booking_record_id = r.record_id
        state.booking_record_hash = r.record_hash
        success(f"Запись создана: record_id={r.record_id}, record_hash={r.record_hash}")

    console.print("\n[bold green]✓ Сценарий 6 PASSED[/bold green]")
    return True


async def scenario_delete(client: YClientsClient) -> bool:
    print_scenario_header("7. Удаление записи", "Удалить тестовую запись")

    if not state.booking_record_id or not state.booking_record_hash:
        info("Нет записи для удаления — пропуск")
        console.print("\n[bold yellow]⚠ Сценарий 7 SKIPPED[/bold yellow]")
        return True

    confirm = _prompt(f"Удалить запись record_id={state.booking_record_id}? (yes/no): ")
    if confirm.lower() not in ("yes", "y", "да"):
        info("Отменено")
        console.print("\n[bold yellow]⚠ Сценарий 7 SKIPPED[/bold yellow]")
        return True

    try:
        await client.delete_booking(state.booking_record_id, state.booking_record_hash)
        success(f"Запись {state.booking_record_id} удалена")
    except YClientsError as e:
        error(f"Ошибка удаления: {e.message}")
        return False

    console.print("\n[bold green]✓ Сценарий 7 PASSED[/bold green]")
    return True


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _flatten_booking_days(booking_days: dict[str, list]) -> list[str]:
    today = date.today()
    dates: list[str] = []
    for month, days in sorted(booking_days.items()):
        if not days:
            continue
        year = today.year if int(month) >= today.month else today.year + 1
        for day in sorted(days, key=int):
            dates.append(f"{year}-{str(month).zfill(2)}-{str(day).zfill(2)}")
    return dates


# ------------------------------------------------------------------
# Scenario definitions
# ------------------------------------------------------------------

SCENARIOS = [
    Scenario("Услуги", scenario_services, "Список услуг для онлайн-записи"),
    Scenario("Мастера", scenario_staff, "Список мастеров для выбранной услуги"),
    Scenario("Даты", scenario_dates, "Доступные даты для записи"),
    Scenario("Слоты", scenario_slots, "Свободные окна на выбранную дату"),
    Scenario("Проверка (book_check)", scenario_check, "Валидация слота без записи"),
    Scenario("Запись (book_record)", scenario_record, "Реальная запись через API"),
    Scenario("Удаление записи", scenario_delete, "Удалить тестовую запись"),
]

# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "interactive"
    client = get_client()

    async def _main() -> int:
        from rich.panel import Panel

        console.print(
            Panel.fit(
                "[bold cyan]YClients Booking Flow Test[/bold cyan]\n\n"
                "Полный флоу: услуги → мастера → даты → слоты → check → record → delete.",
                border_style="cyan",
            )
        )
        info(f"Company ID: {client.company_id}")

        async with client:
            if mode == "all":
                results = await run_all_scenarios(SCENARIOS, client)
                print_summary([(r.name, r.passed) for r in results])
                return 0 if all(r.passed for r in results) else 1
            else:
                await interactive_menu(client, SCENARIOS, state_printer=_print_state)
                return 0

    try:
        sys.exit(asyncio.run(_main()))
    except KeyboardInterrupt:
        console.print("\n[yellow]Прервано[/yellow]")
        sys.exit(130)
