"""
Runner configuration.

A global Config instance that can be modified at runtime.
"""

import getpass
import os
import socket
from dataclasses import dataclass, field

from hakuriver.models.enums import LogLevel


@dataclass
class RunnerConfig:
    """Runner agent configuration."""

    # Network Configuration
    RUNNER_BIND_IP: str = "0.0.0.0"
    RUNNER_PORT: int = 8001
    HOST_ADDRESS: str = "127.0.0.1"
    HOST_PORT: int = 8000

    # Path Configuration
    SHARED_DIR: str = "/mnt/cluster-share"
    LOCAL_TEMP_DIR: str = "/tmp/hakuriver"
    CONTAINER_TAR_DIR: str = ""
    NUMACTL_PATH: str = ""
    RUNNER_LOG_FILE: str = ""

    # Timing Configuration
    HEARTBEAT_INTERVAL_SECONDS: int = 5
    RESOURCE_CHECK_INTERVAL_SECONDS: int = 1

    # Execution Configuration
    RUNNER_USER: str = ""
    DEFAULT_WORKING_DIR: str = "/shared"

    # Docker Configuration
    TASKS_PRIVILEGED: bool = False
    ADDITIONAL_MOUNTS: list[str] = field(default_factory=list)
    DOCKER_IMAGE_SYNC_TIMEOUT: int = 600  # 10 minutes for large image syncs (10-30GB)

    # Logging Configuration
    LOG_LEVEL: LogLevel = LogLevel.INFO

    def get_hostname(self) -> str:
        """Get this runner's hostname."""
        return socket.gethostname()

    def get_host_url(self) -> str:
        """Get the full host URL."""
        return f"http://{self.HOST_ADDRESS}:{self.HOST_PORT}"

    def get_container_tar_dir(self) -> str:
        """Get the container tarball directory path."""
        if self.CONTAINER_TAR_DIR:
            return self.CONTAINER_TAR_DIR
        return os.path.join(self.SHARED_DIR, "hakuriver-containers")

    def get_runner_user(self) -> str:
        """Get the user to run tasks as."""
        if self.RUNNER_USER:
            return self.RUNNER_USER
        return getpass.getuser()

    def get_numactl_path(self) -> str:
        """Get the numactl executable path."""
        if self.NUMACTL_PATH:
            return self.NUMACTL_PATH
        return "numactl"

    def get_state_db_path(self) -> str:
        """Get the path for runner state database (KohakuVault)."""
        return os.path.join(self.LOCAL_TEMP_DIR, "runner-state.db")


# Global config instance
config = RunnerConfig()
