"""
HakuRiver Init CLI: Initialize configuration and services.

Usage:
    hakuriver.init config              # Show instructions
    hakuriver.init config --generate   # Generate example config files
    hakuriver.init service --all       # Generate systemd service files
"""

import argparse
import getpass
import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)

# Template for host configuration - uses module globals + from_globals()
HOST_CONFIG_TEMPLATE = '''"""
HakuRiver Host Configuration

This file is loaded by KohakuEngine when running:
    hakuriver.host --config /path/to/this/file.py

Modify the module-level variables below to customize your host setup.
"""
from kohakuengine import Config

from hakuriver.models.enums import LogLevel

# =============================================================================
# Network Configuration
# =============================================================================

# IP address the Host server binds to
HOST_BIND_IP: str = "0.0.0.0"

# Port the Host API server listens on
HOST_PORT: int = 8000

# Port for SSH proxy (VPS access)
HOST_SSH_PROXY_PORT: int = 8002

# Address that runners/clients use to reach the host
# IMPORTANT: Change this in production to the actual reachable IP/hostname!
HOST_REACHABLE_ADDRESS: str = "127.0.0.1"

# =============================================================================
# Path Configuration
# =============================================================================

# Shared storage accessible by all nodes at the same path (NFS mount)
SHARED_DIR: str = "/mnt/cluster-share"

# SQLite database file path
DB_FILE: str = "/var/lib/hakuriver/hakuriver.db"

# Container tarball directory (empty = SHARED_DIR/hakuriver-containers)
CONTAINER_DIR: str = ""

# Log file path (empty = console only)
HOST_LOG_FILE: str = ""

# =============================================================================
# Timing Configuration
# =============================================================================

# How often runners send heartbeats (seconds)
HEARTBEAT_INTERVAL_SECONDS: int = 5

# Runner is marked offline if no heartbeat for interval * this factor
HEARTBEAT_TIMEOUT_FACTOR: int = 6

# How often to check for dead runners (seconds)
CLEANUP_CHECK_INTERVAL_SECONDS: int = 10

# =============================================================================
# Docker Configuration
# =============================================================================

# Default container name for HakuRiver tasks
DEFAULT_CONTAINER_NAME: str = "hakuriver-base"

# Initial Docker image if default container tarball doesn't exist
INITIAL_BASE_IMAGE: str = "python:3.12-alpine"

# Whether tasks run with --privileged flag (use with caution!)
TASKS_PRIVILEGED: bool = False

# Additional host directories to mount into containers
# Format: ["host_path:container_path", ...]
ADDITIONAL_MOUNTS: list[str] = []

# =============================================================================
# Logging Configuration
# =============================================================================

# Logging verbosity level: full, debug, info, warning
LOG_LEVEL: LogLevel = LogLevel.INFO


# =============================================================================
# KohakuEngine config_gen - DO NOT MODIFY
# =============================================================================

def config_gen():
    """Generate configuration from module globals."""
    return Config.from_globals()
'''

# Template for runner configuration - uses module globals + from_globals()
RUNNER_CONFIG_TEMPLATE = '''"""
HakuRiver Runner Configuration

This file is loaded by KohakuEngine when running:
    hakuriver.runner --config /path/to/this/file.py

Modify the module-level variables below to customize your runner setup.
"""
from kohakuengine import Config

from hakuriver.models.enums import LogLevel

# =============================================================================
# Network Configuration
# =============================================================================

# IP address the Runner server binds to
RUNNER_BIND_IP: str = "0.0.0.0"

# Port the Runner API server listens on
RUNNER_PORT: int = 8001

# Host server address (how runner reaches the host)
HOST_ADDRESS: str = "127.0.0.1"

# Host server port
HOST_PORT: int = 8000

# =============================================================================
# Path Configuration
# =============================================================================

# Shared storage accessible by all nodes (NFS mount)
SHARED_DIR: str = "/mnt/cluster-share"

# Local fast temporary storage on this node
LOCAL_TEMP_DIR: str = "/tmp/hakuriver"

# Container tarball directory (empty = SHARED_DIR/hakuriver-containers)
CONTAINER_TAR_DIR: str = ""

# Path to numactl executable (empty = use system PATH)
NUMACTL_PATH: str = ""

# Log file path (empty = console only)
RUNNER_LOG_FILE: str = ""

# =============================================================================
# Timing Configuration
# =============================================================================

# How often to send heartbeat to host (seconds)
HEARTBEAT_INTERVAL_SECONDS: int = 5

# How often to check resource/task status (seconds)
RESOURCE_CHECK_INTERVAL_SECONDS: int = 1

# =============================================================================
# Execution Configuration
# =============================================================================

# User to run tasks as (empty = current user)
RUNNER_USER: str = ""

# Default working directory inside containers
DEFAULT_WORKING_DIR: str = "/shared"

# =============================================================================
# Docker Configuration
# =============================================================================

# Whether tasks run with --privileged flag (use with caution!)
TASKS_PRIVILEGED: bool = False

# Additional host directories to mount into containers
# Format: ["host_path:container_path", ...]
ADDITIONAL_MOUNTS: list[str] = []

# =============================================================================
# Logging Configuration
# =============================================================================

# Logging verbosity level: full, debug, info, warning
LOG_LEVEL: LogLevel = LogLevel.INFO


# =============================================================================
# KohakuEngine config_gen - DO NOT MODIFY
# =============================================================================

def config_gen():
    """Generate configuration from module globals."""
    return Config.from_globals()
'''


