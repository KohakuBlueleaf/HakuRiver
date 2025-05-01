import argparse
import os
import sys
import time
import re
import toml
import httpx

import hakuriver.core.client as client_core
from hakuriver.utils.logger import logger
from hakuriver.core.config import CLIENT_CONFIG


def parse_memory_string(mem_str: str) -> int | None:
    """Parses memory string like '4G', '512M', '2K' into bytes."""
    if not mem_str:
        return None
    mem_str = mem_str.upper().strip()
    match = re.match(r"^(\d+)([KMG]?)$", mem_str)
    if not match:
        raise ValueError(
            f"Invalid memory format: '{mem_str}'. Use suffix K, M, or G (e.g., 512M, 4G)."
        )

    val = int(match.group(1))
    unit = match.group(2)

    if unit == "G":
        return val * 1000_000_000
    elif unit == "M":
        return val * 1000_000
    elif unit == "K":
        return val * 1000
    else:  # No unit means bytes
        return val


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


def update_client_config_from_toml(config_instance, custom_config_data):
    """Updates attributes of the CLIENT_CONFIG instance based on custom data."""
    if not config_instance or not isinstance(custom_config_data, dict):
        return

    log_prefix = f"{type(config_instance).__name__}"  # Should be "ClientConfig"
    logger.info("Applying custom configuration overrides...")

    for key, value in custom_config_data.items():
        # The ClientConfig class has flat attributes, so we primarily check direct matches
        # However, the TOML might be structured (e.g., [network] host_address).
        # We need to check if the TOML key is a section whose subkeys match config attributes.
        if isinstance(value, dict):
            # Check if any sub-keys match CLIENT_CONFIG attributes
            for sub_key, sub_value in value.items():
                if hasattr(config_instance, sub_key):
                    # This sub-key from a TOML section matches a ClientConfig attribute
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
            # Handle direct attribute overrides (top-level TOML key matches attribute)
            current_value = getattr(config_instance, key)
            logger.info(f"  Overriding {log_prefix}.{key}: {current_value} -> {value}")
            try:
                setattr(config_instance, key, value)
            except AttributeError:
                logger.warning(
                    f"  Warning: Could not set {log_prefix}.{key} (read-only?)"
                )
        else:
            # If a top-level TOML key doesn't match an attribute and isn't a dict, ignore or warn
            logger.debug(
                f"  Ignoring unknown config key/section '{key}' for ClientConfig."
            )

    logger.info("Custom configuration applied.")


def read_public_key_file(file_path: str) -> str:
    """Reads an SSH public key from a file."""
    try:
        path = os.path.expanduser(file_path)  # Expand ~
        with open(path, "r") as f:
            key = f.read().strip()
        if not key:
            raise ValueError(f"Public key file '{file_path}' is empty.")
        if not key.startswith("ssh-"):
            logger.warning(
                f"Public key in file '{file_path}' does not start with 'ssh-'. Is this a valid public key?"
            )
        return key
    except FileNotFoundError:
        raise FileNotFoundError(f"Public key file not found: '{file_path}'")
    except IOError as e:
        raise IOError(f"Error reading public key file '{file_path}': {e}")
    except Exception as e:
        raise Exception(
            f"Unexpected error processing public key file '{file_path}': {e}"
        )


# --- Main Execution Logic ---


