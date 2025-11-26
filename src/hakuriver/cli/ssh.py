"""
SSH CLI for connecting to VPS tasks.

Usage:
    hakuriver.ssh TASK_ID --host HOST --proxy-port PORT
"""
import argparse
import asyncio
import logging
import shlex
import sys

from hakuriver.ssh_proxy.client import ClientProxy

logger = logging.getLogger(__name__)


async def run_ssh_and_proxy(
    task_id: str,
    host: str,
    proxy_port: int,
    local_port: int,
    user: str,
):
    """
    Start the client proxy server and the local SSH subprocess concurrently.
    """
    proxy = ClientProxy(task_id, host, proxy_port, local_port, user)
    if not local_port:
        local_port = proxy.local_port

    # Start the local proxy server as a background task
    proxy_server_task = asyncio.create_task(proxy.start_local_server())

    # Wait briefly for the server to start
    await asyncio.sleep(0.1)

    # Construct the SSH command
    local_bind_address = "127.0.0.1"
    ssh_cmd = [
        "ssh",
        f"{user}@{local_bind_address}",
        "-p",
        str(local_port),
    ]

    logger.info(
        f"Starting local SSH subprocess: {' '.join(shlex.quote(arg) for arg in ssh_cmd)}"
    )
    print(f"\nConnecting using: {' '.join(shlex.quote(arg) for arg in ssh_cmd)}\n")

    ssh_process = None
    returncode = 1

    try:
        ssh_process = await asyncio.create_subprocess_exec(
            *ssh_cmd,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        logger.info(f"SSH subprocess started with PID: {ssh_process.pid}")

        returncode = await ssh_process.wait()
        logger.info(f"SSH subprocess finished with return code: {returncode}")

    except FileNotFoundError:
        logger.error(
            "SSH command not found. Make sure 'ssh' is installed and in your PATH."
        )
        returncode = 127

    except Exception as e:
        logger.exception(f"An error occurred while running the SSH subprocess: {e}")
        returncode = 1

    finally:
        logger.info("SSH subprocess finished. Shutting down local proxy server.")
        proxy.close()
        try:
            await asyncio.wait_for(proxy_server_task, timeout=5.0)
            logger.info("Local proxy server task finished.")
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for local proxy server task to finish.")
        except asyncio.CancelledError:
            logger.debug("Proxy server task was already cancelled.")
        except Exception as e:
            logger.error(f"Error waiting for proxy server task: {e}")

    sys.exit(returncode)


def main():
    """Entry point for the hakuriver-ssh CLI command."""
    parser = argparse.ArgumentParser(
        description="HakuRiver SSH: Connect to a VPS task via SSH proxy.",
        allow_abbrev=False,
    )

    parser.add_argument(
        "task_id",
        metavar="TASK_ID",
        help="The ID of the VPS task to connect to.",
    )
    parser.add_argument(
        "--host",
        metavar="HOST_ADDRESS",
        required=True,
        help="The address of the HakuRiver Host.",
    )
    parser.add_argument(
        "--proxy-port",
        type=int,
        metavar="PORT",
        default=8002,
        help="The port the Host SSH proxy is listening on (default: 8002).",
    )
    parser.add_argument(
        "--local-port",
        type=int,
        metavar="PORT",
        default=0,
        help="The local port for the client proxy (default: OS chooses).",
    )
    parser.add_argument(
        "--user",
        metavar="USER",
        default="root",
        help="The user to connect as inside the container (default: root).",
    )

    args = parser.parse_args()

    try:
        asyncio.run(
            run_ssh_and_proxy(
                args.task_id,
                args.host,
                args.proxy_port,
                args.local_port,
                args.user,
            )
        )
    except SystemExit:
        pass
    except Exception as e:
        logger.exception(f"An error occurred in the hakuriver-ssh CLI: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