def get_default_config_dir() -> str:
    """Get the default config directory path."""
    return os.path.join(os.path.expanduser("~"), ".hakuriver")


def generate_config(config_type: str, output_dir: str) -> str:
    """Generate a configuration file and return its path."""
    os.makedirs(output_dir, exist_ok=True)

    if config_type == "host":
        filename = "host_config.py"
        content = HOST_CONFIG_TEMPLATE
    elif config_type == "runner":
        filename = "runner_config.py"
        content = RUNNER_CONFIG_TEMPLATE
    else:
        raise ValueError(f"Unknown config type: {config_type}")

    filepath = os.path.join(output_dir, filename)

    if os.path.exists(filepath):
        print(f"WARNING: {filepath} already exists, skipping.")
        return filepath

    with open(filepath, "w") as f:
        f.write(content)

    return filepath


def create_service_files(args) -> list[str]:
    """Creates systemd service files for hakuriver components."""
    username = getpass.getuser()
    python_path = sys.executable
    venv_path = os.environ.get("VIRTUAL_ENV")
    env_path_base = os.environ.get("PATH", "")
    env_path_addition = f"{venv_path}/bin:" if venv_path else ""

    # Determine working directory
    working_dir = args.working_dir or "/mnt/cluster-share"

    created_files = []

    if args.host or args.all:
        print("Creating host service file...")
        host_config = args.host_config or ""
        config_arg = f" --config {host_config}" if host_config else ""

        host_service = f"""[Unit]
Description=HakuRiver Host Server
After=network.target

[Service]
Type=simple
User={username}
Group={username}
WorkingDirectory={working_dir}
ExecStart={python_path} -m hakuriver.cli.host{config_arg}
Restart=on-failure
RestartSec=5
Environment="PATH={env_path_addition}{env_path_base}"

[Install]
WantedBy=multi-user.target
"""
        output_path = os.path.join(args.output_dir, "hakuriver-host.service")
        with open(output_path, "w") as f:
            f.write(host_service)
        print(f"  Created: {output_path}")
        created_files.append(output_path)

    if args.runner or args.all:
        print("Creating runner service file...")
        runner_config = args.runner_config or ""
        config_arg = f" --config {runner_config}" if runner_config else ""

        runner_service = f"""[Unit]
Description=HakuRiver Runner Agent
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User={username}
Group={username}
WorkingDirectory={working_dir}
ExecStart={python_path} -m hakuriver.cli.runner{config_arg}
Restart=on-failure
RestartSec=5
Environment="PATH={env_path_addition}{env_path_base}"

[Install]
WantedBy=multi-user.target
"""
        output_path = os.path.join(args.output_dir, "hakuriver-runner.service")
        with open(output_path, "w") as f:
            f.write(runner_service)
        print(f"  Created: {output_path}")
        created_files.append(output_path)

    return created_files


def install_service_files(files: list[str]) -> bool:
    """Install service files to systemd directory."""
    success = True

    for filepath in files:
        cmd = ["sudo", "cp", filepath, "/etc/systemd/system/"]
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"ERROR: Failed to copy {filepath} to /etc/systemd/system/")
            success = False

    if success:
        # Reload systemd
        result = subprocess.run(["sudo", "systemctl", "daemon-reload"])
        if result.returncode != 0:
            print("ERROR: Failed to reload systemd daemon")
            success = False

    return success


