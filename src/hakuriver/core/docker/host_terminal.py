import asyncio
import json

import docker  # Use the docker python library here
from docker.errors import NotFound as DockerNotFound, APIError as DockerAPIError
from fastapi import WebSocket, WebSocketDisconnect, Path

from ...utils.logger import logger  # Use the central logger
from .models import WebSocketInputMessage, WebSocketOutputMessage


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
    client = None  # Docker client instance

    try:
        # 1. Initialize Docker Client
        try:
            client = docker.from_env()
            client.ping()  # Verify connection
            logger.debug("Docker client initialized and connected.")
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {e}")
            await websocket.send_json(
                WebSocketOutputMessage(
                    type="error", data=f"Docker connection error: {e}"
                ).model_dump()
            )
            await websocket.close(code=1011)  # Internal error
            return

        # 2. Get the container
        try:
            container = client.containers.get(container_name)
            if container.status != "running":
                await websocket.send_json(
                    WebSocketOutputMessage(
                        type="error",
                        data=f"Container '{container_name}' is not running (status: {container.status}).",
                    ).model_dump()
                )
                await websocket.close(code=1008)  # Policy violation
                return
            logger.debug(
                f"Found running container '{container_name}' (ID: {container.id})"
            )
        except DockerNotFound:
            logger.warning(
                f"Container '{container_name}' not found for terminal connection."
            )
            await websocket.send_json(
                WebSocketOutputMessage(
                    type="error", data=f"Container '{container_name}' not found."
                ).model_dump()
            )
            await websocket.close(code=1008)  # Policy violation
            return

        # 3. Create exec instance (interactive shell)
        # Use /bin/bash if available, fallback to /bin/sh
        # Check which shell exists. This adds a slight delay but is more robust.
        shell_cmd = "/bin/bash"
        try:
            exit_code, _ = container.exec_run(
                cmd=f"which {shell_cmd}", demux=False, stream=False
            )
            if exit_code != 0:
                shell_cmd = "/bin/sh"
                logger.debug(
                    f"'{shell_cmd}' not found in container '{container_name}', trying '/bin/sh'."
                )
                exit_code_sh, _ = container.exec_run(
                    cmd="which /bin/sh", demux=False, stream=False
                )
                if exit_code_sh != 0:
                    logger.error(
                        f"Neither /bin/bash nor /bin/sh found in container '{container_name}'. Cannot start terminal."
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
                f"Error checking for shell in container '{container_name}': {e}"
            )
            await websocket.send_json(
                WebSocketOutputMessage(
                    type="error", data=f"Error accessing container: {e}"
                ).model_dump()
            )
            await websocket.close(code=1011)
            return

        logger.info(
            f"Creating exec instance in container '{container_name}' with shell '{shell_cmd}'"
        )
        exec_instance = client.api.exec_create(
            container.id,
            cmd=shell_cmd,
            stdin=True,
            stdout=True,  # Explicitly capture stdout
            stderr=True,  # Explicitly capture stderr
            tty=True,
        )
        exec_id = exec_instance["Id"]
        logger.debug(f"Exec instance created (ID: {exec_id})")

        # 4. Start exec and get the raw socket
        socket_stream = client.api.exec_start(
            exec_id,
            socket=True,  # Return the raw socket
            stream=True,  # Stream I/O
            tty=True,
            demux=False,  # Do not demultiplex stdout/stderr
        )
        # The socket is typically socket_stream._sock
        if not hasattr(socket_stream, "_sock") or not socket_stream._sock:
            raise RuntimeError("Failed to get raw socket from exec_start")

        raw_socket = socket_stream._sock
        logger.info(
            f"Exec instance started, socket obtained for container '{container_name}'."
        )
        await websocket.send_json(
            WebSocketOutputMessage(
                type="output", data="Terminal connected.\r\n"
            ).model_dump()
        )

        # 5. Define I/O handling coroutines
        async def handle_output():
            """Reads from container socket and sends to WebSocket."""
            while True:
                try:
                    # Adjust buffer size as needed
                    # Use asyncio.to_thread for potentially blocking recv
                    output = await asyncio.to_thread(raw_socket.recv, 4096)
                    if not output:
                        logger.info(
                            f"Container socket closed (output) for '{container_name}'."
                        )
                        break  # Socket closed
                    await websocket.send_json(
                        WebSocketOutputMessage(
                            type="output", data=output.decode("utf-8", errors="replace")
                        ).model_dump()
                    )
                except TimeoutError:
                    # Handle timeout if needed (e.g., log it)
                    logger.debug(
                        f"Timeout while reading from container socket for '{container_name}'."
                    )
                    continue  # Continue reading
                except BrokenPipeError as e:
                    logger.info(
                        f"Container socket error (output) for '{container_name}': {e}. Assuming disconnect."
                    )
                    break  # Socket likely closed
                except Exception as e:
                    # Catch other potential errors during recv/send
                    logger.error(
                        f"Error reading from container or sending to WebSocket for '{container_name}': {e}",
                        exc_info=True,
                    )
                    # Try sending error to frontend, but it might fail if websocket is also broken
                    try:
                        await websocket.send_json(
                            WebSocketOutputMessage(
                                type="error",
                                data=f"\r\nError reading from container: {e}\r\n",
                            ).model_dump()
                        )
                    except Exception as e:
                        pass
                    break  # Stop this task on error

        async def handle_input():
            """Reads from WebSocket and sends to container socket."""
            while True:
                try:
                    message_text = await websocket.receive_text()
                    message_data = json.loads(message_text)
                    input_msg = WebSocketInputMessage(**message_data)

                    if input_msg.type == "input" and input_msg.data:
                        # Use asyncio.to_thread for potentially blocking send
                        await asyncio.to_thread(
                            raw_socket.sendall, input_msg.data.encode("utf-8")
                        )
                    elif (
                        input_msg.type == "resize" and input_msg.rows and input_msg.cols
                    ):
                        try:
                            logger.debug(
                                f"Resizing container terminal '{container_name}' (exec_id: {exec_id}) to {input_msg.rows}x{input_msg.cols}"
                            )
                            # Run resize in executor as it might involve API call/block
                            await asyncio.to_thread(
                                client.api.exec_resize,
                                exec_id,
                                height=input_msg.rows,
                                width=input_msg.cols,
                            )
                        except DockerAPIError as resize_err:
                            logger.warning(
                                f"Failed to resize terminal for container '{container_name}': {resize_err}"
                            )
                        except Exception as resize_exc:
                            logger.error(
                                f"Unexpected error resizing terminal for '{container_name}': {resize_exc}",
                                exc_info=True,
                            )

                except WebSocketDisconnect:
                    logger.info(
                        f"WebSocket disconnected (input) for '{container_name}'."
                    )
                    break  # Stop loop
                except json.JSONDecodeError:
                    logger.warning(
                        f"Received invalid JSON from WebSocket for container '{container_name}'."
                    )
                    # Continue listening for valid messages
                except Exception as e:
                    logger.error(
                        f"Error receiving from WebSocket or sending to container for '{container_name}': {e}",
                        exc_info=True,
                    )
                    break  # Stop this task on error

        # 6. Run I/O tasks concurrently
        input_task = asyncio.create_task(handle_input())
        output_task = asyncio.create_task(handle_output())

        # Wait for either task to complete (e.g., socket closes, WebSocket disconnects)
        _, pending = await asyncio.wait(
            [input_task, output_task], return_when=asyncio.FIRST_COMPLETED
        )

        # Cancel the other task if one finishes
        for task in pending:
            task.cancel()
            try:
                await task  # Wait for cancellation (optional, handles potential exceptions)
            except asyncio.CancelledError:
                pass  # Expected

        logger.info(f"I/O tasks finished for container '{container_name}'.")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected cleanly for container '{container_name}'.")
    except DockerAPIError as e:
        logger.error(
            f"Docker API error during terminal setup for '{container_name}': {e}"
        )
        # Try sending error message if websocket still open
        try:
            await websocket.send_json(
                WebSocketOutputMessage(
                    type="error", data=f"Docker API Error: {e}\r\n"
                ).model_dump()
            )
        except Exception as e:
            pass  # Ignore send error if websocket is already closed
    except Exception as e:
        logger.exception(
            f"Unexpected error in terminal websocket for container '{container_name}': {e}"
        )
        # Try sending error message if websocket still open
        try:
            await websocket.send_json(
                WebSocketOutputMessage(
                    type="error", data=f"Unexpected Server Error: {e}\r\n"
                ).model_dump()
            )
        except Exception as e:
            pass  # Ignore send error if websocket is already closed
    finally:
        logger.info(
            f"Closing WebSocket connection and cleaning up resources for container '{container_name}'."
        )
        # Ensure socket is closed
        if socket_stream and hasattr(socket_stream, "_sock") and socket_stream._sock:
            try:
                socket_stream._sock.close()
                logger.debug(f"Closed Docker exec socket for '{container_name}'.")
            except Exception as close_exc:
                logger.warning(
                    f"Error closing Docker exec socket for '{container_name}': {close_exc}"
                )
        # Ensure WebSocket is closed from server-side if not already
        try:
            await websocket.close(code=1000)  # Normal closure
        except Exception as e:
            pass  # Ignore if already closed