def main():
    """Parses arguments and executes the requested client action."""

    # --- Setup Argument Parser ---
    parser = argparse.ArgumentParser(
        description="HakuRiver Client: Submit tasks or manage cluster.",
        # usage="%(prog)s [options] <command> [command-options] [arguments...]", # Usage is complex with subparsers
        allow_abbrev=False,
    )

    # --- Global Configuration Argument ---
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Path to a custom TOML configuration file to override defaults.",
        default=None,
    )

    # --- Subcommands ---
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # 1. Submit Command
    parser_submit = subparsers.add_parser(
        "submit", help="Submit a standard command task."
    )
    parser_submit.add_argument(
        "--target",
        action="append",
        metavar="HOST[:NUMA_ID][::GPU_ID1[,GPU_ID2,...]]",
        help="Target node or node:numa_id. Repeatable for multi-node submission. At least one required.",
        required=True,  # Require target for submit
        default=[],
    )
    parser_submit.add_argument(
        "--cores",
        type=int,
        default=1,  # Changed default to 1 core
        help="CPU cores required per target (Default: 1).",
    )
    parser_submit.add_argument(
        "--memory",
        type=str,
        default=None,
        metavar="SIZE",
        help="Memory limit per target (e.g., '512M', '4G'). Optional.",
    )
    parser_submit.add_argument(
        "--env",
        action="append",
        metavar="KEY=VALUE",
        help="Environment variables (repeatable).",
        default=[],
    )
    parser_submit.add_argument(
        "--container",
        type=str,
        default=None,  # Use default from config if None
        metavar="NAME",
        help='HakuRiver container name (e.g., "myenv"). Uses default if not specified. Use "NULL" to disable Docker.',
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
    parser_submit.add_argument(
        "--wait", action="store_true", help="Wait for submitted task completion."
    )
    parser_submit.add_argument(
        "--poll-interval",
        type=int,
        default=1,
        metavar="SEC",
        help="Seconds between status checks when waiting (Default: 1).",
    )
    parser_submit.add_argument(
        "command_and_args",
        nargs=argparse.REMAINDER,
        metavar="COMMAND ARGS...",
        help="Command and arguments to execute inside the container.",
    )

    # 2. Status Command
    parser_status = subparsers.add_parser("status", help="Check task status.")
    parser_status.add_argument(
        "task_id",
        metavar="TASK_ID",
        help="The ID of the task to check.",
    )

    # 3. Kill Command
    parser_kill = subparsers.add_parser("kill", help="Kill a running task.")
    parser_kill.add_argument(
        "task_id",
        metavar="TASK_ID",
        help="The ID of the task to kill.",
    )
    # Maybe add force option?

    # 4. Nodes Command
    parser_nodes = subparsers.add_parser("nodes", help="List node status.")
    # No arguments needed

    # 5. Health Command
    parser_health = subparsers.add_parser("health", help="Get node health status.")
    parser_health.add_argument(
        "hostname",
        metavar="HOSTNAME",
        nargs="?",  # Optional positional argument
        help="Optional: Get health status for a specific HOSTNAME.",
    )

    # 6. VPS Subcommands
    parser_vps = subparsers.add_parser("vps", help="Manage VPS tasks.")
    vps_subparsers = parser_vps.add_subparsers(dest="vps_command", help="VPS commands")

    # 6a. VPS Submit Command
    parser_vps_submit = vps_subparsers.add_parser("submit", help="Submit a VPS task.")
    parser_vps_submit.add_argument(
        "--target",
        metavar="HOST[:NUMA_ID][::GPU_ID1[,GPU_ID2,...]]",  # Keep same target format for consistency
        help="Target node or node:numa_id. Only one target allowed for VPS.",
        required=True,  # Require a target
    )
    parser_vps_submit.add_argument(
        "--cores",
        type=int,
        default=1,
        help="CPU cores required for the VPS (Default: 1).",
    )
    parser_vps_submit.add_argument(
        "--memory",
        type=str,
        default=None,
        metavar="SIZE",
        help="Memory limit for the VPS (e.g., '512M', '4G'). Optional.",
    )
    parser_vps_submit.add_argument(
        "--container",
        type=str,
        default=None,  # Use default from config if None
        metavar="NAME",
        help='HakuRiver container name (e.g., "myenv"). Uses default if not specified.',
    )
    parser_vps_submit.add_argument(
        "--privileged",
        action="store_true",
        help="Run container with --privileged flag (overrides default).",
    )
    parser_vps_submit.add_argument(
        "--mount",
        action="append",
        metavar="HOST_PATH:CONTAINER_PATH",
        default=[],
        help="Additional host directories to mount into the container (repeatable). Overrides default mounts.",
    )

    # Add options for public key input - mutually exclusive group
    pubkey_group = parser_vps_submit.add_mutually_exclusive_group(
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

    # 6b. VPS Status Command
    parser_vps_status = vps_subparsers.add_parser(
        "status", help="List active VPS tasks."
    )
    # No arguments needed, will list all active VPS

    # 7. Commands Command
    parser_command = subparsers.add_parser(
        "command", help="Send a control command to a task (e.g., pause, resume)."
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

    # --- Load Custom Config (if specified) ---
    # This is parsed even before subcommand specific arguments are fully validated
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

    # --- Apply Custom Config Overrides (if custom config was loaded) ---
    # Apply overrides to the global CLIENT_CONFIG instance
    if custom_config_data:
        update_client_config_from_toml(CLIENT_CONFIG, custom_config_data)

    # --- Dispatch based on subcommand ---
    try:
        if args.command is None:
            parser.print_help(sys.stderr)
            sys.exit(1)

        elif args.command == "submit":
            command_parts = args.command_and_args
            if not command_parts:
                parser_submit.error("No command specified for submission.")

            command_to_run = command_parts[0]
            command_arguments = command_parts[1:]

            if args.cores < 0:
                parser_submit.error("--cores must be a non-negative integer.")

            memory_bytes = None
            if args.memory:
                try:
                    memory_bytes = parse_memory_string(args.memory)
                except ValueError as e:
                    parser_submit.error(f"Invalid --memory value: {e}")

            env_vars = parse_key_value(args.env)

            # Map CLI args to TaskRequest optional fields (None means use host default)
            # --privileged flag is present -> True, absent -> None
            privileged_override = True if args.privileged else None
            # --mount list is empty -> None, non-empty -> list
            additional_mounts_override = args.mount if args.mount else None

            targets = []
            gpus = []
            if args.target:
                # Process each target string to extract host/numa and GPUs
                processed_targets = []
                processed_gpus = []
                for target_str in args.target:
                    if "::" in target_str:
                        target_host_numa, gpu_str = target_str.split("::", 1)
                        processed_targets.append(target_host_numa)
                        try:
                            gpu_ids = [
                                int(g.strip()) for g in gpu_str.split(",") if g.strip()
                            ]
                            processed_gpus.append(gpu_ids)
                        except ValueError:
                            parser_submit.error(
                                f"Invalid GPU ID format in target '{target_str}'. GPU IDs must be integers separated by commas."
                            )
                    else:
                        processed_targets.append(target_str)
                        processed_gpus.append([])  # No GPUs specified for this target
                targets = processed_targets
                gpus = processed_gpus

            if len(targets) != len(gpus):
                # This should not happen with the logic above but is a safety check
                parser_submit.error(
                    "Internal error: Mismatch between parsed targets and GPU lists."
                )

            logger.info(
                f"Submitting command task '{command_to_run}' "
                f"to targets: {', '.join(args.target)}. "
                f"Cores: {args.cores}, Memory: {args.memory}, GPUs: {gpus}. "
                f"Container: {args.container if args.container else 'default'}, "
                f"Privileged: {privileged_override if privileged_override is not None else 'default'}, "
                f"Mounts: {additional_mounts_override if additional_mounts_override is not None else 'default'}."
            )

            task_ids = client_core.submit_task(
                task_type="command",  # Explicitly set type
                command=command_to_run,
                args=command_arguments,
                env=env_vars,
                cores=args.cores,
                memory_bytes=memory_bytes,
                targets=targets,
                container_name=args.container,
                privileged=privileged_override,
                additional_mounts=additional_mounts_override,
                gpu_ids=gpus,  # Pass list of list of GPU IDs
            )

            if not task_ids:
                logger.error("Task submission failed. No task IDs received from host.")
                sys.exit(1)

            logger.info(
                f"Host accepted submission. Created Task ID(s): {', '.join(task_ids)}"
            )

            if args.wait:
                if len(task_ids) > 1:
                    logger.warning(
                        "`--wait` requested for multi-target submission. Waiting for ALL tasks individually."
                    )

                task_final_status = {}  # Track final status of each task
                waiting_tasks_info = {
                    tid: {"status": "pending"} for tid in task_ids
                }  # Minimal tracking

                while waiting_tasks_info:
                    waiting_for_ids = list(waiting_tasks_info.keys())
                    # logger.info( # Avoid spamming this line
                    #    f"Waiting for tasks: {', '.join(waiting_for_ids)} (checking every {args.poll_interval}s)..."
                    # )

                    # Check status for each remaining task
                    for i, task_id_to_check in enumerate(waiting_for_ids):
                        # Add a small delay between checks if many tasks to avoid hammering host
                        if i > 0 and len(waiting_for_ids) > 5:
                            time.sleep(0.05)  # Small delay

                        current_status_data = client_core.check_status(
                            task_id_to_check
                        )  # This prints details
                        if current_status_data is None:
                            logger.warning(
                                f"Could not get status for task {task_id_to_check}. Retrying..."
                            )
                            # Could add retry counter here if needed
                        elif "status" in current_status_data:
                            status = current_status_data["status"]
                            if status in [
                                "completed",
                                "failed",
                                "killed",
                                "lost",
                                "killed_oom",
                            ]:
                                logger.info(
                                    f"Task {task_id_to_check} finished with status: {status}"
                                )
                                task_final_status[task_id_to_check] = status
                                del waiting_tasks_info[
                                    task_id_to_check
                                ]  # Remove from waiting
                                if status not in ["completed"]:
                                    all_finished_normally = False
                            # else: Status is pending/running/assigning/paused, continue waiting
                            # check_status already printed the details

                    if waiting_tasks_info:
                        time.sleep(
                            args.poll_interval
                        )  # Wait before next round of checks

                logger.info("--- Wait Complete ---")
                logger.info("Final statuses:")
                for tid, status in task_final_status.items():
                    logger.info(f"  Task {tid}: {status}")
                if not all_finished_normally:
                    logger.warning("One or more tasks did not complete successfully.")
                    # Optionally exit with non-zero code
                    # sys.exit(1)

        elif args.command == "status":
            if not args.task_id:
                # This check is technically redundant because argparse handles required positional args
                # but keeping it is harmless.
                parser_status.error("task_id is required for the status command.")
            logger.info(f"Checking status for task: {args.task_id}")
            client_core.check_status(args.task_id)

        elif args.command == "kill":
            if not args.task_id:
                parser_kill.error("task_id is required for the kill command.")
            logger.info(f"Requesting kill for task: {args.task_id}")
            client_core.kill_task(args.task_id)

        elif args.command == "nodes":
            logger.info("Listing nodes...")
            client_core.list_nodes()

        elif args.command == "health":
            target_host = args.hostname
            logger.info(
                f"Fetching health status for {'node ' + target_host if target_host else 'all nodes'}..."
            )
            client_core.get_health(target_host)

        elif args.command == "command":
            if not args.task_id:
                parser_command.error("task_id is required for the command command.")
            if not args.action:
                parser_command.error(
                    "action (pause, resume) is required for the command command."
                )

            logger.info(f"Sending '{args.action}' command to task {args.task_id}...")
            client_core.send_task_command(args.task_id, args.action)

        elif args.command == "vps":
            if args.vps_command is None:
                parser_vps.print_help(sys.stderr)
                sys.exit(1)

            elif args.vps_command == "submit":
                # --- Get Public Key ---
                public_key_string = None
                if args.public_key_string:
                    public_key_string = args.public_key_string.strip()
                    logger.debug("Using public key provided as string.")
                elif args.public_key_file:
                    try:
                        public_key_string = read_public_key_file(args.public_key_file)
                        logger.debug(
                            f"Using public key from file: {args.public_key_file}"
                        )
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
                    parser_vps_submit.error(
                        "No SSH public key provided. Use --public-key-string, "
                        "--public-key-file, or place a key in ~/.ssh/id_rsa.pub "
                        "or ~/.ssh/id_ed25519.pub."
                    )

                # --- Parse Target and GPUs ---
                if not args.target:
                    parser_vps_submit.error("--target is required for VPS submission.")
                # VPS only supports a single target currently as per Host logic
                if isinstance(args.target, list) and len(args.target) > 1:
                    parser_vps_submit.error(
                        "Only one --target is allowed for VPS submission."
                    )

                # Extract GPUs from target string if present
                target_str = (
                    args.target[0] if isinstance(args.target, list) else args.target
                )  # Handle list or single string
                target_host_numa = target_str
                vps_gpu_ids = []
                if "::" in target_str:
                    target_host_numa, gpu_str = target_str.split("::", 1)
                    try:
                        vps_gpu_ids = [
                            int(g.strip()) for g in gpu_str.split(",") if g.strip()
                        ]
                    except ValueError:
                        parser_vps_submit.error(
                            f"Invalid GPU ID format in target '{target_str}'. GPU IDs must be integers separated by commas."
                        )

                if args.cores < 0:
                    parser_vps_submit.error("--cores must be a non-negative integer.")

                memory_bytes = None
                if args.memory:
                    try:
                        memory_bytes = parse_memory_string(args.memory)
                    except ValueError as e:
                        parser_vps_submit.error(f"Invalid --memory value: {e}")

                # VPS doesn't currently use env or additional mounts in the Runner setup helper,
                # but we pass them through in case the Host or Runner logic changes.
                # The TaskRequest model allows them.
                env_vars = {}  # VPS submit CLI doesn't have --env yet
                additional_mounts_override = args.mount if args.mount else None

                # --privileged flag is present -> True, absent -> None
                privileged_override = True if args.privileged else None

                logger.info(
                    f"Submitting VPS task to target: {target_str}. "
                    f"Cores: {args.cores}, Memory: {args.memory}, GPUs: {vps_gpu_ids}. "
                    f"Container: {args.container if args.container else 'default'}, "
                    f"Privileged: {privileged_override if privileged_override is not None else 'default'}, "
                    f"Mounts: {additional_mounts_override if additional_mounts_override is not None else 'default'}."
                )

                # Call the updated core function for VPS submission
                task_ids = client_core.create_vps(
                    task_type="vps",  # Explicitly set type
                    public_key=public_key_string,  # Pass the validated public key string
                    cores=args.cores,
                    memory_bytes=memory_bytes,
                    targets=target_host_numa,  # Pass the single target string
                    container_name=args.container,
                    privileged=privileged_override,
                    additional_mounts=additional_mounts_override,
                    gpu_ids=vps_gpu_ids,  # Pass the list of GPU IDs
                )

                if not task_ids:
                    logger.error(
                        "VPS task submission failed. No task IDs received from host."
                    )
                    sys.exit(1)

                # Host's create_vps returns response including ssh_port in runner_response field
                # The submit_payload function called by create_vps already prints the full response
                # including runner_response, so no extra print needed here for the port.

                logger.info(
                    f"Host accepted VPS submission. Created Task ID: {task_ids[0]}"
                )  # VPS submits only one task ID

            elif args.vps_command == "status":
                # List active VPS tasks
                logger.info("Fetching active VPS tasks...")
                # Need to call the new core client function
                client_core.get_active_vps_status()  # This function needs to be added to core/client.py

    except httpx.HTTPStatusError as e:
        # print_response is already called by client_core functions on HTTP errors
        # so we just need to exit
        logger.error(f"HTTP error occurred.")  # Error details already printed
        sys.exit(1)
    except httpx.RequestError as e:
        # Error details already printed by client_core functions
        logger.error(f"Network error occurred.")
        sys.exit(1)
    except Exception as e:
        logger.exception(
            f"An unexpected error occurred during client command execution: {e}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
