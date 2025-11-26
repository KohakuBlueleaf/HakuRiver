"""
General HakuRiver client CLI.

Usage:
    hakuriver.client nodes
    hakuriver.client health [HOSTNAME]
    hakuriver.client status TASK_ID
    hakuriver.client kill TASK_ID
    hakuriver.client command TASK_ID pause|resume
"""

import argparse
import logging
import sys

import httpx

from hakuriver.cli import api_client, config as CLI_CONFIG

logger = logging.getLogger(__name__)


def main():
    """Parse arguments and execute the requested client action."""
    parser = argparse.ArgumentParser(
        description="HakuRiver Client: General cluster information and task control.",
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

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Nodes Command
    subparsers.add_parser("nodes", help="List node status.")

    # Health Command
    parser_health = subparsers.add_parser("health", help="Get node health status.")
    parser_health.add_argument(
        "hostname",
        metavar="HOSTNAME",
        nargs="?",
        help="Optional: Get health status for a specific hostname.",
    )

    # Status Command
    parser_status = subparsers.add_parser(
        "status", help="Check status for any task ID."
    )
    parser_status.add_argument(
        "task_id",
        metavar="TASK_ID",
        help="The ID of the task to check.",
    )

    # Kill Command
    parser_kill = subparsers.add_parser("kill", help="Kill any task by ID.")
    parser_kill.add_argument(
        "task_id",
        metavar="TASK_ID",
        help="The ID of the task to kill.",
    )

    # Command Command
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

    # Apply host/port overrides
    if args.host:
        CLI_CONFIG.HOST_ADDRESS = args.host
    if args.port:
        CLI_CONFIG.HOST_PORT = args.port

    # Dispatch based on command
    try:
        if args.command is None:
            parser.print_help(sys.stderr)
            sys.exit(1)

        elif args.command == "nodes":
            logger.info("Listing nodes...")
            api_client.list_nodes()

        elif args.command == "health":
            target_host = args.hostname
            logger.info(
                f"Fetching health status for "
                f"{'node ' + target_host if target_host else 'all nodes'}..."
            )
            api_client.get_health(target_host)

        elif args.command == "status":
            logger.info(f"Checking status for task: {args.task_id}")
            api_client.check_status(args.task_id)

        elif args.command == "kill":
            logger.info(f"Requesting kill for task: {args.task_id}")
            api_client.kill_task(args.task_id)

        elif args.command == "command":
            logger.info(f"Sending '{args.action}' command to task {args.task_id}...")
            api_client.send_task_command(args.task_id, args.action)

    except httpx.HTTPStatusError:
        sys.exit(1)
    except httpx.RequestError:
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
