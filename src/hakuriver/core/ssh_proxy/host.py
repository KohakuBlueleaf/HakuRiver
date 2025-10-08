import asyncio
import re

from hakuriver.db.models import Task, Node  # Import necessary DB models
from hakuriver.utils.logger import logger  # Use the main HakuRiver logger
from hakuriver.core.ssh_proxy.bind_connection import bind_reader_writer


# Define the simple custom protocol request format
# REQUEST_TUNNEL <task_id>\n
REQUEST_TUNNEL_PREFIX = b"REQUEST_TUNNEL "
SUCCESS_RESPONSE = b"SUCCESS\n"
ERROR_RESPONSE_PREFIX = b"ERROR "


async def handle_connection(reader, writer):
    """Handles a single incoming connection to the Host SSH proxy."""
    client_addr = writer.get_extra_info("peername")
    log_prefix = f"[Client {client_addr}]"
    logger.info(f"{log_prefix} New connection.")

    task_id_str = None
    proxy_reader = None
    proxy_writer = None

    try:
        # --- Step 1: Read the initial request from the client proxy ---
        # We expect a line like "REQUEST_TUNNEL <task_id>\n"
        try:
            # Read up to a reasonable limit to prevent abuse
            initial_request = await asyncio.wait_for(
                reader.readuntil(b"\n"), timeout=10.0
            )
            logger.debug(
                f"{log_prefix} Received initial request: {initial_request.strip()}"
            )

            if not initial_request.startswith(REQUEST_TUNNEL_PREFIX):
                logger.warning(f"{log_prefix} Invalid request format: Missing prefix.")
                raise ValueError("Invalid request format.")

            # Extract task_id part
            task_id_bytes = initial_request[len(REQUEST_TUNNEL_PREFIX) :].strip()

            # Validate task_id format (expect digits)
            if not re.fullmatch(rb"\d+", task_id_bytes):
                logger.warning(
                    f"{log_prefix} Invalid task ID format: {task_id_bytes.decode(errors='ignore')}"
                )
                raise ValueError("Invalid task ID format.")

            task_id_str = task_id_bytes.decode("ascii")  # Decode assuming ASCII digits

        except asyncio.TimeoutError:
            logger.warning(f"{log_prefix} Timeout waiting for initial request.")
            raise ValueError("Timeout waiting for request.")
        except ValueError as e:
            # Specific ValueError from request parsing
            raise e
        except Exception as e:
            logger.error(
                f"{log_prefix} Error reading/parsing initial request: {e}",
                exc_info=True,
            )
            raise ValueError("Error processing request.")

        # --- Step 2: Lookup Task in Database ---
        task = None
        node = None
        runner_ip = None
        ssh_port = None
        try:
            # Peewee DB calls are blocking, run in a thread pool
            task = await asyncio.to_thread(
                Task.get_or_none, Task.task_id == int(task_id_str)
            )

            if not task:
                logger.warning(f"{log_prefix} Task ID {task_id_str} not found in DB.")
                raise ValueError(f"Task {task_id_str} not found.")

            if task.task_type != "vps":
                logger.warning(
                    f"{log_prefix} Task ID {task_id_str} is not a VPS task (type: {task.task_type})."
                )
                raise ValueError(f"Task {task_id_str} is not a VPS task.")

            active_vps_statuses = ["running", "paused"]  # Only route to active VPS
            if task.status not in active_vps_statuses:
                logger.warning(
                    f"{log_prefix} VPS task {task_id_str} is not active (status: {task.status})."
                )
                raise ValueError(
                    f"VPS task {task_id_str} is not active (status: {task.status})."
                )

            if not task.assigned_node:
                logger.error(
                    f"{log_prefix} VPS task {task_id_str} has no assigned node in DB."
                )
                raise ValueError(f"VPS task {task_id_str} has no assigned node.")
            if (
                task.ssh_port is None or task.ssh_port <= 0
            ):  # Ensure port is set and valid
                logger.error(
                    f"{log_prefix} VPS task {task_id_str} has no valid SSH port assigned in DB: {task.ssh_port}."
                )
                raise ValueError(f"VPS task {task_id_str} has no SSH port assigned.")

            # Get assigned node details
            # Need to fetch Node explicitly if task.assigned_node is just PK, or ensure it's loaded
            node = await asyncio.to_thread(
                Node.get_or_none, Node.hostname == task.assigned_node.hostname
            )

            if not node or node.status != "online":
                logger.warning(
                    f"{log_prefix} Assigned node {task.assigned_node.hostname} for task {task_id_str} is not online."
                )
                raise ValueError(
                    f"Assigned node for VPS task {task_id_str} is not online."
                )

            # Extract Runner IP/hostname from node URL
            try:
                # Simple parsing: expect http://<host>:<port>
                url_parts = node.url.split("://")
                if len(url_parts) < 2:
                    logger.error(
                        f"{log_prefix} Invalid runner URL format for node {node.hostname}: {node.url}"
                    )
                    raise ValueError(
                        f"Invalid runner URL format for node {node.hostname}."
                    )
                host_port_part = url_parts[1]
                runner_address = host_port_part.split(":")[0]  # Just take the host part

                runner_ip = runner_address
                ssh_port = task.ssh_port
                logger.info(
                    f"{log_prefix} Task {task_id_str} validated. Routing to {runner_ip}:{ssh_port}."
                )

            except Exception as url_e:
                logger.error(
                    f"{log_prefix} Error parsing runner URL {node.url}: {url_e}",
                    exc_info=True,
                )
                raise ValueError(f"Error parsing runner URL for node {node.hostname}.")

        except ValueError as e:
            # Specific ValueError from task lookup/validation
            raise e
        except Exception as e:
            logger.exception(
                f"{log_prefix} Unexpected error during task lookup for task ID {task_id_str}: {e}"
            )
            raise ValueError("Internal server error during task lookup.")

        # --- Step 3: Connect to the Runner/VPS SSH Port ---
        try:
            logger.debug(
                f"{log_prefix} Connecting to Runner/VPS at {runner_ip}:{ssh_port}..."
            )
            # Use wait_for with a timeout for the connection attempt
            proxy_reader, proxy_writer = await asyncio.wait_for(
                asyncio.open_connection(runner_ip, ssh_port), timeout=15.0
            )
            logger.info(
                f"{log_prefix} Proxy connection established to {runner_ip}:{ssh_port}."
            )

        except asyncio.TimeoutError:
            logger.warning(
                f"{log_prefix} Timeout connecting to Runner/VPS at {runner_ip}:{ssh_port}."
            )
            raise ValueError(f"Timeout connecting to Runner for task {task_id_str}.")
        except ConnectionRefusedError:
            logger.warning(
                f"{log_prefix} Connection refused by {runner_ip}:{ssh_port}. Is SSH daemon running in the container?"
            )
            raise ValueError(
                f"Connection refused by VPS task {task_id_str} on node {node.hostname}."
            )
        except Exception as e:
            logger.error(
                f"{log_prefix} Error connecting to Runner/VPS at {runner_ip}:{ssh_port}: {e}",
                exc_info=True,
            )
            raise ValueError(f"Failed to connect to Runner for task {task_id_str}.")

        # --- Step 4: Send SUCCESS response to client proxy and start forwarding ---
        try:
            logger.debug(f"{log_prefix} Sending SUCCESS response to client proxy.")
            writer.write(SUCCESS_RESPONSE)
            await writer.drain()

            logger.info(f"{log_prefix} Starting bidirectional data forwarding.")
            # Pipe data bidirectionally
            # asyncio.copyfileobj copies until EOF or connection error
            # It does not close the streams, so we close them in the finally block
            task_client_to_proxy = asyncio.create_task(
                bind_reader_writer(reader, proxy_writer)
            )
            task_proxy_to_client = asyncio.create_task(
                bind_reader_writer(proxy_reader, writer)
            )

            # Wait for either side to disconnect
            await asyncio.gather(
                task_client_to_proxy, task_proxy_to_client, return_exceptions=True
            )
            logger.info(f"{log_prefix} Bidirectional forwarding ended.")

        except Exception as e:
            logger.error(
                f"{log_prefix} Error during data forwarding: {e}", exc_info=True
            )
            # An error during forwarding likely means one side disconnected unexpectedly.
            # Gather will report it, but we'll ensure cleanup happens next.

    except ValueError as e:
        # Handle errors caught during request parsing or task lookup/validation/runner connection
        error_message = f"{ERROR_RESPONSE_PREFIX}{str(e)}\n"
        logger.warning(
            f"{log_prefix} Sending error to client proxy: {error_message.strip()}"
        )
        try:
            writer.write(error_message.encode())
            await writer.drain()
        except Exception:
            pass  # Ignore write errors on failing connection
    except Exception as e:
        # Handle any unexpected errors
        error_message = f"{ERROR_RESPONSE_PREFIX}Internal server error.\n"
        logger.exception(f"{log_prefix} Unexpected error in connection handler: {e}")
        try:
            writer.write(error_message.encode())
            await writer.drain()
        except Exception:
            pass
    finally:
        # --- Step 5: Clean up connections ---
        logger.debug(f"{log_prefix} Cleaning up connections.")
        if writer:
            writer.close()
            # Wait for the close to complete if possible, but handle exceptions
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
            except Exception:
                pass  # Ignore
        if proxy_writer:
            proxy_writer.close()
            try:
                await asyncio.wait_for(proxy_writer.wait_closed(), timeout=1.0)
            except Exception:
                pass  # Ignore
        logger.info(f"{log_prefix} Connection handler finished.")


