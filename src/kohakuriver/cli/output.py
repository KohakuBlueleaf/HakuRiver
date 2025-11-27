"""
Rich console output utilities for CLI.

Provides shared console instance and common output helpers.
"""

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

# Shared console instance
console = Console()
err_console = Console(stderr=True)


# Status color mapping
STATUS_COLORS = {
    "running": "green",
    "pending": "yellow",
    "assigning": "yellow",
    "completed": "blue",
    "failed": "red",
    "killed": "red",
    "killed_oom": "red",
    "paused": "cyan",
    "stopped": "dim",
    "lost": "magenta",
    "online": "green",
    "offline": "red",
}


def get_status_style(status: str) -> str:
    """Get Rich style for a status value."""
    return STATUS_COLORS.get(status.lower(), "white")


def format_status(status: str) -> Text:
    """Format status with appropriate color."""
    return Text(status, style=get_status_style(status))


def format_bytes(bytes_val: int | None) -> str:
    """Format bytes as human-readable string."""
    if bytes_val is None:
        return "-"

    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(bytes_val) < 1024:
            return f"{bytes_val:.1f}{unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f}PB"


def format_duration(seconds: float | None) -> str:
    """Format duration in human-readable form."""
    if seconds is None:
        return "-"

    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def print_error(message: str) -> None:
    """Print error message in red."""
    err_console.print(f"[red]Error:[/red] {message}")


def print_warning(message: str) -> None:
    """Print warning message in yellow."""
    console.print(f"[yellow]Warning:[/yellow] {message}")


def print_success(message: str) -> None:
    """Print success message in green."""
    console.print(f"[green]{message}[/green]")


def print_info(message: str) -> None:
    """Print info message."""
    console.print(f"[cyan]Info:[/cyan] {message}")


def create_spinner_progress() -> Progress:
    """Create a progress bar with spinner for indeterminate operations."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    )


def create_progress_bar() -> Progress:
    """Create a progress bar for determinate operations."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    )


def create_key_value_panel(
    data: dict[str, str | None],
    title: str,
    border_style: str = "blue",
) -> Panel:
    """Create a panel with key-value pairs."""
    lines = []
    for key, value in data.items():
        if value is not None:
            lines.append(f"[bold]{key}:[/bold] {value}")
        else:
            lines.append(f"[bold]{key}:[/bold] [dim]-[/dim]")

    content = "\n".join(lines)
    return Panel(content, title=title, border_style=border_style)


def create_simple_table(
    headers: list[str],
    rows: list[list[str]],
    title: str | None = None,
) -> Table:
    """Create a simple table with headers and rows."""
    table = Table(title=title, show_header=True, header_style="bold magenta")

    for header in headers:
        table.add_column(header)

    for row in rows:
        table.add_row(*row)

    return table
