"""Node management commands."""

from typing import Annotated

import typer

from kohakuriver.cli import client
from kohakuriver.cli.formatters.node import (
    format_cluster_summary,
    format_node_detail,
    format_node_table,
)
from kohakuriver.cli.output import console, print_error

app = typer.Typer(help="Node management commands")


@app.command("list")
def list_nodes(
    status: Annotated[
        str | None,
        typer.Option("--status", "-s", help="Filter by status (online/offline)"),
    ] = None,
):
    """List all registered nodes."""
    try:
        nodes = client.get_nodes()

        if status:
            nodes = [n for n in nodes if n.get("status") == status]

        if not nodes:
            console.print("[yellow]No nodes found.[/yellow]")
            return

        table = format_node_table(nodes)
        console.print(table)

    except client.APIError as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("status")
def node_status(
    hostname: Annotated[str, typer.Argument(help="Node hostname")],
):
    """Get detailed status for a node."""
    try:
        nodes = client.get_nodes()
        node = next((n for n in nodes if n.get("hostname") == hostname), None)

        if not node:
            print_error(f"Node {hostname} not found.")
            raise typer.Exit(1)

        panel = format_node_detail(node)
        console.print(panel)

    except client.APIError as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("health")
def node_health(
    hostname: Annotated[
        str | None, typer.Argument(help="Node hostname (optional)")
    ] = None,
):
    """Show node health metrics."""
    try:
        if hostname:
            health = client.get_node_health(hostname)
            if isinstance(health, dict):
                panel = format_node_detail(health)
                console.print(panel)
            else:
                console.print("[yellow]No health data available.[/yellow]")
        else:
            nodes = client.get_nodes()
            if not nodes:
                console.print("[yellow]No nodes found.[/yellow]")
                return

            # Show cluster summary
            summary = format_cluster_summary(nodes)
            console.print(summary)
            console.print()

            # Show node table
            table = format_node_table(nodes)
            console.print(table)

    except client.APIError as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("watch")
def watch_nodes():
    """Live monitor cluster status (TUI dashboard)."""
    try:
        from kohakuriver.cli.interactive.dashboard import run_dashboard

        run_dashboard()

    except client.APIError as e:
        print_error(str(e))
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[dim]Dashboard closed.[/dim]")


@app.command("summary")
def cluster_summary():
    """Show cluster summary."""
    try:
        nodes = client.get_nodes()

        if not nodes:
            console.print("[yellow]No nodes found.[/yellow]")
            return

        panel = format_cluster_summary(nodes)
        console.print(panel)

    except client.APIError as e:
        print_error(str(e))
        raise typer.Exit(1)
