import argparse
import os
import sys
import toml
import httpx

import hakuriver.core.client as client_core
from hakuriver.core.config import CLIENT_CONFIG
from hakuriver.utils.logger import logger
from hakuriver.utils.ssh_key import read_public_key_file
from hakuriver.utils.cli import parse_memory_string
from .client import update_client_config_from_toml


def main():
    """Parses arguments and executes the requested VPS task action."""

    parser = argparse.ArgumentParser(
        description="HakuRiver VPS CLI: Submit and manage VPS tasks.",
        allow_abbrev=False,
    )

    # Global Configuration Argument
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Path to a custom TOML configuration file to override defaults.",
        default=None,
    )

    # Subcommands for VPS operations
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Submit Command
    parser_submit = subparsers.add_parser("submit", help="Submit a new VPS task.")
    parser_submit.add_argument(
        "--target",
        metavar="HOST[:NUMA_ID][::GPU_ID1[,GPU_ID2,...]]",  # Keep same format for consistency
        help="Target node or node:numa_id. Only one target allowed for VPS.",
        default=None,
    )
    parser_submit.add_argument(
        "--cores",
        type=int,
        default=0,
        help="CPU cores required for the VPS (Default: 1).",
    )
    parser_submit.add_argument(
        "--memory",
        type=str,
        default=None,
        metavar="SIZE",
        help="Memory limit for the VPS (e.g., '512M', '4G'). Optional.",
    )
    parser_submit.add_argument(
        "--container",
        type=str,
        default=None,
        metavar="NAME",
        help='HakuRiver container name (e.g., "myenv"). Uses default if not specified.',
    )
    parser_submit.add_argument(
        "--privileged",
        action="store_true",
        help="Run container with --privileged flag (overrides default).",
    )
    parser_submit.add_argument(
        "--mount",
        action="append",
        metavar="HOST_PATH:CONTAINER_PATH",
        default=[],
        help="Additional host directories to mount into the container (repeatable). Overrides default mounts.",
    )

    # Options for public key input - mutually exclusive group
    pubkey_group = parser_submit.add_mutually_exclusive_group(
        required=False
    )  # Not required initially due to implicit default
    pubkey_group.add_argument(
        "--public-key-string",
        metavar="KEY_STRING",
        help="Provide the SSH public key directly as a string.",
    )
    pubkey_group.add_argument(
        "--public-key-file",
        metavar="PATH",
        help="Path to a file containing the SSH public key (e.g., ~/.ssh/id_rsa.pub). Reads ~/.ssh/id_rsa.pub or ~/.ssh/id_ed25519.pub by default if neither --public-key-string nor --public-key-file is specified.",
    )

    # Status Command (List active VPS tasks)
    subparsers.add_parser("status", help="List active VPS tasks.")

    # Kill Command (Specific to VPS task IDs)
    parser_kill = subparsers.add_parser("kill", help="Kill a VPS task by ID.")
    parser_kill.add_argument(
        "task_id",
        metavar="TASK_ID",
        help="The ID of the VPS task to kill.",
    )

    # Command Command (Pause/Resume specific to VPS task IDs)
    parser_command = subparsers.add_parser(
        "command", help="Send a control command (pause, resume) to a VPS task by ID."
    )
    parser_command.add_argument(
        "task_id",
        metavar="TASK_ID",
        help="The ID of the VPS task.",
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

        elif args.command == "submit":
            # --- Get Public Key ---
            public_key_string = None
            if args.public_key_string:
                public_key_string = args.public_key_string.strip()
                logger.debug("Using public key provided as string.")
            elif args.public_key_file:
                try:
                    public_key_string = read_public_key_file(args.public_key_file)
                    logger.debug(f"Using public key from file: {args.public_key_file}")
                except (FileNotFoundError, IOError, Exception) as e:
                    logger.error(f"Failed to read public key file: {e}")
                    sys.exit(1)
            else:
                # Try default locations
                default_keys = [
                    os.path.join(os.path.expanduser("~"), ".ssh", "id_rsa.pub"),
                    os.path.join(os.path.expanduser("~"), ".ssh", "id_ed25519.pub"),
                    # Add other common key types here if needed
                ]
                for default_path in default_keys:
                    if os.path.exists(default_path):
                        try:
                            public_key_string = read_public_key_file(default_path)
                            logger.info(
                                f"Using default public key file: {default_path}"
                            )
                            break  # Found and read a key, stop searching
                        except (IOError, Exception) as e:
                            logger.warning(
                                f"Could not read default key file '{default_path}': {e}. Trying next default..."
                            )
                            public_key_string = (
                                None  # Ensure it's None if reading failed
                            )

            if not public_key_string:
                parser_submit.error(
                    "No SSH public key provided. Use --public-key-string, "
                    "--public-key-file, or place a key in ~/.ssh/id_rsa.pub "
                    "or ~/.ssh/id_ed25519.pub."
                )

            # --- Parse Target and GPUs ---
            # VPS only supports a single target currently as per Host logic
            if isinstance(args.target, list) and len(args.target) > 1:
                parser_submit.error("Only one --target is allowed for VPS submission.")

            target_str = (
                args.target[0] if isinstance(args.target, list) else args.target
            )
            vps_gpu_ids = []
            target_host_numa = target_str
            if target_str and "::" in target_str:
                target_host_numa, gpu_str = target_str.split("::", 1)
                try:
                    vps_gpu_ids = [
                        int(g.strip()) for g in gpu_str.split(",") if g.strip()
                    ]
                except ValueError:
                    parser_submit.error(
                        f"Invalid GPU ID format in target '{target_str}'. GPU IDs must be integers separated by commas."
                    )

            if args.cores < 0:
                parser_submit.error("--cores must be a non-negative integer.")

            memory_bytes = None
            if args.memory:
                try:
                    memory_bytes = parse_memory_string(args.memory)
                except ValueError as e:
                    parser_submit.error(f"Invalid --memory value: {e}")

            additional_mounts_override = args.mount if args.mount else None
            privileged_override = True if args.privileged else None

            logger.info(
                f"Submitting VPS task to target: {target_str}. "
                f"Cores: {args.cores}, Memory: {args.memory}, GPUs: {vps_gpu_ids}. "
                f"Container: {args.container if args.container else 'default'}, "
                f"Privileged: {privileged_override if privileged_override is not None else 'default'}, "
                f"Mounts: {additional_mounts_override if additional_mounts_override is not None else 'default'}."
            )

            task_ids = client_core.create_vps(
                public_key=public_key_string,
                cores=args.cores,
                memory_bytes=memory_bytes,
                targets=target_host_numa,
                container_name=args.container,
                privileged=privileged_override,
                additional_mounts=additional_mounts_override,
                gpu_ids=vps_gpu_ids,
            )

            if not task_ids:
                logger.error(
                    "VPS task submission failed. No task IDs received from host."
                )
                sys.exit(1)

            # Host's create_vps returns response including ssh_port in runner_response field
            # The submit_payload function called by create_vps already prints the full response
            # including runner_response, so no extra print needed here for the port.

            logger.info(f"Host accepted VPS submission. Created Task ID: {task_ids[0]}")

        elif args.command == "status":
            logger.info("Fetching active VPS tasks...")
            client_core.get_active_vps_status()  # Call the new core client function

        elif args.command == "kill":
            # argparse handles required task_id
            logger.info(f"Requesting kill for VPS task: {args.task_id}")
            # Call the general kill function, Host handles the type
            client_core.kill_task(args.task_id)

        elif args.command == "command":
            # argparse handles required args
            logger.info(
                f"Sending '{args.action}' command to VPS task {args.task_id}..."
            )
            # Call the general command function, Host handles the type/state check
            client_core.send_task_command(args.task_id, args.action)

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error occurred.")
        sys.exit(1)
    except httpx.RequestError as e:
        logger.error(f"Network error occurred.")
        sys.exit(1)
    except Exception as e:
        logger.exception(
            f"An unexpected error occurred during VPS command execution: {e}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
