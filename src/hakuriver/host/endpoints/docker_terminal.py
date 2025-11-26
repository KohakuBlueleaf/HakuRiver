"""WebSocket terminal endpoint for Docker containers on the Host."""

import asyncio
import json
import logging

import docker
from docker.errors import NotFound as DockerNotFound, APIError as DockerAPIError
from fastapi import WebSocket, WebSocketDisconnect, Path
from pydantic import BaseModel

from hakuriver.docker.naming import ENV_PREFIX

logger = logging.getLogger(__name__)


# --- WebSocket Message Models ---


class WebSocketInputMessage(BaseModel):
    """Model for messages received FROM the client over WebSocket."""

    type: str  # "input" or "resize"
    data: str | None = None  # Terminal input
    rows: int | None = None  # For resize
    cols: int | None = None  # For resize


class WebSocketOutputMessage(BaseModel):
    """Model for messages sent TO the client over WebSocket."""

    type: str  # "output" or "error"
    data: str


def _resolve_container_name(client: docker.DockerClient, env_name: str) -> str | None:
    """Resolve environment name to actual container name.

    Checks for prefixed name first, then falls back to unprefixed.
    """
    # Try prefixed name first
    prefixed_name = f"{ENV_PREFIX}-{env_name}"
    try:
        client.containers.get(prefixed_name)
        return prefixed_name
    except DockerNotFound:
        pass

    # Fallback: try the name as-is
    try:
        client.containers.get(env_name)
        return env_name
    except DockerNotFound:
        pass

    return None


