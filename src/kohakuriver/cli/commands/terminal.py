"""Terminal UI and container access commands."""

import subprocess
from typing import Annotated

import typer

from kohakuriver.cli import client
from kohakuriver.cli.output import console, print_error

app = typer.Typer(
    help="Terminal UI and container access",
    invoke_without_command=True,
)


@app.callback(invoke_without_command=True)
def terminal_main(
    ctx: typer.Context,
    host: Annotated[
        str | None,
        typer.Option("--host", "-H", help="Host address", envvar="KOHAKURIVER_HOST"),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option("--port", "-P", help="Host port", envvar="KOHAKURIVER_PORT"),
    ] = None,
    refresh: Annotated[
        float,
        typer.Option("--refresh", "-r", help="Refresh rate in seconds"),
    ] = 2.0,
):
    """
    Launch the KohakuRiver Terminal UI.

    A full-screen dashboard showing cluster status, nodes, tasks, and VPS instances.
    Updates automatically and supports keyboard navigation.

    Keys:
      1 - Dashboard view
      2 - Nodes view
      3 - Tasks view
      4 - VPS view
      f - Filter tasks (in Tasks view)
      r - Refresh data
      q - Quit
    """
    from kohakuriver.cli import config as cli_config

    # Apply host/port overrides
    if host:
        cli_config.HOST_ADDRESS = host
    if port:
        cli_config.HOST_PORT = port

    # If a subcommand was invoked, skip the TUI
    if ctx.invoked_subcommand is not None:
        return

    # Launch TUI
    try:
        from kohakuriver.cli.interactive.tui import run_tui

        run_tui(refresh_rate=refresh)
    except KeyboardInterrupt:
        console.print("\n[dim]Goodbye![/dim]")
    except Exception as e:
        print_error(f"TUI error: {e}")
        raise typer.Exit(1)


@app.command("attach")
def attach_terminal(
    task_id: Annotated[str, typer.Argument(help="Task ID")],
    shell: Annotated[
        str, typer.Option("--shell", "-s", help="Shell to use")
    ] = "/bin/bash",
):
    """Attach to a running task's container."""
    from kohakuriver.docker.naming import task_container_name, vps_container_name

    try:
        task = client.get_task_status(task_id)

        if not task:
            print_error(f"Task {task_id} not found.")
            raise typer.Exit(1)

        if task.get("status") != "running":
            print_error(f"Task is not running (status: {task.get('status')})")
            raise typer.Exit(1)

        # Use correct container name based on task type
        if task.get("task_type") == "vps":
            container_name = vps_container_name(int(task_id))
        else:
            container_name = task_container_name(int(task_id))
        console.print(f"[dim]Attaching to container: {container_name}[/dim]")

        cmd = ["docker", "exec", "-it", container_name, shell]
        subprocess.run(cmd)

    except client.APIError as e:
        print_error(str(e))
        raise typer.Exit(1)
    except FileNotFoundError:
        print_error("Docker command not found.")
        raise typer.Exit(1)


@app.command("exec")
def exec_command(
    task_id: Annotated[str, typer.Argument(help="Task ID")],
    command: Annotated[list[str], typer.Argument(help="Command to execute")],
):
    """Execute a command in a running task's container."""
    from kohakuriver.docker.naming import task_container_name, vps_container_name

    try:
        task = client.get_task_status(task_id)

        if not task:
            print_error(f"Task {task_id} not found.")
            raise typer.Exit(1)

        if task.get("status") != "running":
            print_error(f"Task is not running (status: {task.get('status')})")
            raise typer.Exit(1)

        # Use correct container name based on task type
        if task.get("task_type") == "vps":
            container_name = vps_container_name(int(task_id))
        else:
            container_name = task_container_name(int(task_id))
        console.print(f"[dim]Executing in container: {container_name}[/dim]")

        cmd = ["docker", "exec", "-it", container_name] + list(command)
        subprocess.run(cmd)

    except client.APIError as e:
        print_error(str(e))
        raise typer.Exit(1)
    except FileNotFoundError:
        print_error("Docker command not found.")
        raise typer.Exit(1)
