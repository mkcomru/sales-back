"""Scenario-based testing infrastructure."""

import asyncio
import re
import sys
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from rich.panel import Panel

from framework.client import BaseTestClient
from framework.output import console, print_summary
from framework.setup import setup_environment


def _parse_choice_to_indices(choice: str, max_index: int) -> list[int] | None:
    """Parse choice like '1,3-5,12' into 0-based scenario indices.

    Returns None if any part is invalid.
    """
    seen: set[int] = set()
    result: list[int] = []
    for part in choice.split(","):
        part = part.strip()
        if "-" in part:
            match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
            if not match:
                return None
            lo, hi = int(match.group(1)), int(match.group(2))
            if lo > hi:
                return None
            for n in range(lo, hi + 1):
                if 1 <= n <= max_index and n not in seen:
                    seen.add(n)
                    result.append(n - 1)
        else:
            if not part.isdigit():
                return None
            n = int(part)
            if 1 <= n <= max_index and n not in seen:
                seen.add(n)
                result.append(n - 1)
    return result if result else None

ScenarioFunc = Callable[..., Awaitable[bool]]


@dataclass
class Scenario:
    """A test scenario definition."""

    name: str
    func: ScenarioFunc
    description: str = ""


@dataclass
class ScenarioResult:
    """Result of running a scenario."""

    name: str
    passed: bool
    error: str | None = None


async def run_scenario(scenario: Scenario, client: Any) -> ScenarioResult:
    """Run a single scenario with error handling."""
    try:
        passed = await scenario.func(client)
        return ScenarioResult(name=scenario.name, passed=passed)
    except Exception as e:
        console.print(f"[red]Error in {scenario.name}: {e}[/red]")
        console.print(Panel(traceback.format_exc(), title="[red]Traceback[/red]", border_style="red"))
        return ScenarioResult(name=scenario.name, passed=False, error=str(e))


async def run_all_scenarios(
    scenarios: list[Scenario],
    client: Any,
) -> list[ScenarioResult]:
    """Run all scenarios sequentially and return results."""
    console.print("\n[bold yellow]Running all scenarios...[/bold yellow]\n")

    results: list[ScenarioResult] = []
    for scenario in scenarios:
        result = await run_scenario(scenario, client)
        results.append(result)

    return results


def run_scenarios[T: BaseTestClient](
    client_class: type[T],
    scenarios: list[Scenario],
    *,
    title: str,
    description: str,
    company_name: str,
    create_thread: bool = False,
    check_sales_agent: bool = False,
) -> None:
    """Main entry point for BaseTestClient-based scenario tests."""

    async def _main() -> int:
        console.print(Panel.fit(f"[bold cyan]{title}[/bold cyan]\n\n{description}", border_style="cyan"))

        client = client_class()

        if not await setup_environment(
            client,
            company_name,
            create_thread=create_thread,
            check_sales_agent=check_sales_agent,
        ):
            return 1

        results = await run_all_scenarios(scenarios, client)
        print_summary([(r.name, r.passed) for r in results])

        console.print("\n[bold green]Done![/bold green]")
        return 0 if all(r.passed for r in results) else 1

    try:
        exit_code = asyncio.run(_main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(130)


async def interactive_menu(
    client: Any,
    scenarios: list[Scenario],
    *,
    state_printer: Callable[[], None] | None = None,
    utilities: list[tuple[str, str, Callable[[Any], Awaitable[None]]]] | None = None,
) -> None:
    """Run interactive menu for manual testing.

    Works with any client type. Use ``state_printer`` to display
    domain-specific state (selected items, IDs, etc.) above the menu.
    """
    utilities = utilities or []

    while True:
        console.print("\n" + "=" * 70)
        console.print("[bold]Test Menu[/bold]")
        console.print("=" * 70)

        if state_printer:
            state_printer()
        elif isinstance(client, BaseTestClient):
            if client.company_id:
                console.print(f"Company ID: [cyan]{client.company_id}[/cyan]")
            if client.order_id:
                console.print(f"Order ID: [cyan]{client.order_id}[/cyan]")
            if client.company_user_id:
                console.print(f"Company User ID: [cyan]{client.company_user_id}[/cyan]")

        console.print("-" * 70)
        console.print("[bold]Test Scenarios:[/bold] (1,3-5,12 = multiple)")

        for i, scenario in enumerate(scenarios, 1):
            desc = f" - {scenario.description}" if scenario.description else ""
            console.print(f"  \\[{i}] {scenario.name}{desc}")

        console.print("  \\[a] Run All Scenarios")
        console.print("-" * 70)

        if utilities:
            console.print("[bold]Utilities:[/bold]")
            for key, desc, _ in utilities:
                console.print(f"  \\[{key}] {desc}")
            console.print("-" * 70)

        console.print("  \\[q] Quit")
        console.print("-" * 70)

        try:
            choice = await asyncio.get_event_loop().run_in_executor(None, input, "Choice: ")
        except EOFError:
            break

        choice = choice.strip().lower()

        if choice == "q":
            break
        elif choice == "a":
            results = await run_all_scenarios(scenarios, client)
            print_summary([(r.name, r.passed) for r in results])
        elif (indices := _parse_choice_to_indices(choice, len(scenarios))) is not None:
            for idx in indices:
                await run_scenario(scenarios[idx], client)
        else:
            util = next((u for u in utilities if u[0] == choice), None)
            if util:
                try:
                    await util[2](client)
                except Exception as e:
                    console.print(f"[red]Error: {e}[/red]")
            else:
                console.print("[red]Invalid choice[/red]")
