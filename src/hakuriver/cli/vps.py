"""
HakuRiver VPS CLI: Submit and manage VPS tasks.

Usage:
    hakuriver.vps submit --target HOST[:NUMA_ID][::GPU_IDS] [options]
    hakuriver.vps status
    hakuriver.vps kill TASK_ID
    hakuriver.vps command TASK_ID pause|resume

SSH Key Modes:
    --no-ssh-key       Create VPS without SSH key (passwordless root)
    --gen-ssh-key      Generate SSH keypair (saves private key locally)
    --public-key-file  Upload existing public key (default behavior)
    --public-key-string  Upload public key as string
"""

import argparse
import logging
import os
import sys

import httpx

from hakuriver.cli import api_client, config as CLI_CONFIG
from hakuriver.utils.cli import parse_memory_string
from hakuriver.utils.ssh_key import (
    generate_ssh_keypair,
    get_default_key_output_path,
    read_public_key_file,
)

logger = logging.getLogger(__name__)


def main():
    """Parses arguments and executes the requested VPS task action."""

    parser = argparse.ArgumentParser(
        description="HakuRiver VPS CLI: Submit and manage VPS tasks.",
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

    # Subcommands for VPS operations
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Submit Command
    parser_submit = subparsers.add_parser("submit", help="Submit a new VPS task.")
    parser_submit.add_argument(
        "--target",
        metavar="HOST[:NUMA_ID][::GPU_ID1[,GPU_ID2,...]]",
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

    # Options for SSH key mode - mutually exclusive group
    ssh_key_group = parser_submit.add_mutually_exclusive_group(required=False)
    ssh_key_group.add_argument(
        "--no-ssh-key",
        action="store_true",
        help="Create VPS without SSH key authentication (passwordless root login).",
    )
    ssh_key_group.add_argument(
        "--gen-ssh-key",
        action="store_true",
        help="Generate a new SSH keypair. Private key saved to --key-out-file location.",
    )
    ssh_key_group.add_argument(
        "--public-key-string",
        metavar="KEY_STRING",
        help="Provide the SSH public key directly as a string.",
    )
    ssh_key_group.add_argument(
        "--public-key-file",
        metavar="PATH",
        help="Path to a file containing the SSH public key (e.g., ~/.ssh/id_rsa.pub). "
        "Reads ~/.ssh/id_rsa.pub or ~/.ssh/id_ed25519.pub by default.",
    )

    # Key output path for --gen-ssh-key mode
    parser_submit.add_argument(
        "--key-out-file",
        metavar="PATH",
        help="Path to save generated private key (default: ~/.ssh/id-hakuriver-<task_id>). "
        "Only used with --gen-ssh-key.",
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

        elif args.command == "submit":
            # --- Determine SSH Key Mode ---
            ssh_key_mode = "upload"  # Default mode
            public_key_string = None
            key_out_file = args.key_out_file if hasattr(args, "key_out_file") else None

            if args.no_ssh_key:
                # No SSH key mode - passwordless root login
                ssh_key_mode = "none"
                public_key_string = None
                logger.info(
                    "VPS will be created without SSH key (passwordless root login)."
                )

            elif args.gen_ssh_key:
                # Generate SSH key mode - will generate after we get task_id
                ssh_key_mode = "generate"
                public_key_string = None
                logger.info("SSH keypair will be generated for this VPS.")

            elif args.public_key_string:
                # Direct public key string
                ssh_key_mode = "upload"
                public_key_string = args.public_key_string.strip()
                logger.debug("Using public key provided as string.")

            elif args.public_key_file:
                # Public key from file
                ssh_key_mode = "upload"
                try:
                    public_key_string = read_public_key_file(args.public_key_file)
                    logger.debug(f"Using public key from file: {args.public_key_file}")
                except (FileNotFoundError, IOError, Exception) as e:
                    logger.error(f"Failed to read public key file: {e}")
                    sys.exit(1)

            else:
                # Try default locations (default upload mode)
                ssh_key_mode = "upload"
                default_keys = [
                    os.path.join(os.path.expanduser("~"), ".ssh", "id_rsa.pub"),
                    os.path.join(os.path.expanduser("~"), ".ssh", "id_ed25519.pub"),
                ]
                for default_path in default_keys:
                    if os.path.exists(default_path):
                        try:
                            public_key_string = read_public_key_file(default_path)
                            logger.info(
                                f"Using default public key file: {default_path}"
                            )
                            break
                        except (IOError, Exception) as e:
                            logger.warning(
                                f"Could not read default key file '{default_path}': {e}. Trying next default..."
                            )
                            public_key_string = None

                # If no default key found and no explicit mode, error
                if not public_key_string:
                    parser_submit.error(
                        "No SSH public key provided. Use one of:\n"
                        "  --no-ssh-key          (passwordless root login)\n"
                        "  --gen-ssh-key         (generate new keypair)\n"
                        "  --public-key-file     (upload existing key)\n"
                        "  --public-key-string   (provide key as string)\n"
                        "Or place a key in ~/.ssh/id_rsa.pub or ~/.ssh/id_ed25519.pub."
                    )

            # --- Parse Target and GPUs ---
            target_str = args.target
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
                f"SSH Key Mode: {ssh_key_mode}. "
                f"Cores: {args.cores}, Memory: {args.memory}, GPUs: {vps_gpu_ids}. "
                f"Container: {args.container if args.container else 'default'}, "
                f"Privileged: {privileged_override if privileged_override is not None else 'default'}, "
                f"Mounts: {additional_mounts_override if additional_mounts_override is not None else 'default'}."
            )

            result = api_client.create_vps(
                ssh_key_mode=ssh_key_mode,
                public_key=public_key_string,
                cores=args.cores,
                memory_bytes=memory_bytes,
                target=target_host_numa,
                container_name=args.container,
                privileged=privileged_override,
                additional_mounts=additional_mounts_override,
                gpu_ids=vps_gpu_ids,
            )

            if not result or not result.get("task_id"):
                logger.error(
                    "VPS task submission failed. No task ID received from host."
                )
                sys.exit(1)

            task_id = result.get("task_id")
            logger.info(f"Host accepted VPS submission. Created Task ID: {task_id}")

            # Handle generated SSH key if mode is "generate"
            if ssh_key_mode == "generate" and result.get("ssh_private_key"):
                # Determine output path
                out_path = key_out_file or get_default_key_output_path(task_id)
                out_path = os.path.expanduser(out_path)

                # Ensure ~/.ssh directory exists
                ssh_dir = os.path.dirname(out_path)
                if ssh_dir:
                    os.makedirs(ssh_dir, exist_ok=True)

                # Write private key
                with open(out_path, "w") as f:
                    f.write(result["ssh_private_key"])
                os.chmod(out_path, 0o600)

                # Write public key
                public_key_path = f"{out_path}.pub"
                if result.get("ssh_public_key"):
                    with open(public_key_path, "w") as f:
                        f.write(result["ssh_public_key"])
                    os.chmod(public_key_path, 0o644)

                logger.info(f"SSH private key saved to: {out_path}")
                print(f"\nSSH private key saved to: {out_path}")
                print(f"SSH public key saved to: {public_key_path}")
                print(f"\nTo connect: ssh -i {out_path} root@<host> -p <ssh_port>")

        elif args.command == "status":
            logger.info("Fetching active VPS tasks...")
            api_client.get_active_vps_status()

        elif args.command == "kill":
            logger.info(f"Requesting kill for VPS task: {args.task_id}")
            api_client.kill_task(args.task_id)

        elif args.command == "command":
            logger.info(
                f"Sending '{args.action}' command to VPS task {args.task_id}..."
            )
            api_client.send_task_command(args.task_id, args.action)

    except httpx.HTTPStatusError:
        logger.error("HTTP error occurred.")
        sys.exit(1)
    except httpx.RequestError:
        logger.error("Network error occurred.")
        sys.exit(1)
    except Exception as e:
        logger.exception(
            f"An unexpected error occurred during VPS command execution: {e}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
