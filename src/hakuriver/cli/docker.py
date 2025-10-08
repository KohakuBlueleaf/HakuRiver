# src/hakuriver/cli/docker.py
import argparse
import os
import sys
import json
import toml
import httpx

# HakuRiver imports (assume they exist in the package)
from hakuriver.core.client import CLIENT_CONFIG
from hakuriver.utils.logger import logger


def parse_key_value(items: list[str]) -> dict[str, str]:
    """Parses ['KEY1=VAL1', 'KEY2=VAL2'] into {'KEY1': 'VAL1', 'KEY2': 'VAL2'}"""
    result = {}
    if not items:
        return result
    for item in items:
        parts = item.split("=", 1)
        if len(parts) == 2:
            result[parts[0].strip()] = parts[1].strip()
        else:
            logger.warning(f"Ignoring invalid environment variable format: {item}")
    return result


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

    # --- Configuration Argument ---
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Path to a custom TOML configuration file to override defaults.",
        default=None,
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

    # --- Load and Apply Custom Config ---
    custom_config_data = None
    if args.config:
        config_path = os.path.abspath(args.config)
        if not os.path.exists(config_path):
            logger.error(f"Custom config file not found: {config_path}")
            sys.exit(1)
        try:
            with open(config_path, "r") as f:
                custom_config_data = toml.load(f)
            logger.info(f"Loaded custom configuration from: {config_path}")
        except (toml.TomlDecodeError, IOError) as e:
            logger.error(f"Error loading or reading config file '{config_path}': {e}")
            sys.exit(1)

    if custom_config_data:
        for key, val in custom_config_data.items():
            CLIENT_CONFIG.update_setting(key, val)

    # --- Execute Command ---
    host_url = CLIENT_CONFIG.host_url
    timeout = CLIENT_CONFIG.default_timeout  # Use default timeout

    try:
        # some command require longer execution time
        with httpx.Client(
            base_url=host_url,
            timeout=timeout
            + 180 * (args.command in {"create-container", "create-tar"}),
        ) as client:
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
