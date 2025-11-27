"""Task output formatters."""

import json

from rich.panel import Panel
from rich.table import Table

from kohakuriver.cli.output import format_bytes, format_status, get_status_style


def format_task_table(tasks: list[dict], title: str = "Tasks") -> Table:
    """Format tasks as a Rich table."""
    table = Table(title=title, show_header=True, header_style="bold magenta")

    table.add_column("Task ID", style="cyan", no_wrap=True)
    table.add_column("Status", justify="center")
    table.add_column("Node", style="green")
    table.add_column("Cores", justify="right")
    table.add_column("GPUs", justify="right")
    table.add_column("Command", overflow="ellipsis", max_width=40)

    for task in tasks:
        status = task.get("status", "unknown")
        status_text = format_status(status)

        gpus = task.get("required_gpus", [])
        if isinstance(gpus, str):
            try:
                gpus = json.loads(gpus)
            except (json.JSONDecodeError, TypeError):
                gpus = []
        gpu_str = ",".join(map(str, gpus)) if gpus else "-"

        node = task.get("assigned_node")
        if isinstance(node, dict):
            node = node.get("hostname", "-")
        node = node or "-"

        table.add_row(
            str(task.get("task_id", "")),
            status_text,
            node,
            str(task.get("required_cores", 1)),
            gpu_str,
            task.get("command", ""),
        )

    return table


def format_task_list_compact(tasks: list[dict]) -> Table:
    """Format tasks in compact view (less columns)."""
    table = Table(show_header=True, header_style="bold magenta")

    table.add_column("Task ID", style="cyan", no_wrap=True)
    table.add_column("Status", justify="center")
    table.add_column("Node")
    table.add_column("Command", overflow="ellipsis", max_width=50)

    for task in tasks:
        status = task.get("status", "unknown")
        status_text = format_status(status)

        node = task.get("assigned_node")
        if isinstance(node, dict):
            node = node.get("hostname", "-")
        node = node or "-"

        table.add_row(
            str(task.get("task_id", "")),
            status_text,
            node,
            task.get("command", ""),
        )

    return table


def format_task_detail(task: dict) -> Panel:
    """Format single task as a Rich panel."""
    status = task.get("status", "unknown")
    color = get_status_style(status)

    gpus = task.get("required_gpus", [])
    if isinstance(gpus, str):
        try:
            gpus = json.loads(gpus)
        except (json.JSONDecodeError, TypeError):
            gpus = []
    gpu_str = ",".join(map(str, gpus)) if gpus else "None"

    node = task.get("assigned_node")
    if isinstance(node, dict):
        node = node.get("hostname", "N/A")
    node = node or "N/A"

    memory = task.get("required_memory_bytes")
    memory_str = format_bytes(memory) if memory else "No limit"

    lines = [
        f"[bold]Task ID:[/bold] {task.get('task_id', 'N/A')}",
        f"[bold]Type:[/bold] {task.get('task_type', 'command')}",
        f"[bold]Status:[/bold] [{color}]{status}[/{color}]",
        f"[bold]Node:[/bold] {node}",
        "",
        f"[bold]Command:[/bold] {task.get('command', 'N/A')}",
        f"[bold]Arguments:[/bold] {task.get('arguments', [])}",
        "",
        "[bold]Resources:[/bold]",
        f"  Cores: {task.get('required_cores', 'N/A')}",
        f"  Memory: {memory_str}",
        f"  GPUs: {gpu_str}",
        f"  NUMA Node: {task.get('target_numa_node_id', 'Auto')}",
        "",
        "[bold]Timing:[/bold]",
        f"  Submitted: {task.get('submitted_at', 'N/A')}",
        f"  Started: {task.get('started_at', 'N/A')}",
        f"  Completed: {task.get('completed_at', 'N/A')}",
    ]

    if task.get("exit_code") is not None:
        exit_code = task["exit_code"]
        exit_style = "green" if exit_code == 0 else "red"
        lines.append(
            f"\n[bold]Exit Code:[/bold] [{exit_style}]{exit_code}[/{exit_style}]"
        )

    if task.get("error_message"):
        lines.append(f"\n[bold red]Error:[/bold red] {task['error_message']}")

    if task.get("ssh_port"):
        lines.append(f"\n[bold]SSH Port:[/bold] {task['ssh_port']}")

    content = "\n".join(lines)
    return Panel(content, title="Task Details", border_style=color)
