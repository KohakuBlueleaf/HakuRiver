# src/hakuriver/cli/ssh.py
import argparse
import asyncio
import sys
import os
import shlex  # For quoting command arguments

import toml
from zmq import has  # Needed if --config is supported

# Assume ClientProxy is located here based on previous step's design
from hakuriver.core.ssh_proxy.client import ClientProxy
from hakuriver.utils.logger import logger

# Import ClientConfig and config update helper for default values
from hakuriver.core.config import CLIENT_CONFIG, HOST_CONFIG
from .client import update_client_config_from_toml


async def run_ssh_and_proxy(
    task_id: str,
    host: str,
    proxy_port: int,
    local_port: int,
    user: str,
    config_path: str | None,  # Added config_path here
):
    """
    Starts the client proxy server and the local SSH subprocess concurrently.
    """
    # Apply config overrides here if needed for this specific utility
    # This assumes update_client_config_from_toml can be safely called multiple times
    # or that config loading happens earlier and is global.
    # If --config is only for this CLI, load and update here:
    if config_path:
        try:
            custom_config_data = None
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    custom_config_data = toml.load(f)
                update_client_config_from_toml(CLIENT_CONFIG, custom_config_data)
                logger.info(f"Client SSH CLI loaded custom config from {config_path}")
            else:
                logger.warning(f"Client SSH CLI config file not found: {config_path}")
        except Exception as e:
            logger.error(
                f"Error loading/applying config in SSH CLI: {e}", exc_info=True
            )
            # Decide if this is fatal or just a warning

    proxy = ClientProxy(task_id, host, proxy_port, local_port, user)
    if not local_port:
        local_port = proxy.local_port

    # --- Start the local proxy server as a background task ---
    proxy_server_task = asyncio.create_task(proxy.start_local_server())

    # Wait briefly for the server to start and print the command
    # A more robust way might be to get a signal from start_local_server
    # or wait for the socket to be listening. For simplicity, a short sleep.
    await asyncio.sleep(0.1)  # Give the server a moment to bind and print

    # --- Construct and start the local SSH client subprocess ---
    # Get the bound address and port from the proxy object (should be set after start_local_server runs)
    local_bind_address = "127.0.0.1"  # We hardcoded binding to localhost

    # The SSH command to connect to our local proxy server
    ssh_cmd = [
        "ssh",
        f"{user}@{local_bind_address}",
        "-p",
        str(local_port),
        # Recommended options for proxying
        # "-o",
        # "StrictHostKeyChecking=no",
        # "-o",
        # "UserKnownHostsFile=/dev/null",
        # "-o",
        # "PreferredAuthentications=publickey",  # Force public key auth
        # "-o",
        # "IdentitiesOnly=yes",  # Only use keys explicitly loaded/configured
        # Add other options here if needed, e.g., Verbose, ForwardAgent, X11Forwarding
        # Add -vvv for debugging: "-vvv"
    ]

    # Print the command that will be executed (useful for debugging)
    logger.info(
        f"Starting local SSH subprocess: {' '.join(shlex.quote(arg) for arg in ssh_cmd)}"
    )
    print(f"\nConnecting using: {' '.join(shlex.quote(arg) for arg in ssh_cmd)}\n")

    ssh_process = None
    try:
        # Use asyncio.create_subprocess_exec to run the SSH client
        # This connects its stdio to the parent process (this CLI)
        ssh_process = await asyncio.create_subprocess_exec(
            *ssh_cmd,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        logger.info(f"SSH subprocess started with PID: {ssh_process.pid}")

        # Wait for the SSH subprocess to finish
        returncode = await ssh_process.wait()
        logger.info(f"SSH subprocess finished with return code: {returncode}")

    except FileNotFoundError:
        logger.error(
            "SSH command not found. Make sure 'ssh' is installed and in your PATH."
        )
        # Set a non-zero return code for the overall process
        returncode = 127  # Standard Unix error for command not found
    except Exception as e:
        logger.exception(f"An error occurred while running the SSH subprocess: {e}")
        returncode = 1  # Indicate failure
    finally:
        # --- Shut down the local proxy server ---
        logger.info("SSH subprocess finished. Shutting down local proxy server.")
        proxy.close()  # This cancels the serve_forever loop in the background task
        try:
            # Wait for the proxy server task to acknowledge cancellation and finish
            await asyncio.wait_for(proxy_server_task, timeout=5.0)
            logger.info("Local proxy server task finished.")
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for local proxy server task to finish.")
        except asyncio.CancelledError:
            logger.debug("Proxy server task was already cancelled.")
        except Exception as e:
            logger.error(f"Error waiting for proxy server task: {e}")

    # Exit the script with the SSH process's return code (or an error code)
    sys.exit(returncode)


def main():
    """Entry point for the hakuriver-ssh CLI command."""
    parser = argparse.ArgumentParser(
        description="HakuRiver SSH: Connect to a VPS task via SSH proxy.",
        allow_abbrev=False,
    )

    # Global Configuration Argument
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Path to a custom TOML configuration file to override defaults.",
        default=None,
    )

    parser.add_argument(
        "task_id",
        metavar="TASK_ID",
        help="The ID of the VPS task to connect to.",
    )
    parser.add_argument(
        "--host",
        metavar="HOST_ADDRESS",
        # Default can be read from CLIENT_CONFIG, but required=True is simpler initially
        required=not hasattr(HOST_CONFIG, "REACABLE_ADDRESS"),
        default=getattr(HOST_CONFIG, "REACABLE_ADDRESS"),
        help="The address of the HakuRiver Host.",
    )
    parser.add_argument(
        "--proxy-port",
        type=int,
        metavar="PORT",
        # Default can be read from HOST_CONFIG.vps_proxy_port, but required=True is simpler initially
        required=not hasattr(HOST_CONFIG, "HOST_SSH_PROXY_PORT"),
        default=getattr(HOST_CONFIG, "HOST_SSH_PROXY_PORT", 0),
        help="The port the Host SSH proxy is listening on.",
    )
    parser.add_argument(
        "--local-port",
        type=int,
        metavar="PORT",
        default=0,  # Default to 0 to let the OS choose a free port
        help="The local port for the client proxy to listen on (Default: OS chooses).",
    )
    parser.add_argument(
        "--user",
        metavar="USER",
        default="root",  # Default to root as that's where key is placed by default
        help="The user to connect as inside the container (Default: root).",
    )

    args = parser.parse_args()

    # Load global config *before* running async logic if defaults are needed
    # or if config impacts logging or other global settings used early.
    # For simplicity here, we will pass the config_path to the async function
    # and let it handle the potential loading/updating within the async context.
    # If your config loading is truly global and synchronous, it happens on module import anyway.

    try:
        # Use asyncio.run to execute the main async function
        asyncio.run(
            run_ssh_and_proxy(
                args.task_id,
                args.host,
                args.proxy_port,
                args.local_port,
                args.user,
                args.config,  # Pass the config path
            )
        )
    except SystemExit:
        # Allow sys.exit calls from within the async function to terminate the script
        pass
    except Exception as e:
        logger.exception(f"An error occurred in the hakuriver-ssh CLI: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Logger setup happens on import of hakuriver.utils.logger
    main()
