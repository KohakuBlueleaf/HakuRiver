"""Terminal connect command for task/VPS containers."""

import asyncio
import json
import os
import signal
import sys
import termios
import tty
from typing import Annotated

import typer
import websockets
from websockets.exceptions import (
    ConnectionClosed,
    ConnectionClosedOK,
    ConnectionClosedError,
)

from hakuriver.cli import client, config as cli_config
from hakuriver.cli.output import console, print_error

app = typer.Typer(help="Connect to container terminal")


@app.callback(invoke_without_command=True)
def connect(
    task_id: Annotated[str, typer.Argument(help="Task or VPS ID to connect to")],
):
    """Connect to a running container's terminal.

    Works with both VPS containers and running task containers.
    Uses WebSocket for full TTY support including arrow keys, Ctrl+C,
    and TUI applications like vim, htop, etc.

    Exit by typing 'exit' in the shell or pressing Ctrl+D.
    """
    try:
        # Validate task exists and is running
        task = client.get_task_status(task_id)

        if not task:
            print_error(f"Task {task_id} not found.")
            raise typer.Exit(1)

        task_type = task.get("task_type")
        if task_type not in ("vps", "command"):
            print_error(f"Task {task_id} is not a container task (type: {task_type})")
            raise typer.Exit(1)

        status = task.get("status")
        if status != "running":
            print_error(f"Task is not running (status: {status})")
            raise typer.Exit(1)

        console.print(f"[dim]Connecting to {task_type} {task_id}...[/dim]")

        # Run the terminal session
        asyncio.run(_run_terminal_session(task_id))

    except client.APIError as e:
        print_error(str(e))
        raise typer.Exit(1)


async def _run_terminal_session(task_id: str):
    """Run interactive WebSocket terminal session with full TTY support.

    Supports:
    - Arrow keys, escape sequences
    - Ctrl+C (sent to container, not local)
    - TUI apps like vim, htop, nano, screen
    - Exit by typing 'exit' command in shell
    """
    # Construct WebSocket URL
    ws_url = (
        f"ws://{cli_config.HOST_ADDRESS}:{cli_config.HOST_PORT}/task/{task_id}/terminal"
    )

    console.print(f"[dim]Connecting to {ws_url}...[/dim]")

    # Save original terminal settings
    old_settings = None
    if sys.stdin.isatty():
        old_settings = termios.tcgetattr(sys.stdin)

    try:
        async with websockets.connect(ws_url) as websocket:
            # Send initial terminal size FIRST - server waits for this before starting I/O
            if sys.stdout.isatty():
                try:
                    size = os.get_terminal_size()
                    # os.get_terminal_size() returns (columns, lines)
                    resize_msg = {
                        "type": "resize",
                        "rows": size.lines,
                        "cols": size.columns,
                    }
                    await websocket.send(json.dumps(resize_msg))
                except OSError:
                    pass

            # Wait for server acknowledgment (empty message after resize applied)
            try:
                await asyncio.wait_for(websocket.recv(), timeout=3.0)
            except asyncio.TimeoutError:
                pass

            # Set terminal to raw mode for full TTY forwarding
            # This allows arrow keys, Ctrl+C, etc. to be sent to container
            if old_settings:
                tty.setraw(sys.stdin.fileno())

            # Handle terminal resize (SIGWINCH)
            resize_queue = asyncio.Queue()

            def handle_resize(signum, frame):
                if sys.stdout.isatty():
                    try:
                        size = os.get_terminal_size()
                        # (columns, lines) -> (rows, cols)
                        resize_queue.put_nowait((size.lines, size.columns))
                    except Exception:
                        pass

            if hasattr(signal, "SIGWINCH"):
                signal.signal(signal.SIGWINCH, handle_resize)

            async def send_resize():
                """Send resize messages from queue."""
                try:
                    while True:
                        rows, cols = await resize_queue.get()
                        msg = {"type": "resize", "rows": rows, "cols": cols}
                        await websocket.send(json.dumps(msg))
                except Exception:
                    pass

            async def receive_messages():
                """Receives messages from the WebSocket and writes to stdout."""
                try:
                    while True:
                        message_text = await websocket.recv()
                        try:
                            message = json.loads(message_text)
                            if message.get("type") == "output" and message.get("data"):
                                # Write directly to stdout fd (works in raw mode)
                                os.write(
                                    sys.stdout.fileno(),
                                    message["data"].encode("utf-8", errors="replace"),
                                )
                            elif message.get("type") == "error" and message.get("data"):
                                os.write(
                                    sys.stdout.fileno(),
                                    f"\r\nERROR: {message['data']}\r\n".encode(),
                                )
                        except json.JSONDecodeError:
                            os.write(sys.stdout.fileno(), message_text.encode())
                except (ConnectionClosedOK, ConnectionClosedError, ConnectionClosed):
                    pass
                except Exception:
                    pass

            async def send_input():
                """Reads raw input from stdin and sends to WebSocket."""
                try:
                    while True:
                        # Read raw bytes from stdin (non-blocking via asyncio)
                        data = await asyncio.to_thread(
                            lambda: os.read(sys.stdin.fileno(), 1024)
                        )
                        if not data:
                            # EOF
                            break

                        # Send all input including Ctrl+C (\x03), arrow keys, etc.
                        message = {
                            "type": "input",
                            "data": data.decode("utf-8", errors="replace"),
                        }
                        await websocket.send(json.dumps(message))
                except (ConnectionClosed, ConnectionClosedOK, ConnectionClosedError):
                    pass
                except Exception:
                    pass

            # Run all tasks concurrently
            tasks = [
                asyncio.create_task(receive_messages()),
                asyncio.create_task(send_input()),
                asyncio.create_task(send_resize()),
            ]

            # Wait for any task to complete (connection closed, etc.)
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    except OSError as e:
        print_error(f"Connection error: {e}")
    except Exception as e:
        print_error(f"WebSocket error: {e}")
    finally:
        # Restore terminal settings
        if old_settings:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        # Reset signal handler
        if hasattr(signal, "SIGWINCH"):
            signal.signal(signal.SIGWINCH, signal.SIG_DFL)
        console.print("\r\n[dim]Disconnected.[/dim]")
