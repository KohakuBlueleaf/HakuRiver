import os
import sys
import getpass
import argparse
import subprocess

from hakuriver.utils.logger import logger
from hakuriver.utils.config_loader import settings


def create_service_files(args):
    """Creates systemd service files for hakuriver components."""
    # Determine key variables
    username = getpass.getuser()
    python_path = sys.executable
    venv_path = os.environ.get("VIRTUAL_ENV")
    env_path_base = os.environ.get("PATH")
    env_path_addition = f"{venv_path}/bin:" if venv_path else ""

    # Load configuration
    config_path = args.config
    if config_path:
        logger.info(f"Using specified config file: {config_path}")
    else:
        config_path = os.path.join(os.path.expanduser("~"), ".hakuriver", "config.toml")
        if os.path.exists(config_path):
            logger.info(f"Using default config file: {config_path}")
        else:
            logger.warning(
                f"Default config file not found at {config_path}, using built-in defaults"
            )

    # Get shared_dir from config
    shared_dir = settings["paths"]["shared_dir"]
    working_dir = shared_dir
    logger.info(f"Setting working directory to shared_dir: {working_dir}")

    created_file = []
    if args.host or args.all:
        logger.info("Creating host service file...")
        host_config = args.host_config or config_path

        host_service = f"""[Unit]
Description=HakuRiver Host Server
After=network.target

[Service]
Type=simple
User={username}
Group={username}
WorkingDirectory={working_dir}
ExecStart={python_path} -m hakuriver.cli.host --config {host_config}
Restart=on-failure
RestartSec=5
Environment="PATH={env_path_addition}:{env_path_base}"

[Install]
WantedBy=multi-user.target
"""
        output_path = os.path.join(args.output_dir, "hakuriver-host.service")
        with open(output_path, "w") as f:
            f.write(host_service)
        logger.info(f"Host service file created at {output_path}")
        created_file.append(output_path)

    if args.runner or args.all:
        logger.info("Creating runner service file...")
        runner_config = args.runner_config or config_path

        runner_service = f"""[Unit]
Description=HakuRiver Runner Agent
After=network.target

[Service]
Type=simple
User={username}
Group={username}
WorkingDirectory={working_dir}
ExecStart={python_path} -m hakuriver.cli.runner --config {runner_config}
Restart=on-failure
RestartSec=5
Environment="PATH={env_path_addition}:{env_path_base}"

[Install]
WantedBy=multi-user.target
"""
        output_path = os.path.join(args.output_dir, "hakuriver-runner.service")
        with open(output_path, "w") as f:
            f.write(runner_service)
        logger.info(f"Runner service file created at {output_path}")
        created_file.append(output_path)
        # Add note about sudo requirements for runner
        logger.warning(
            "\nIMPORTANT: The runner requires passwordless sudo access for systemd-run and systemctl."
        )
        logger.warning(
            "You may need to add the following to /etc/sudoers using visudo:"
        )
        logger.warning(
            f"{username} ALL=(ALL) NOPASSWD: /usr/bin/systemd-run, /usr/bin/systemctl"
        )

    return created_file


def _main():
    # Default config initialization
    default_config_path = os.path.join(os.path.expanduser("~"), ".hakuriver")
    if not os.path.exists(default_config_path):
        os.makedirs(default_config_path)

    base_dir = os.path.dirname(__file__).split("cli")[0]
    config_path = os.path.join(base_dir, "utils", "default_config.toml")
    default_config_file = os.path.join(default_config_path, "config.toml")

    # Create argument parser
    parser = argparse.ArgumentParser(
        description="Initialize HakuRiver configuration and services"
    )
    subparsers = parser.add_subparsers(dest="command")

    # Config subcommand - handles the existing functionality
    config_parser = subparsers.add_parser(
        "config", help="Initialize default configuration"
    )

    # Service subcommand - new functionality
    service_parser = subparsers.add_parser(
        "service", help="Create systemd service files"
    )
    service_parser.add_argument(
        "--host", action="store_true", help="Create host service file"
    )
    service_parser.add_argument(
        "--runner", action="store_true", help="Create runner service file"
    )
    service_parser.add_argument(
        "--all", action="store_true", help="Create both service files"
    )
    service_parser.add_argument(
        "--host-config", type=str, help="Path to host config file"
    )
    service_parser.add_argument(
        "--runner-config", type=str, help="Path to runner config file"
    )
    service_parser.add_argument("--config", type=str, help="Path to shared config file")
    service_parser.add_argument(
        "--output-dir",
        type=str,
        default=".",
        help="Directory to write service files to",
    )

    args = parser.parse_args()

    # Default to config command if none specified
    if not args.command:
        args.command = "config"

    if args.command == "config":
        # Existing config initialization code
        if not os.path.exists(default_config_file):
            with open(config_path, "r") as g:
                config = g.read()
            logger.info("Default config:")
            print(config)
            logger.info("Creating default config file...")
            with open(default_config_file, "w") as f:
                f.write(config)
        logger.info(f"Default config file created at {default_config_file}")

    elif args.command == "service":
        # At least one of the service options must be specified
        if not any([args.host, args.runner, args.all]):
            service_parser.error("You must specify --host, --runner, or --all")

        # Ensure output directory exists
        os.makedirs(args.output_dir, exist_ok=True)

        files = create_service_files(args)

        for file in files:
            mv_cmd = ["sudo", "cp", file, "/etc/systemd/system/"]
            result = subprocess.run(mv_cmd)
            if result.returncode == 0:
                logger.info("Service files moved to /etc/systemd/system/")
            else:
                logger.error(f"Failed to move service files.")
                return 1
        systemctl_cmd = ["sudo", "systemctl", "daemon-reload"]
        result = subprocess.run(systemctl_cmd)
        if result.returncode == 0:
            logger.info("Systemd daemon reloaded.")
        else:
            logger.error("Failed to reload systemd daemon.")
            return 1
        logger.info("Service files created successfully.")
        logger.info("To start the services, use:")
        logger.info("  sudo systemctl start hakuriver-host.service")
        logger.info("  sudo systemctl start hakuriver-runner.service")
        logger.info("To enable the services on boot, use:")
        logger.info("  sudo systemctl enable hakuriver-host.service")
        logger.info("  sudo systemctl enable hakuriver-runner.service")
        logger.info("To check the logs, use:")
        logger.info("  journalctl -u hakuriver-host.service")
        logger.info("  journalctl -u hakuriver-runner.service")


def main():
    _main()
    result1 = result2 = 0
    if os.path.exists("hakuriver-host.service"):
        clean_cmd1 = ["rm", "hakuriver-host.service"]
        result1 = subprocess.run(clean_cmd1).returncode
    if os.path.exists("hakuriver-runner.service"):
        clean_cmd2 = ["rm", "hakuriver-runner.service"]
        result2 = subprocess.run(clean_cmd2).returncode
    if not any([result1, result2]):
        logger.info("Temporary service files cleaned up.")
    else:
        logger.error("Failed to clean up temporary service files.")
        sys.exit(1)


if __name__ == "__main__":
    main()
