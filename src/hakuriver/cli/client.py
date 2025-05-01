import argparse
import os
import sys
import re
import toml
import httpx  # Keep httpx for potential direct client calls in future, although core handles it now

import hakuriver.core.client as client_core
from hakuriver.utils.logger import logger
from hakuriver.core.config import CLIENT_CONFIG


def update_client_config_from_toml(config_instance, custom_config_data):
    """Updates attributes of the CLIENT_CONFIG instance based on custom data."""
    if not config_instance or not isinstance(custom_config_data, dict):
        return

    log_prefix = f"{type(config_instance).__name__}"  # Should be "ClientConfig"
    logger.info("Applying custom configuration overrides...")

    for key, value in custom_config_data.items():
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                if hasattr(config_instance, sub_key):
                    current_sub_value = getattr(config_instance, sub_key)
                    logger.info(
                        f"  Overriding {log_prefix}.{sub_key} from section '{key}': {current_sub_value} -> {sub_value}"
                    )
                    try:
                        setattr(config_instance, sub_key, sub_value)
                    except AttributeError:
                        logger.warning(
                            f"  Warning: Could not set {log_prefix}.{sub_key} (read-only?)"
                        )
        elif hasattr(config_instance, key):
            current_value = getattr(config_instance, key)
            logger.info(f"  Overriding {log_prefix}.{key}: {current_value} -> {value}")
            try:
                setattr(config_instance, key, value)
            except AttributeError:
                logger.warning(
                    f"  Warning: Could not set {log_prefix}.{key} (read-only?)"
                )
        else:
            logger.debug(
                f"  Ignoring unknown config key/section '{key}' for ClientConfig."
            )

    logger.info("Custom configuration applied.")


def main():
    """Parses arguments and executes the requested general client action."""

    parser = argparse.ArgumentParser(
        description="HakuRiver Client: General cluster information and task control.",
        # usage is implicit with subparsers
        allow_abbrev=False,
    )

    # Global Configuration Argument
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Path to a custom TOML configuration file to override defaults.",
        default=None,
    )

    # Subcommands for general client operations
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Nodes Command
    subparsers.add_parser("nodes", help="List node status.")

    # Health Command
    parser_health = subparsers.add_parser("health", help="Get node health status.")
    parser_health.add_argument(
        "hostname",
        metavar="HOSTNAME",
        nargs="?",  # Optional positional argument
        help="Optional: Get health status for a specific HOSTNAME.",
    )

    # Status Command (for ANY task ID)
    parser_status = subparsers.add_parser(
        "status", help="Check status for any task ID."
    )
    parser_status.add_argument(
        "task_id",
        metavar="TASK_ID",
        help="The ID of the task to check.",
    )

    # Kill Command (for ANY task ID)
    parser_kill = subparsers.add_parser("kill", help="Kill any task by ID.")
    parser_kill.add_argument(
        "task_id",
        metavar="TASK_ID",
        help="The ID of the task to kill.",
    )

    # Command Command (for ANY task ID)
    parser_command = subparsers.add_parser(
        "command", help="Send a control command (pause, resume) to any task by ID."
    )
    parser_command.add_argument(
        "task_id",
        metavar="TASK_ID",
        help="The ID of the task.",
    )
    parser_command.add_argument(
        "action",
        metavar="ACTION",
        choices=["pause", "resume"],
        help="The control action to send (pause, resume).",
    )

    args = parser.parse_args()

    # Load and apply custom config
    custom_config_data = None
    if args.config:
        config_path = os.path.abspath(args.config)
        if not os.path.exists(config_path):
            logger.error(f"Error: Custom config file not found: {config_path}")
            sys.exit(1)
        try:
            with open(config_path, "r") as f:
                custom_config_data = toml.load(f)
            logger.info(f"Loaded custom configuration from: {config_path}")
        except (toml.TomlDecodeError, IOError) as e:
            logger.error(f"Error loading or reading config file '{config_path}': {e}")
            sys.exit(1)

    if custom_config_data:
        update_client_config_from_toml(CLIENT_CONFIG, custom_config_data)

    # Dispatch based on command
    try:
        if args.command is None:
            parser.print_help(sys.stderr)
            sys.exit(1)

        elif args.command == "nodes":
            logger.info("Listing nodes...")
            client_core.list_nodes()

        elif args.command == "health":
            target_host = args.hostname
            logger.info(
                f"Fetching health status for {'node ' + target_host if target_host else 'all nodes'}..."
            )
            client_core.get_health(target_host)

        elif args.command == "status":
            # argparse handles the required task_id positional arg check
            logger.info(f"Checking status for task: {args.task_id}")
            client_core.check_status(args.task_id)

        elif args.command == "kill":
            # argparse handles the required task_id positional arg check
            logger.info(f"Requesting kill for task: {args.task_id}")
            client_core.kill_task(args.task_id)

        elif args.command == "command":
            # argparse handles required positional args
            logger.info(f"Sending '{args.action}' command to task {args.task_id}...")
            client_core.send_task_command(args.task_id, args.action)

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error occurred.")
        sys.exit(1)
    except httpx.RequestError as e:
        logger.error(f"Network error occurred.")
        sys.exit(1)
    except Exception as e:
        logger.exception(
            f"An unexpected error occurred during client command execution: {e}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
