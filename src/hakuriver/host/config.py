"""
Host configuration.

A global Config instance that can be modified at runtime.
"""

import os
from dataclasses import dataclass, field

from hakuriver.models.enums import LogLevel


@dataclass
class HostConfig:
    """Host server configuration."""

    # Network Configuration
    HOST_BIND_IP: str = "0.0.0.0"
    HOST_PORT: int = 8000
    HOST_SSH_PROXY_PORT: int = 8002
    HOST_REACHABLE_ADDRESS: str = "127.0.0.1"

    # Path Configuration
    SHARED_DIR: str = "/mnt/cluster-share"
    DB_FILE: str = "/var/lib/hakuriver/hakuriver.db"
    CONTAINER_DIR: str = ""
    HOST_LOG_FILE: str = ""

    # Timing Configuration
    HEARTBEAT_INTERVAL_SECONDS: int = 5
    HEARTBEAT_TIMEOUT_FACTOR: int = 6
    CLEANUP_CHECK_INTERVAL_SECONDS: int = 10

    # Docker Configuration
    DEFAULT_CONTAINER_NAME: str = "hakuriver-base"
    INITIAL_BASE_IMAGE: str = "python:3.12-alpine"
    TASKS_PRIVILEGED: bool = False
    ADDITIONAL_MOUNTS: list[str] = field(default_factory=list)
    DEFAULT_WORKING_DIR: str = "/shared"

    # Logging Configuration
    LOG_LEVEL: LogLevel = LogLevel.INFO

    def get_container_dir(self) -> str:
        """Get the container tarball directory path."""
        if self.CONTAINER_DIR:
            return self.CONTAINER_DIR
        return os.path.join(self.SHARED_DIR, "hakuriver-containers")

    def get_host_url(self) -> str:
        """Get the full host URL."""
        return f"http://{self.HOST_REACHABLE_ADDRESS}:{self.HOST_PORT}"


# Global config instance
config = HostConfig()