async def terminal_websocket_endpoint(
    websocket: WebSocket,
    container_name: str = Path(
        ..., description="Name of the Host container to connect to."
    ),
):
    """
    Handles WebSocket connection for interacting with a Host container's shell.
    Uses the `docker` Python library.
    """
    await websocket.accept()
    logger.info(f"WebSocket connection accepted for container '{container_name}'")

    socket_stream = None
    exec_id = None
    client = None

    try:
        # 1. Initialize Docker Client
        try:
            client = docker.from_env(timeout=None)
            client.ping()
            logger.debug("Docker client initialized and connected.")
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            await websocket.send_json(
                WebSocketOutputMessage(
                    type="error", data=f"Docker connection error: {e}"
                ).model_dump()
            )
            await websocket.close(code=1011)
            return

        # 2. Resolve container name (support env_name without prefix)
        actual_container_name = _resolve_container_name(client, container_name)
        if not actual_container_name:
            logger.warning(
                f"Container '{container_name}' not found for terminal connection."
            )
            await websocket.send_json(
                WebSocketOutputMessage(
                    type="error", data=f"Container '{container_name}' not found."
                ).model_dump()
            )
            await websocket.close(code=1008)
            return

        # 3. Get the container
        try:
            container = client.containers.get(actual_container_name)
            if container.status != "running":
                await websocket.send_json(
                    WebSocketOutputMessage(
                        type="error",
                        data=f"Container '{container_name}' is not running (status: {container.status}).",
                    ).model_dump()
                )
                await websocket.close(code=1008)
                return
            logger.debug(
                f"Found running container '{actual_container_name}' (ID: {container.id})"
            )
        except DockerNotFound:
            logger.warning(
                f"Container '{actual_container_name}' not found for terminal connection."
            )
            await websocket.send_json(
                WebSocketOutputMessage(
                    type="error", data=f"Container '{container_name}' not found."
                ).model_dump()
            )
            await websocket.close(code=1008)
            return

        # 4. Create exec instance (interactive shell)
        shell_cmd = "/bin/bash"
        try:
            exit_code, _ = container.exec_run(
                cmd=f"which {shell_cmd}", demux=False, stream=False
            )
            if exit_code != 0:
                shell_cmd = "/bin/sh"
                logger.debug(
                    f"'/bin/bash' not found in container '{actual_container_name}', trying '/bin/sh'."
                )
                exit_code_sh, _ = container.exec_run(
                    cmd="which /bin/sh", demux=False, stream=False
                )
                if exit_code_sh != 0:
                    logger.error(
                        f"Neither /bin/bash nor /bin/sh found in container '{actual_container_name}'."
                    )
                    await websocket.send_json(
                        WebSocketOutputMessage(
                            type="error", data="No suitable shell found in container."
                        ).model_dump()
                    )
                    await websocket.close(code=1011)
                    return
        except DockerAPIError as e:
            logger.error(
                f"Error checking for shell in container '{actual_container_name}': {e}"
            )
            await websocket.send_json(
                WebSocketOutputMessage(
                    type="error", data=f"Error accessing container: {e}"
                ).model_dump()
            )
            await websocket.close(code=1011)
            return

        logger.info(
            f"Creating exec instance in container '{actual_container_name}' with shell '{shell_cmd}'"
        )
        exec_instance = client.api.exec_create(
            container.id,
            cmd=shell_cmd,
            stdin=True,
            stdout=True,
            stderr=True,
            tty=True,
        )
        exec_id = exec_instance["Id"]
        logger.debug(f"Exec instance created (ID: {exec_id})")

        # 5. Start exec and get the raw socket
        socket_stream = client.api.exec_start(
            exec_id,
            socket=True,
            stream=True,
            tty=True,
            demux=False,
        )
        if not hasattr(socket_stream, "_sock") or not socket_stream._sock:
            raise RuntimeError("Failed to get raw socket from exec_start")

        raw_socket = socket_stream._sock
        logger.info(
            f"Exec instance started, socket obtained for container '{actual_container_name}'."
        )

        # Wait for initial resize message from client (with timeout)
        # This ensures terminal dimensions are set before shell starts rendering
        try:
            initial_msg = await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
            initial_data = json.loads(initial_msg)
            if initial_data.get("type") == "resize":
                rows = initial_data.get("rows")
                cols = initial_data.get("cols")
                if rows and cols:
                    await asyncio.to_thread(
                        client.api.exec_resize,
                        exec_id,
                        height=rows,
                        width=cols,
                    )
                    logger.debug(f"Initial terminal resize to {rows}x{cols}")
        except asyncio.TimeoutError:
            logger.debug("No initial resize message received, using default size")
        except Exception as e:
            logger.debug(f"Error processing initial resize: {e}")

        await websocket.send_json(
            WebSocketOutputMessage(type="output", data="").model_dump()
        )

        # 6. Define I/O handling coroutines
        async def handle_output():
            """Reads from container socket and sends to WebSocket."""
            while True:
                try:
                    output = await asyncio.to_thread(raw_socket.recv, 4096)
                    if not output:
                        logger.info(
                            f"Container socket closed (output) for '{actual_container_name}'."
                        )
                        break
                    await websocket.send_json(
                        WebSocketOutputMessage(
                            type="output", data=output.decode("utf-8", errors="replace")
                        ).model_dump()
                    )
                except TimeoutError:
                    logger.debug(
                        f"Timeout while reading from container socket for '{actual_container_name}'."
                    )
                    continue
                except BrokenPipeError as e:
                    logger.info(
                        f"Container socket error (output) for '{actual_container_name}': {e}."
                    )
                    break
                except Exception as e:
                    logger.error(
                        f"Error reading from container or sending to WebSocket for '{actual_container_name}': {e}",
                        exc_info=True,
                    )
                    try:
                        await websocket.send_json(
                            WebSocketOutputMessage(
                                type="error",
                                data=f"\r\nError reading from container: {e}\r\n",
                            ).model_dump()
                        )
                    except Exception:
                        pass
                    break

        async def handle_input():
            """Reads from WebSocket and sends to container socket."""
            while True:
                try:
                    message_text = await websocket.receive_text()
                    message_data = json.loads(message_text)
                    input_msg = WebSocketInputMessage(**message_data)

                    if input_msg.type == "input" and input_msg.data:
                        await asyncio.to_thread(
                            raw_socket.sendall, input_msg.data.encode("utf-8")
                        )
                    elif (
                        input_msg.type == "resize" and input_msg.rows and input_msg.cols
                    ):
                        try:
                            logger.debug(
                                f"Resizing container terminal '{actual_container_name}' to {input_msg.rows}x{input_msg.cols}"
                            )
                            await asyncio.to_thread(
                                client.api.exec_resize,
                                exec_id,
                                height=input_msg.rows,
                                width=input_msg.cols,
                            )
                        except DockerAPIError as resize_err:
                            logger.warning(
                                f"Failed to resize terminal for container '{actual_container_name}': {resize_err}"
                            )
                        except Exception as resize_exc:
                            logger.error(
                                f"Unexpected error resizing terminal for '{actual_container_name}': {resize_exc}",
                                exc_info=True,
                            )

                except WebSocketDisconnect:
                    logger.info(
                        f"WebSocket disconnected (input) for '{actual_container_name}'."
                    )
                    break
                except json.JSONDecodeError:
                    logger.warning(
                        f"Received invalid JSON from WebSocket for container '{actual_container_name}'."
                    )
                except Exception as e:
                    logger.error(
                        f"Error receiving from WebSocket or sending to container for '{actual_container_name}': {e}",
                        exc_info=True,
                    )
                    break

        # 7. Run I/O tasks concurrently
        input_task = asyncio.create_task(handle_input())
        output_task = asyncio.create_task(handle_output())

        _, pending = await asyncio.wait(
            [input_task, output_task], return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass  # Expected when cancelling tasks
            except Exception as e:
                logger.debug(f"Task error during cleanup: {e}")

        logger.info(f"I/O tasks finished for container '{actual_container_name}'.")

    except asyncio.CancelledError:
        logger.info(f"Terminal session cancelled for container '{container_name}'.")
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected cleanly for container '{container_name}'.")
    except DockerAPIError as e:
        logger.error(
            f"Docker API error during terminal setup for '{container_name}': {e}"
        )
        try:
            await websocket.send_json(
                WebSocketOutputMessage(
                    type="error", data=f"Docker API Error: {e}\r\n"
                ).model_dump()
            )
        except Exception:
            pass
    except Exception as e:
        logger.exception(
            f"Unexpected error in terminal websocket for container '{container_name}': {e}"
        )
        try:
            await websocket.send_json(
                WebSocketOutputMessage(
                    type="error", data=f"Unexpected Server Error: {e}\r\n"
                ).model_dump()
            )
        except Exception:
            pass
    finally:
        logger.info(
            f"Closing WebSocket connection and cleaning up resources for container '{container_name}'."
        )
        if socket_stream and hasattr(socket_stream, "_sock") and socket_stream._sock:
            try:
                socket_stream._sock.close()
                logger.debug(f"Closed Docker exec socket for '{container_name}'.")
            except Exception as close_exc:
                logger.warning(
                    f"Error closing Docker exec socket for '{container_name}': {close_exc}"
                )
        try:
            await websocket.close(code=1000)
        except Exception:
            pass
