"""
Example production host configuration.

Copy this file and modify for your deployment.

Usage:
    hakuriver-host --config configs/host/production.py

Or via KohakuEngine:
    from kohakuengine import Config, Script
    config = Config.from_file("configs/host/production.py")
    script = Script("hakuriver.host.app", config=config)
    script.run()
"""

from kohakuengine import Config

from hakuriver.models.enums import LogLevel

# =============================================================================
# Network Configuration - CHANGE THESE for your deployment
# =============================================================================
HOST_BIND_IP = "0.0.0.0"
HOST_PORT = 8000
HOST_SSH_PROXY_PORT = 8002
HOST_REACHABLE_ADDRESS = "10.0.0.1"  # <-- Your host's IP

# =============================================================================
# Path Configuration - CHANGE THESE for your deployment
# =============================================================================
SHARED_DIR = "/mnt/cluster-share"
DB_FILE = "/var/lib/hakuriver/hakuriver.db"

# =============================================================================
# Timing Configuration
# =============================================================================
HEARTBEAT_INTERVAL_SECONDS = 5
HEARTBEAT_TIMEOUT_FACTOR = 6
CLEANUP_CHECK_INTERVAL_SECONDS = 10

# =============================================================================
# Docker Configuration
# =============================================================================
DEFAULT_CONTAINER_NAME = "hakuriver-base"
INITIAL_BASE_IMAGE = "python:3.12-alpine"
TASKS_PRIVILEGED = False
ADDITIONAL_MOUNTS: list[str] = []

# =============================================================================
# Logging Configuration
# =============================================================================
LOG_LEVEL = LogLevel.INFO


def config_gen() -> Config:
    """KohakuEngine entry point."""
    return Config.from_globals()