async def start_server(host: str, port: int):
    """Starts the Host-side TCP server for VPS SSH proxying."""
    # Note: Assumes the Peewee DB is initialized and accessible in this process.
    # If using a connection pool, accessing models like Task/Node should be safe.
    # If not using a pool, you might need explicit connect/close around DB operations in handle_connection,
    # or pass connection handles if the DB library supports async management.
    # Using asyncio.to_thread handles the *blocking* nature, but not necessarily connection lifespan if not pooled.
    # For SQLite, a single connection might be sufficient for many concurrent threads via to_thread.
    # For simplicity here, we rely on the setup in host.py making Task/Node usable.

    try:
        # Use functools.partial if you need to pass extra args to handle_connection
        # from functools import partial
        # handler = partial(handle_connection, db=db) # Example if passing db explicity

        server = await asyncio.start_server(handle_connection, host, port)
        addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
        logger.info(f"Host SSH Proxy server started on {addrs}")

        async with server:
            await server.serve_forever()

    except asyncio.CancelledError:
        logger.info("Host SSH Proxy server task cancelled.")
    except Exception as e:
        logger.critical(
            f"FATAL: Host SSH Proxy server failed to start on {host}:{port}: {e}",
            exc_info=True,
        )
        # Re-raise to potentially stop the main Host process
        raise


# Example of how this would be called from host.py's startup_event:
# from .core.host_ssh_proxy import start_server as start_ssh_proxy_server
# ... in startup_event ...
# asyncio.create_task(start_ssh_proxy_server(HOST_CONFIG.HOST_BIND_IP, HOST_CONFIG.vps_proxy_port))
