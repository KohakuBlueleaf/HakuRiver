import argparse
import os
import sys
import time
import re
import json
import toml

import hakuriver.core.client as client_core
from hakuriver.utils.logger import logger  # Import logger setup by core


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


def update_config(config_instance, custom_config_data):
    """Updates attributes of the config instance based on custom data."""
    # Client doesn't have its own logger typically
    if not config_instance or not isinstance(custom_config_data, dict):
        return

    log_prefix = f"{type(config_instance).__name__}"  # e.g., "ClientConfig"
    print("Applying custom configuration overrides...")

    for key, value in custom_config_data.items():
        if isinstance(value, dict):
            # Handle nested TOML sections mapping to potentially flat config attributes
            for sub_key, sub_value in value.items():
                if hasattr(config_instance, sub_key):
                    current_sub_value = getattr(config_instance, sub_key)
                    print(
                        f"  Overriding {log_prefix}.{sub_key} from section '{key}': {current_sub_value} -> {sub_value}"
                    )
                    try:
                        setattr(config_instance, sub_key, sub_value)
                    except AttributeError:
                        print(
                            f"  Warning: Could not set {log_prefix}.{sub_key} (read-only?)"
                        )
        elif hasattr(config_instance, key):
            # Handle direct attribute overrides
            current_value = getattr(config_instance, key)
            print(f"  Overriding {log_prefix}.{key}: {current_value} -> {value}")
            try:
                setattr(config_instance, key, value)
            except AttributeError:
                print(f"  Warning: Could not set {log_prefix}.{key} (read-only?)")
    print("Custom configuration applied.")


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
            print(
                f"Warning: Ignoring invalid environment variable format: {item}",
                file=sys.stderr,
            )
    return result


# --- Main Execution Logic ---