def main():
    """Initialize HakuRiver configuration and services."""
    parser = argparse.ArgumentParser(
        description="Initialize HakuRiver configuration and services",
        allow_abbrev=False,
    )

    subparsers = parser.add_subparsers(dest="command")

    # Config subcommand
    config_parser = subparsers.add_parser(
        "config", help="Initialize configuration files"
    )
    config_parser.add_argument(
        "--generate",
        "-g",
        action="store_true",
        help="Generate example configuration files",
    )
    config_parser.add_argument(
        "--host",
        action="store_true",
        help="Generate host configuration only",
    )
    config_parser.add_argument(
        "--runner",
        action="store_true",
        help="Generate runner configuration only",
    )
    config_parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        default=None,
        help=f"Output directory for config files (default: {get_default_config_dir()})",
    )

    # Service subcommand
    service_parser = subparsers.add_parser(
        "service", help="Create systemd service files"
    )
    service_parser.add_argument(
        "--host",
        action="store_true",
        help="Create host service file",
    )
    service_parser.add_argument(
        "--runner",
        action="store_true",
        help="Create runner service file",
    )
    service_parser.add_argument(
        "--all",
        action="store_true",
        help="Create both service files",
    )
    service_parser.add_argument(
        "--host-config",
        type=str,
        help="Path to host config file for service",
    )
    service_parser.add_argument(
        "--runner-config",
        type=str,
        help="Path to runner config file for service",
    )
    service_parser.add_argument(
        "--working-dir",
        type=str,
        default=None,
        help="Working directory for services (default: /mnt/cluster-share)",
    )
    service_parser.add_argument(
        "--output-dir",
        type=str,
        default=".",
        help="Directory to write service files to (default: current dir)",
    )
    service_parser.add_argument(
        "--install",
        action="store_true",
        help="Install service files to /etc/systemd/system/ (requires sudo)",
    )

    args = parser.parse_args()

    # Show help if no command
    if not args.command:
        parser.print_help()
        print()
        print("Examples:")
        print("  hakuriver.init config --generate       # Generate config files")
        print(
            "  hakuriver.init service --all --install # Create and install systemd services"
        )
        return

    if args.command == "config":
        output_dir = args.output_dir or get_default_config_dir()

        if args.generate or args.host or args.runner:
            # Generate config files
            os.makedirs(output_dir, exist_ok=True)
            generated = []

            if args.host or (args.generate and not args.runner):
                path = generate_config("host", output_dir)
                generated.append(("host", path))

            if args.runner or (args.generate and not args.host):
                path = generate_config("runner", output_dir)
                generated.append(("runner", path))

            if generated:
                print()
                print("Generated configuration files:")
                for config_type, path in generated:
                    print(f"  {path}")

                print()
                print("Usage:")
                for config_type, path in generated:
                    if config_type == "host":
                        print(f"  hakuriver.host --config {path}")
                    elif config_type == "runner":
                        print(f"  hakuriver.runner --config {path}")
        else:
            # Show instructions
            print("HakuRiver Configuration")
            print("=" * 60)
            print()
            print("HakuRiver uses KohakuEngine for Python-based configuration.")
            print("Config files define module-level variables and a config_gen()")
            print("function that returns Config.from_globals().")
            print()
            print("Generate config files:")
            print("  hakuriver.init config --generate    # Both host and runner")
            print("  hakuriver.init config --host        # Host only")
            print("  hakuriver.init config --runner      # Runner only")
            print("  hakuriver.init config -g -o ./      # Custom output dir")
            print()
            print("Run with config:")
            print(f"  hakuriver.host --config {output_dir}/host_config.py")
            print(f"  hakuriver.runner --config {output_dir}/runner_config.py")
            print()
            print(f"Default config directory: {output_dir}")

    elif args.command == "service":
        if not any([args.host, args.runner, args.all]):
            print("ERROR: You must specify --host, --runner, or --all")
            sys.exit(1)

        os.makedirs(args.output_dir, exist_ok=True)
        files = create_service_files(args)

        if not files:
            print("No service files created.")
            sys.exit(1)

        if args.install:
            print()
            print("Installing service files...")
            if install_service_files(files):
                print()
                print("Service files installed successfully.")
                print()
                print("To start the services:")
                if args.host or args.all:
                    print("  sudo systemctl start hakuriver-host")
                if args.runner or args.all:
                    print("  sudo systemctl start hakuriver-runner")
                print()
                print("To enable on boot:")
                if args.host or args.all:
                    print("  sudo systemctl enable hakuriver-host")
                if args.runner or args.all:
                    print("  sudo systemctl enable hakuriver-runner")
                print()
                print("To view logs:")
                if args.host or args.all:
                    print("  journalctl -u hakuriver-host -f")
                if args.runner or args.all:
                    print("  journalctl -u hakuriver-runner -f")
            else:
                print("ERROR: Failed to install some service files.")
                sys.exit(1)

            # Cleanup temporary files
            for filepath in files:
                if os.path.exists(filepath) and args.output_dir == ".":
                    os.remove(filepath)
        else:
            print()
            print("Service files created. To install, run with --install flag")
            print("or manually copy to /etc/systemd/system/ and run:")
            print("  sudo systemctl daemon-reload")


if __name__ == "__main__":
    main()
