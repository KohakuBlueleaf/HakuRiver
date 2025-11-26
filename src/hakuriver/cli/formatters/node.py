"""Node output formatters."""

from rich.panel import Panel
from rich.table import Table

from hakuriver.cli.output import format_bytes, format_status, get_status_style


def format_node_table(nodes: list[dict], title: str = "Nodes") -> Table:
    """Format nodes as a Rich table."""
    table = Table(title=title, show_header=True, header_style="bold magenta")

    table.add_column("Hostname", style="cyan", no_wrap=True)
    table.add_column("Status", justify="center")
    table.add_column("Cores", justify="right")
    table.add_column("Available", justify="right")
    table.add_column("Memory", justify="right")
    table.add_column("GPUs", justify="right")
    table.add_column("URL")

    for node in nodes:
        status = node.get("status", "unknown")
        status_text = format_status(status)

        total_cores = node.get("total_cores", 0)
        available_cores = node.get("available_cores", total_cores)

        memory_total = node.get("memory_total_bytes")
        memory_used = node.get("memory_used_bytes", 0)
        if memory_total:
            memory_str = f"{format_bytes(memory_used)}/{format_bytes(memory_total)}"
        else:
            memory_str = "-"

        gpu_info = node.get("gpu_info", [])
        gpu_count = len(gpu_info) if gpu_info else 0
        gpu_str = str(gpu_count) if gpu_count > 0 else "-"

        table.add_row(
            node.get("hostname", ""),
            status_text,
            str(total_cores),
            str(available_cores),
            memory_str,
            gpu_str,
            node.get("url", ""),
        )

    return table


def format_node_detail(node: dict) -> Panel:
    """Format single node as a Rich panel."""
    status = node.get("status", "unknown")
    color = get_status_style(status)

    memory_total = node.get("memory_total_bytes")
    memory_used = node.get("memory_used_bytes", 0)
    memory_percent = node.get("memory_percent", 0)

    lines = [
        f"[bold]Hostname:[/bold] {node.get('hostname', 'N/A')}",
        f"[bold]Status:[/bold] [{color}]{status}[/{color}]",
        f"[bold]URL:[/bold] {node.get('url', 'N/A')}",
        "",
        "[bold]CPU:[/bold]",
        f"  Total Cores: {node.get('total_cores', 'N/A')}",
        f"  Usage: {node.get('cpu_percent', 0):.1f}%",
        "",
        "[bold]Memory:[/bold]",
        f"  Total: {format_bytes(memory_total)}",
        f"  Used: {format_bytes(memory_used)} ({memory_percent:.1f}%)",
        "",
        "[bold]Temperature:[/bold]",
        f"  Average: {node.get('current_avg_temp', 'N/A')}C",
        f"  Max: {node.get('current_max_temp', 'N/A')}C",
        "",
        f"[bold]Last Heartbeat:[/bold] {node.get('last_heartbeat', 'N/A')}",
    ]

    # NUMA topology
    numa = node.get("numa_topology")
    if numa:
        lines.append("")
        lines.append("[bold]NUMA Topology:[/bold]")
        for node_id, cores in numa.items():
            lines.append(f"  Node {node_id}: cores {cores}")

    # GPU info
    gpu_info = node.get("gpu_info", [])
    if gpu_info:
        lines.append("")
        lines.append("[bold]GPUs:[/bold]")
        for i, gpu in enumerate(gpu_info):
            name = gpu.get("name", "Unknown")
            memory = gpu.get("memory_total", 0)
            util = gpu.get("utilization", 0)
            lines.append(f"  [{i}] {name} ({format_bytes(memory)}) - {util}%")

    content = "\n".join(lines)
    return Panel(content, title="Node Details", border_style=color)


def format_cluster_summary(nodes: list[dict]) -> Panel:
    """Format cluster summary as a Rich panel."""
    online = sum(1 for n in nodes if n.get("status") == "online")
    offline = len(nodes) - online

    total_cores = sum(n.get("total_cores", 0) for n in nodes)
    available_cores = sum(
        n.get("available_cores", 0) for n in nodes if n.get("status") == "online"
    )

    total_gpus = sum(len(n.get("gpu_info", [])) for n in nodes)

    total_memory = sum(n.get("memory_total_bytes", 0) for n in nodes)
    used_memory = sum(n.get("memory_used_bytes", 0) for n in nodes)

    lines = [
        f"[bold]Nodes:[/bold] {online} online / {offline} offline",
        f"[bold]Cores:[/bold] {available_cores} available / {total_cores} total",
        f"[bold]Memory:[/bold] {format_bytes(used_memory)} used / {format_bytes(total_memory)} total",
        f"[bold]GPUs:[/bold] {total_gpus} total",
    ]

    content = "\n".join(lines)
    return Panel(content, title="Cluster Summary", border_style="blue")
