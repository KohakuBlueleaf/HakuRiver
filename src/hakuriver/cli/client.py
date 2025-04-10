#!/usr/bin/env python
# cli/client.py

# --- Standard Library Imports ---
import argparse
import json
import os
import shlex  # Keep for potential future use, though not needed with REMAINDER
import sys
import time

# --- Third Party Imports ---
import toml

# httpx is used by the core client functions

# --- Local Imports ---
# Delay core import until after --config is processed


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
    action_group.add_argument(
        "--status",
        metavar="TASK_ID",
        help="Check the status of a specific task.",
    )
    action_group.add_argument(
        "--kill",
        metavar="TASK_ID",
        help="Request to kill a running task.",
    )
    action_group.add_argument(
        "--list-nodes",
        action="store_true",
        help="List status of compute nodes.",
    )

    # --- Options for Submit Action ---
    parser.add_argument(
        "--cores",
        type=int,
        default=1,
        help="Number of CPU cores required (Required for submit action).",
    )
    parser.add_argument(
        "--env",
        action="append",
        metavar="KEY=VALUE",
        help="Environment variables for the task (repeatable).",
        default=[],
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for the submitted task to complete.",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=5,
        metavar="SEC",
        help="Seconds between status checks when waiting (Default: 5).",
    )

    # --- Capturing the Command and its Arguments ---
    parser.add_argument(
        "command_and_args",
        nargs=argparse.REMAINDER,
        metavar="COMMAND ARGUMENTS...",
        help="The command and its arguments to execute on the cluster.",
    )

    # --- Parse ALL Arguments ---
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

    # --- Import Core Client Logic ---
    # This import triggers default config loading via config_loader
    # AND makes client_config and API functions available.
    try:
        import hakuriver.core.client as client_core

        if not hasattr(client_core, "client_config"):
            raise ImportError(
                "Core client module does not expose 'client_config' instance."
            )
        if not hasattr(client_core, "submit_task"):
            raise ImportError(
                "Core client module does not expose expected API functions."
            )
    except ImportError as e:
        print(
            f"Error: Failed to import or initialize core client module: {e}",
            file=sys.stderr,
        )
        print(
            "Make sure HakuRiver is installed or accessible in PYTHONPATH.",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- Apply Custom Config Overrides (if custom config was loaded) ---
    if custom_config_data:
        # Pass the instance from the imported module to the update function
        update_config(client_core.client_config, custom_config_data)

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

            if args.cores is None:
                parser.error(
                    "Missing required argument: --cores is required for submitting a task."
                )
            if args.cores <= 0:
                parser.error("Argument --cores must be a positive integer.")

            env_vars = parse_key_value(args.env)
            print(
                f"Submitting command: '{command_to_run}' with args {command_arguments}"
            )
            task_id = client_core.submit_task(
                command_to_run, command_arguments, env_vars, args.cores
            )

            if task_id and args.wait:
                # (Wait logic remains the same as previous version)
                print(
                    f"\nWaiting for task {task_id} to complete (checking every {args.poll_interval}s)..."
                )
                final_states = ["completed", "failed", "killed", "lost"]
                consecutive_errors = 0
                while True:
                    time.sleep(args.poll_interval)
                    current_status = client_core.check_status(task_id)
                    if current_status is None:
                        consecutive_errors += 1
                        print(
                            f"\nWarning: Could not get task status (attempt {consecutive_errors}). Retrying...",
                            file=sys.stderr,
                            end="\r",
                            flush=True,
                        )
                        if consecutive_errors >= 3:
                            print(
                                "\nError: Failed to get task status after multiple attempts. Stopping wait."
                                + " " * 20,
                                file=sys.stderr,
                            )
                            break
                        continue
                    else:
                        if consecutive_errors > 0:
                            print(" " * 80, end="\r", flush=True)
                        consecutive_errors = 0
                    if current_status in final_states:
                        print(
                            f"\nTask {task_id} finished with status: {current_status}"
                        )
                        break
                    else:
                        print(
                            f"  (Current status: {current_status}){' '*20}",
                            end="\r",
                            flush=True,
                        )
                print()

        if not action_taken:
            parser.print_help()
            sys.exit(0)

    except Exception as e:
        print(f"\nError during client command execution: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