def main():
    """Parses arguments and executes the requested client action."""

    # --- Setup Argument Parser ---
    # Use allow_abbrev=False to disallow abbreviated options like -co for --cores
    parser = argparse.ArgumentParser(
        description="HakuRiver Client: Submit tasks or manage cluster.",
        usage="%(prog)s [options] [--] [COMMAND ARGUMENTS...]",
        allow_abbrev=False,
    )

    # --- Configuration Argument ---
    # Add --config here, parsed along with everything else
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Path to a custom TOML configuration file to override defaults.",
        default=None,
    )

    # --- Action Flags (Mutually Exclusive) ---
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument("--status", metavar="TASK_ID", help="Check task status.")
    action_group.add_argument("--kill", metavar="TASK_ID", help="Kill a running task.")
    action_group.add_argument(
        "--list-nodes", action="store_true", help="List node status."
    )
    action_group.add_argument(
        "--health",
        metavar="HOSTNAME",
        nargs="?",
        const=True,
        help="Get health status for all nodes or a specific HOSTNAME.",
    )

    parser.add_argument(
        "--target",
        action="append",  # Allow multiple targets
        metavar="HOST[:NUMA_ID]",
        help="Target node or node:numa_id (repeatable for multi-node submission). Required for submission.",
        default=[],  # Start with empty list
    )
    parser.add_argument(
        "--cores",
        type=int,
        default=0,
        help="CPU cores required (per target). Default: 1.",
    )
    parser.add_argument(
        "--memory",
        type=str,
        default=None,
        metavar="SIZE",
        help="Memory limit per target (e.g., '512M', '4G'). Optional.",
    )
    parser.add_argument(
        "--env",
        action="append",
        metavar="KEY=VALUE",
        help="Environment variables (repeatable).",
        default=[],
    )

    parser.add_argument(
        "--container",
        type=str,
        default=None,
        metavar="NAME",
        help='HakuRiver container name (e.g., "myenv"). Uses default if not specified. Use "NULL" to disable Docker.',
    )
    parser.add_argument(
        "--privileged",
        action="store_true",
        help="Run container with --privileged flag (overrides default).",
    )
    parser.add_argument(
        "--mount",
        action="append",
        metavar="HOST_PATH:CONTAINER_PATH",
        default=[],
        help="Additional host directories to mount into the container (repeatable). Overrides default mounts.",
    )

    parser.add_argument("--wait", action="store_true", help="Wait for submitted task.")
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=1,
        metavar="SEC",
        help="Seconds between status checks when waiting (Default: 1).",
    )

    parser.add_argument(
        "command_and_args",
        nargs=argparse.REMAINDER,
        metavar="COMMAND ARGS...",
        help="Command and arguments to execute.",
    )

    args = parser.parse_args()

    # --- Load Custom Config (if specified) ---
    custom_config_data = None
    if args.config:
        config_path = os.path.abspath(args.config)
        if not os.path.exists(config_path):
            print(
                f"Error: Custom config file not found: {config_path}", file=sys.stderr
            )
            sys.exit(1)
        try:
            with open(config_path, "r") as f:
                custom_config_data = toml.load(f)
            print(f"Loaded custom configuration from: {config_path}")
        except (toml.TomlDecodeError, IOError) as e:
            print(
                f"Error loading or reading config file '{config_path}': {e}",
                file=sys.stderr,
            )
            sys.exit(1)

    # --- Apply Custom Config Overrides (if custom config was loaded) ---
    if custom_config_data:
        # Pass the instance from the imported module to the update function
        update_config(client_core.CLIENT_CONFIG, custom_config_data)

    # --- Determine Action and Dispatch ---
    action_taken = False
    try:
        if args.status:
            if args.command_and_args:
                parser.error("Cannot provide command arguments when using --status.")
            print(f"Checking status for task: {args.status}")
            client_core.check_status(args.status)
            action_taken = True

        elif args.kill:
            if args.command_and_args:
                parser.error("Cannot provide command arguments when using --kill.")
            print(f"Requesting kill for task: {args.kill}")
            client_core.kill_task(args.kill)
            action_taken = True

        elif args.health:
            if args.command_and_args:
                parser.error("Cannot provide command arguments when using --health.")
            target_host = args.health if isinstance(args.health, str) else None
            print(
                f"Fetching health status for {'node ' + target_host if target_host else 'all nodes'}..."
            )
            client_core.get_health(target_host)  # Call new core function
            action_taken = True

        elif args.list_nodes:
            if args.command_and_args:
                parser.error(
                    "Cannot provide command arguments when using --list-nodes."
                )
            print("Listing nodes...")
            client_core.list_nodes()
            action_taken = True

        elif args.command_and_args:
            # Submit action
            action_taken = True
            command_parts = args.command_and_args
            if command_parts and command_parts[0] == "--":
                command_parts = command_parts[1:]
            if not command_parts:
                parser.error("No command specified for submission.")

            command_to_run = command_parts[0]
            command_arguments = command_parts[1:]

            print(
                f"Submitting command '{command_to_run}' with args {command_arguments}"
            )

            if args.cores < 0:
                parser.error("--cores must be a positive integer or 0.")

            memory_bytes = None
            if args.memory:
                try:
                    memory_bytes = parse_memory_string(args.memory)
                except ValueError as e:
                    parser.error(f"Invalid --memory value: {e}")

            env_vars = parse_key_value(args.env)

            # Map CLI args to TaskRequest optional fields (None means use host default)
            # --privileged flag is present -> True, absent -> None
            privileged_override = True if args.privileged else None
            # --mount list is empty -> None, non-empty -> list
            additional_mounts_override = args.mount if args.mount else None

            logger.info(
                f"Submitting command '{command_to_run}' "
                f"with args {command_arguments} "
                f"to targets: {', '.join(args.target)}. "
                f"Cores: {args.cores}, Memory: {args.memory}. "
                f"Container: {args.container if args.container else 'default'}, "
                f"Privileged: {privileged_override if privileged_override is not None else 'default'}, "
                f"Mounts: {additional_mounts_override if additional_mounts_override is not None else 'default'}."
            )

            # Call the updated core function
            task_ids = client_core.submit_task(
                command=command_to_run,
                args=command_arguments,
                env=env_vars,
                cores=args.cores,
                memory_bytes=memory_bytes,
                targets=args.target,  # Pass the list of targets
                container_name=args.container,  # Pass the specified container name (or None)
                privileged=privileged_override,  # Pass True or None
                additional_mounts=additional_mounts_override,  # Pass list or None
            )

            if not task_ids:
                logger.error("Task submission failed. No task IDs received from host.")
                sys.exit(1)

            logger.info(
                f"Host accepted submission. Created Task IDs: {', '.join(task_ids)}"
            )

            if args.wait:
                if len(task_ids) > 1:
                    logger.warning(
                        "`--wait` requested for multi-target submission. Waiting for ALL tasks individually."
                    )
                    # Implement waiting for multiple tasks if desired, otherwise just warn/exit.
                    # For now, let's proceed but it might be long/noisy.

                all_finished_normally = True
                final_states = ["completed", "failed", "killed", "lost", "killed_oom"]
                task_final_status = {}  # Track final status of each task

                while len(task_final_status) < len(task_ids):
                    waiting_for_ids = [
                        tid for tid in task_ids if tid not in task_final_status
                    ]
                    logger.info(
                        f"Waiting for tasks: {', '.join(waiting_for_ids)} (checking every {args.poll_interval}s)..."
                    )

                    # Check status for each remaining task
                    # Add a small delay between checks if many tasks to avoid hammering host
                    for i, task_id_to_check in enumerate(waiting_for_ids):
                        if i > 0 and len(waiting_for_ids) > 5:
                            time.sleep(0.1)  # Small delay

                        current_status = client_core.check_status(
                            task_id_to_check
                        )  # This prints details
                        if current_status is None:
                            logger.warning(
                                f"Could not get status for task {task_id_to_check}. Will retry."
                            )
                            # Consider adding retry limit per task
                        elif current_status in final_states:
                            logger.info(
                                f"Task {task_id_to_check} finished with status: {current_status}"
                            )
                            task_final_status[task_id_to_check] = current_status
                            if current_status not in ["completed"]:
                                all_finished_normally = False
                        else:
                            # Status is pending/running/assigning, continue waiting
                            pass  # check_status already printed the details

                    if len(task_final_status) < len(task_ids):
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

        if not action_taken:
            parser.print_help()
            sys.exit(0)

    except Exception as e:
        print(f"\nError during client command execution: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
