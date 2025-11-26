"""
Example production runner configuration.

Copy this file and modify for your deployment.

Usage:
    hakuriver-runner --config configs/runner/production.py

Or via KohakuEngine:
    from kohakuengine import Config, Script
    config = Config.from_file("configs/runner/production.py")
    script = Script("hakuriver.runner.app", config=config)
    script.run()
"""
from kohakuengine import Config

from hakuriver.models.enums import LogLevel

# =============================================================================
# Network Configuration - CHANGE THESE for your deployment
# =============================================================================
RUNNER_BIND_IP = "0.0.0.0"
RUNNER_PORT = 8001
HOST_ADDRESS = "10.0.0.1"  # <-- Your host's IP
HOST_PORT = 8000

# =============================================================================
# Path Configuration - CHANGE THESE for your deployment
# =============================================================================
SHARED_DIR = "/mnt/cluster-share"
LOCAL_TEMP_DIR = "/tmp/hakuriver"
NUMACTL_PATH = "/usr/bin/numactl"  # or "" for system PATH

# =============================================================================
# Timing Configuration
# =============================================================================
HEARTBEAT_INTERVAL_SECONDS = 5
RESOURCE_CHECK_INTERVAL_SECONDS = 1

# =============================================================================
# Execution Configuration
# =============================================================================
RUNNER_USER = ""  # Empty = current user
DEFAULT_WORKING_DIR = "/shared"

# =============================================================================
# Docker Configuration
# =============================================================================
TASKS_PRIVILEGED = False
ADDITIONAL_MOUNTS: list[str] = []

# =============================================================================
# Logging Configuration
# =============================================================================
LOG_LEVEL = LogLevel.INFO


def config_gen() -> Config:
    """KohakuEngine entry point."""
    return Config.from_globals()
