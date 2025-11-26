"""VPS output formatters."""

import json

from rich.panel import Panel
from rich.table import Table

from hakuriver.cli.output import format_bytes, format_status, get_status_style


def format_vps_table(vps_list: list[dict], title: str = "VPS Instances") -> Table:
    """Format VPS list as a Rich table."""
    table = Table(title=title, show_header=True, header_style="bold magenta")

    table.add_column("Task ID", style="cyan", no_wrap=True)
    table.add_column("Status", justify="center")
    table.add_column("Node", style="green")
    table.add_column("SSH Port", justify="right")
    table.add_column("Cores", justify="right")
    table.add_column("GPUs", justify="right")
    table.add_column("Started", overflow="ellipsis", max_width=20)

    for vps in vps_list:
        status = vps.get("status", "unknown")
        status_text = format_status(status)

        gpus = vps.get("required_gpus", [])
        if isinstance(gpus, str):
            try:
                gpus = json.loads(gpus)
            except (json.JSONDecodeError, TypeError):
                gpus = []
        gpu_str = ",".join(map(str, gpus)) if gpus else "-"

        node = vps.get("assigned_node")
        if isinstance(node, dict):
            node = node.get("hostname", "-")
        node = node or "-"

        ssh_port = vps.get("ssh_port")
        ssh_str = str(ssh_port) if ssh_port else "-"

        started = vps.get("started_at", "-")
        if started and isinstance(started, str) and len(started) > 19:
            started = started[:19]

        table.add_row(
            str(vps.get("task_id", "")),
            status_text,
            node,
            ssh_str,
            str(vps.get("required_cores", 0)),
            gpu_str,
            str(started),
        )

    return table


def format_vps_detail(vps: dict) -> Panel:
    """Format single VPS as a Rich panel."""
    status = vps.get("status", "unknown")
    color = get_status_style(status)

    gpus = vps.get("required_gpus", [])
    if isinstance(gpus, str):
        try:
            gpus = json.loads(gpus)
        except (json.JSONDecodeError, TypeError):
            gpus = []
    gpu_str = ",".join(map(str, gpus)) if gpus else "None"

    node = vps.get("assigned_node")
    if isinstance(node, dict):
        node = node.get("hostname", "N/A")
    node = node or "N/A"

    memory = vps.get("required_memory_bytes")
    memory_str = format_bytes(memory) if memory else "No limit"

    lines = [
        f"[bold]Task ID:[/bold] {vps.get('task_id', 'N/A')}",
        f"[bold]Status:[/bold] [{color}]{status}[/{color}]",
        f"[bold]Node:[/bold] {node}",
        "",
        f"[bold]SSH Port:[/bold] {vps.get('ssh_port', 'N/A')}",
        "",
        "[bold]Resources:[/bold]",
        f"  Cores: {vps.get('required_cores', 'N/A')}",
        f"  Memory: {memory_str}",
        f"  GPUs: {gpu_str}",
        f"  NUMA Node: {vps.get('target_numa_node_id', 'Auto')}",
        "",
        "[bold]Timing:[/bold]",
        f"  Submitted: {vps.get('submitted_at', 'N/A')}",
        f"  Started: {vps.get('started_at', 'N/A')}",
    ]

    if vps.get("error_message"):
        lines.append(f"\n[bold red]Error:[/bold red] {vps['error_message']}")

    content = "\n".join(lines)
    return Panel(content, title="VPS Details", border_style=color)


def format_vps_created(result: dict) -> Panel:
    """Format VPS creation result as a Rich panel."""
    task_id = result.get("task_id", "N/A")
    ssh_port = result.get("ssh_port", "N/A")
    ssh_key_mode = result.get("ssh_key_mode", "upload")

    assigned = result.get("assigned_node", {})
    if isinstance(assigned, dict):
        hostname = assigned.get("hostname", "N/A")
    else:
        hostname = str(assigned) if assigned else "N/A"

    lines = [
        f"[bold]Task ID:[/bold] {task_id}",
        f"[bold]Node:[/bold] {hostname}",
        f"[bold]SSH Port:[/bold] {ssh_port}",
        f"[bold]SSH Key Mode:[/bold] {ssh_key_mode}",
    ]

    # Add SSH key info for generate mode
    if ssh_key_mode == "generate":
        lines.append("")
        lines.append("[bold]SSH Keys Generated:[/bold]")
        lines.append("  Private key will be saved locally")
        lines.append("  (see output below)")

    # Add connection info
    lines.append("")
    lines.append("[bold]Connect with:[/bold]")

    if ssh_key_mode == "none":
        lines.append(f"  ssh root@{hostname} -p {ssh_port}")
        lines.append("  [dim](passwordless root login enabled)[/dim]")
    elif ssh_key_mode == "generate":
        lines.append(f"  ssh -i <key_file> root@{hostname} -p {ssh_port}")
    else:
        lines.append(f"  ssh root@{hostname} -p {ssh_port}")

    content = "\n".join(lines)
    return Panel(content, title="VPS Created", border_style="green")
