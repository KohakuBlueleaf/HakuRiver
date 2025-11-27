"""Docker output formatters."""

from rich.panel import Panel
from rich.table import Table

from kohakuriver.cli.output import format_bytes


def format_image_table(images: list[dict], title: str = "Docker Images") -> Table:
    """Format Docker images as a Rich table."""
    table = Table(title=title, show_header=True, header_style="bold magenta")

    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Tag", style="green")
    table.add_column("Size", justify="right")
    table.add_column("Created", overflow="ellipsis", max_width=20)

    for image in images:
        name = image.get("name", "")
        tag = image.get("tag", "latest")
        size = image.get("size_bytes")
        size_str = format_bytes(size) if size else "-"

        created = image.get("created", "-")
        if created and isinstance(created, str) and len(created) > 19:
            created = created[:19]

        table.add_row(
            name,
            tag,
            size_str,
            str(created),
        )

    return table


def format_container_table(containers: list[dict], title: str = "Containers") -> Table:
    """Format Docker containers as a Rich table."""
    table = Table(title=title, show_header=True, header_style="bold magenta")

    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Image", style="green")
    table.add_column("Status", justify="center")
    table.add_column("Created", overflow="ellipsis", max_width=20)

    for container in containers:
        name = container.get("name", "")
        image = container.get("image", "")
        status = container.get("status", "unknown")

        # Color status
        if "running" in status.lower():
            status_styled = f"[green]{status}[/green]"
        elif "exited" in status.lower():
            status_styled = f"[red]{status}[/red]"
        else:
            status_styled = f"[yellow]{status}[/yellow]"

        created = container.get("created", "-")
        if created and isinstance(created, str) and len(created) > 19:
            created = created[:19]

        table.add_row(
            name,
            image,
            status_styled,
            str(created),
        )

    return table


def format_image_detail(image: dict) -> Panel:
    """Format single Docker image as a Rich panel."""
    size = image.get("size_bytes")
    size_str = format_bytes(size) if size else "Unknown"

    lines = [
        f"[bold]Name:[/bold] {image.get('name', 'N/A')}",
        f"[bold]Tag:[/bold] {image.get('tag', 'latest')}",
        f"[bold]Full Tag:[/bold] {image.get('full_tag', 'N/A')}",
        f"[bold]Size:[/bold] {size_str}",
        f"[bold]Created:[/bold] {image.get('created', 'N/A')}",
    ]

    content = "\n".join(lines)
    return Panel(content, title="Image Details", border_style="blue")
