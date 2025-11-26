"""
HakuRiver Docker Client: Manage Host-side Docker containers and tarballs.

Usage:
    hakuriver.docker list-containers
    hakuriver.docker create-container IMAGE_NAME CONTAINER_NAME
    hakuriver.docker delete-container CONTAINER_NAME
    hakuriver.docker stop-container CONTAINER_NAME
    hakuriver.docker start-container CONTAINER_NAME
    hakuriver.docker list-tars
    hakuriver.docker create-tar CONTAINER_NAME
"""
import argparse
import json
import logging
import sys

import httpx

from hakuriver.cli import config as CLI_CONFIG

logger = logging.getLogger(__name__)


def _get_host_url() -> str:
    """Get the host URL from config."""
    return f"http://{CLI_CONFIG.HOST_ADDRESS}:{CLI_CONFIG.HOST_PORT}"


def print_json_response(response: httpx.Response):
    """Helper to print formatted JSON response."""
    try:
        data = response.json()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except json.JSONDecodeError:
        logger.error("Failed to decode JSON response.")
        print(response.text)
    except Exception as e:
        logger.error(f"Error processing JSON response: {e}")
        print(response.text)


def main():
    """CLI entry point for Docker management commands."""
    parser = argparse.ArgumentParser(
        description="HakuRiver Docker Client: Manage Host-side Docker containers and tarballs.",
        usage="%(prog)s [options] <command> [command-options]",
        allow_abbrev=False,
    )

    # Global arguments
    parser.add_argument(
        "--host",
        metavar="HOST",
        default=None,
        help=f"Host address (default: {CLI_CONFIG.HOST_ADDRESS})",
    )
    parser.add_argument(
        "--port",
        type=int,
        metavar="PORT",
        default=None,
        help=f"Host port (default: {CLI_CONFIG.HOST_PORT})",
    )

    # --- Subcommands ---
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: list (containers on Host)
    subparsers.add_parser("list-containers", help="List Docker containers on the Host.")

    # Command: create (container on Host)
    parser_create_container = subparsers.add_parser(
        "create-container", help="Create a persistent Docker container on the Host."
    )
    parser_create_container.add_argument(
        "image_name", help="Public Docker image name (e.g., ubuntu:latest)."
    )
    parser_create_container.add_argument(
        "container_name", help="Desired name for the container on the Host."
    )

    # Command: delete (container on Host)
    parser_delete_container = subparsers.add_parser(
        "delete-container", help="Delete a persistent Docker container on the Host."
    )
    parser_delete_container.add_argument(
        "container_name", help="Name of the container to delete."
    )

    # Command: stop (container on Host)
    parser_stop_container = subparsers.add_parser(
        "stop-container", help="Stop a running Docker container on the Host."
    )
    parser_stop_container.add_argument(
        "container_name", help="Name of the container to stop."
    )

    # Command: start (container on Host)
    parser_start_container = subparsers.add_parser(
        "start-container", help="Start a stopped Docker container on the Host."
    )
    parser_start_container.add_argument(
        "container_name", help="Name of the container to start."
    )

    # Command: list-tars (tarballs in shared dir)
    subparsers.add_parser(
        "list-tars",
        help="List available HakuRiver container tarballs in the shared directory.",
    )

    # Command: create-tar (from container on Host)
    parser_create_tar = subparsers.add_parser(
        "create-tar", help="Create a HakuRiver container tarball from a Host container."
    )
    parser_create_tar.add_argument(
        "container_name",
        help="Name of the Host container to commit and create a tarball from.",
    )

    args = parser.parse_args()

    # Apply host/port overrides
    if args.host:
        CLI_CONFIG.HOST_ADDRESS = args.host
    if args.port:
        CLI_CONFIG.HOST_PORT = args.port

    host_url = _get_host_url()
    default_timeout = 10.0

    # --- Execute Command ---
    try:
        # some commands require longer execution time
        timeout = default_timeout
        if args.command in {"create-container", "create-tar"}:
            timeout += 180

        with httpx.Client(base_url=host_url, timeout=timeout) as client:
            if args.command == "list-containers":
                logger.info(
                    f"Listing Host containers from {host_url}/docker/host/containers..."
                )
                response = client.get("/docker/host/containers")
                response.raise_for_status()
                print_json_response(response)

            elif args.command == "create-container":
                logger.info(
                    f"Creating Host container '{args.container_name}' from image '{args.image_name}' at {host_url}/docker/host/create..."
                )
                payload = {
                    "image_name": args.image_name,
                    "container_name": args.container_name,
                }
                response = client.post("/docker/host/create", json=payload)
                response.raise_for_status()
                print_json_response(response)

            elif args.command == "delete-container":
                logger.info(
                    f"Deleting Host container '{args.container_name}' at {host_url}/docker/host/delete/{args.container_name}..."
                )
                response = client.post(f"/docker/host/delete/{args.container_name}")
                response.raise_for_status()
                print_json_response(response)

            elif args.command == "stop-container":
                logger.info(
                    f"Stopping Host container '{args.container_name}' at {host_url}/docker/host/stop/{args.container_name}..."
                )
                response = client.post(f"/docker/host/stop/{args.container_name}")
                response.raise_for_status()
                print_json_response(response)

            elif args.command == "start-container":
                logger.info(
                    f"Starting Host container '{args.container_name}' at {host_url}/docker/host/start/{args.container_name}..."
                )
                response = client.post(f"/docker/host/start/{args.container_name}")
                response.raise_for_status()
                print_json_response(response)

            elif args.command == "list-tars":
                logger.info(
                    f"Listing HakuRiver tarballs from {host_url}/docker/list..."
                )
                response = client.get("/docker/list")
                response.raise_for_status()
                print_json_response(response)

            elif args.command == "create-tar":
                logger.info(
                    f"Creating HakuRiver tarball from Host container '{args.container_name}' at {host_url}/docker/create_tar/{args.container_name}..."
                )
                response = client.post(f"/docker/create_tar/{args.container_name}")
                response.raise_for_status()
                print_json_response(response)

            elif args.command is None:
                parser.print_help()

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error occurred: {e}")
        logger.error("Response:")
        print_json_response(e.response)
        sys.exit(1)
    except httpx.RequestError as e:
        logger.error(f"Network error occurred while connecting to {host_url}: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
