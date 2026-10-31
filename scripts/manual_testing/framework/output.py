"""Rich console output utilities for consistent formatting."""

import json
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def success(message: str) -> None:
    """Print success message with green checkmark."""
    console.print(f"[green]✓ {message}[/green]")


def error(message: str) -> None:
    """Print error message with red X."""
    console.print(f"[red]✗ {message}[/red]")


def warn(message: str) -> None:
    """Print warning message with yellow indicator."""
    console.print(f"[yellow]⚠ {message}[/yellow]")


def info(message: str) -> None:
    """Print info message."""
    console.print(f"[cyan]{message}[/cyan]")


def step(message: str) -> None:
    """Print step indicator."""
    console.print(f"[yellow]{message}[/yellow]")


def print_json(data: Any, title: str | None = None, style: str = "cyan") -> None:
    """Print JSON data in a panel."""
    formatted = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    if title:
        console.print(Panel(formatted, title=f"[{style}]{title}[/{style}]", border_style=style))
    else:
        console.print(Panel(formatted, border_style=style))


def print_table(
    data: list[dict[str, Any]],
    columns: list[tuple[str, str]],
    title: str | None = None,
) -> None:
    """Print data as a Rich table.

    Args:
        data: List of dictionaries to display
        columns: List of (key, header) tuples defining columns
        title: Optional table title
    """
    table = Table(title=title)

    styles = ["cyan", "green", "yellow", "magenta", "blue", "white", "dim"]
    for i, (_, header) in enumerate(columns):
        table.add_column(header, style=styles[i % len(styles)])

    for row in data:
        values = []
        for key, _ in columns:
            value = row.get(key)
            if value is None:
                values.append("null")
            elif isinstance(value, bool):
                values.append("✓" if value else "✗")
            else:
                values.append(str(value))
        table.add_row(*values)

    console.print(table)


def print_header(title: str, description: str | None = None) -> None:
    """Print script header panel."""
    content = f"[bold cyan]{title}[/bold cyan]"
    if description:
        content += f"\n\n{description}"
    console.print(Panel.fit(content, border_style="cyan"))


def print_scenario_header(name: str, goal: str) -> None:
    """Print scenario header."""
    console.print(f"\n[bold cyan]{name}[/bold cyan]")
    console.print(f"Goal: {goal}\n")


def print_summary(results: list[tuple[str, bool]]) -> None:
    """Print test results summary table."""
    console.print("\n" + "=" * 60)
    console.print("[bold]Test Results Summary[/bold]")
    console.print("=" * 60)

    table = Table()
    table.add_column("Scenario", style="cyan")
    table.add_column("Result")

    passed = 0
    for name, result in results:
        status = "[green]✓ PASS[/green]" if result else "[red]✗ FAIL[/red]"
        table.add_row(name, status)
        if result:
            passed += 1

    console.print(table)
    console.print("-" * 60)
    console.print(f"Total: {passed}/{len(results)} passed")
    console.print("=" * 60)
