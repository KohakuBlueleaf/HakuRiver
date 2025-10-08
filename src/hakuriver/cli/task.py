import argparse
import os
import sys
import time
import toml
import httpx

import hakuriver.core.client as client_core
from hakuriver.core.config import CLIENT_CONFIG
from hakuriver.utils.cli import parse_key_value, parse_memory_string
from hakuriver.utils.logger import logger
from .client import update_client_config_from_toml


def main():
    """Parses arguments and executes the requested standard task action."""

    parser = argparse.ArgumentParser(
        description="HakuRiver Task CLI: Submit and manage standard tasks.",
        allow_abbrev=False,
    )

    # Global Configuration Argument
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Path to a custom TOML configuration file to override defaults.",
        default=None,
    )

    # Subcommands for standard task operations
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Submit Command
    parser_submit = subparsers.add_parser("submit", help="Submit a new standard task.")
    parser_submit.add_argument(
        "--target",
        action="append",
        metavar="HOST[:NUMA_ID][::GPU_ID1[,GPU_ID2,...]]",
        help="Target node or node:numa_id. Repeatable for multi-node submission. At least one required.",
        default=None,
        nargs="+",
    )
    parser_submit.add_argument(
        "--cores",
        type=int,
        default=1,
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
        default=None,
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

    # Kill Command (Specific to task IDs)
    parser_kill = subparsers.add_parser("kill", help="Kill a standard task by ID.")
    parser_kill.add_argument(
        "task_id",
        metavar="TASK_ID",
        help="The ID of the standard task to kill.",
    )

    # Command Command (Pause/Resume specific to task IDs)
    parser_command = subparsers.add_parser(
        "command",
        help="Send a control command (pause, resume) to a standard task by ID.",
    )
    parser_command.add_argument(
        "task_id",
        metavar="TASK_ID",
        help="The ID of the standard task.",
    )
    parser_command.add_argument(
        "action",
        metavar="ACTION",
        choices=["pause", "resume"],
        help="The control action to send (pause, resume).",
    )

    # Get Stdout Command
    parser_stdout = subparsers.add_parser(
        "stdout", help="Get standard output for a standard task."
    )
    parser_stdout.add_argument(
        "task_id",
        metavar="TASK_ID",
        help="The ID of the standard task.",
    )

    # Get Stderr Command
    parser_stderr = subparsers.add_parser(
        "stderr", help="Get standard error for a standard task."
    )
    parser_stderr.add_argument(
        "task_id",
        metavar="TASK_ID",
        help="The ID of the standard task.",
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

            privileged_override = True if args.privileged else None
            additional_mounts_override = args.mount if args.mount else None

            targets = []
            gpus = []
            if args.target:
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
                        processed_gpus.append([])
                targets = processed_targets
                gpus = processed_gpus

            if len(targets) != len(gpus):
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
                gpu_ids=gpus,
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

                task_final_status = {}
                waiting_tasks_info = {tid: {"status": "pending"} for tid in task_ids}

                while waiting_tasks_info:
                    waiting_for_ids = list(waiting_tasks_info.keys())

                    for i, task_id_to_check in enumerate(waiting_for_ids):
                        if i > 0 and len(waiting_for_ids) > 5:
                            time.sleep(0.05)

                        current_status_data = client_core.check_status(task_id_to_check)
                        if current_status_data is None:
                            logger.warning(
                                f"Could not get status for task {task_id_to_check}. Retrying..."
                            )
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
                                del waiting_tasks_info[task_id_to_check]
                                if status not in ["completed"]:
                                    all_finished_normally = False

                    if waiting_tasks_info:
                        time.sleep(args.poll_interval)

                logger.info("--- Wait Complete ---")
                logger.info("Final statuses:")
                for tid, status in task_final_status.items():
                    logger.info(f"  Task {tid}: {status}")
                if not all_finished_normally:
                    logger.warning("One or more tasks did not complete successfully.")
                    # sys.exit(1)

        elif args.command == "kill":
            # argparse handles required task_id
            logger.info(f"Requesting kill for task: {args.task_id}")
            client_core.kill_task(args.task_id)

        elif args.command == "command":
            # argparse handles required args
            logger.info(f"Sending '{args.action}' command to task {args.task_id}...")
            client_core.send_task_command(args.task_id, args.action)

        elif args.command == "stdout":
            # argparse handles required task_id
            logger.info(f"Fetching stdout for task: {args.task_id}")
            client_core.get_task_stdout(args.task_id)

        elif args.command == "stderr":
            # argparse handles required task_id
            logger.info(f"Fetching stderr for task: {args.task_id}")
            client_core.get_task_stderr(args.task_id)

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error occurred.")
        sys.exit(1)
    except httpx.RequestError as e:
        logger.error(f"Network error occurred.")
        sys.exit(1)
    except Exception as e:
        logger.exception(
            f"An unexpected error occurred during task command execution: {e}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
