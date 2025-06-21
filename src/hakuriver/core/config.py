import os
import sys
import getpass
import socket
from hakuriver.utils.config_loader import settings
from hakuriver.utils.logger import logger


try:
    # --- Configuration from settings ---
    class HostConfig:
        # Network
        HOST_BIND_IP = settings["network"]["host_bind_ip"]
        HOST_PORT = settings["network"]["host_port"]
        HOST_SSH_PROXY_PORT = settings["network"]["host_ssh_proxy_port"]
        REACABLE_ADDRESS = settings["network"]["host_reachable_address"]
        # Paths
        SHARED_DIR = settings["paths"]["shared_dir"]
        # Database
        DB_FILE = settings["database"]["db_file"]
        # Timing
        HEARTBEAT_INTERVAL_SECONDS = settings["timing"]["heartbeat_interval"]
        HEARTBEAT_TIMEOUT_FACTOR = settings["timing"]["heartbeat_timeout_factor"]
        CLEANUP_CHECK_INTERVAL_SECONDS = settings["timing"]["cleanup_check_interval"]
        # Docker
        CONTAINER_DIR = os.path.join(
            settings["paths"]["shared_dir"], settings["docker"]["container_dir"]
        )
        DEFAULT_CONTAINER_NAME = settings["docker"]["default_container_name"]
        INITIAL_BASE_IMAGE = settings["docker"]["initial_base_image"]
        TASKS_PRIVILEGED = settings["docker"]["tasks_privileged"]
        ADDITIONAL_MOUNTS = settings["docker"].get(
            "additional_mounts", []
        )  # Use .get for safety

except Exception as e:
    logger.warning("Failed to load config for host")
    logger.debug(f"Error: {e}", exc_info=True)

    class HostConfig:
        pass


try:

    class RunnerConfig:
        # This needs to happen before setting up logging if log filename includes hostname
        RUNNER_HOSTNAME = socket.gethostname()
        # Network
        HOST_ADDRESS = settings["network"]["host_reachable_address"]
        HOST_PORT = settings["network"]["host_port"]
        RUNNER_ADDRESS = settings["network"]["runner_address"]
        RUNNER_PORT = settings["network"]["runner_port"]
        HOST_URL = f"http://{HOST_ADDRESS}:{HOST_PORT}"
        # Paths
        SHARED_DIR = settings["paths"]["shared_dir"]
        LOCAL_TEMP_DIR = settings["paths"]["local_temp_dir"]
        NUMACTL_PATH = (
            settings["paths"]["numactl_path"] or "numactl"
        )  # Default to system PATH
        # Timing
        HEARTBEAT_INTERVAL_SECONDS = settings["timing"]["heartbeat_interval"]
        TASK_CHECK_INTERVAL_SECONDS = settings["timing"].get(
            "resource_check_interval", 1
        )
        RUNNER_USER = settings.get("environment", {}).get(
            "runner_user", getpass.getuser()
        )
        CONTAINER_TAR_DIR = os.path.join(
            settings["paths"]["shared_dir"], settings["docker"]["container_dir"]
        )

except Exception as e:
    logger.warning("Failed to load config for runner")
    logger.debug(f"Error: {e}", exc_info=True)

    class RunnerConfig:
        pass


try:

    class ClientConfig:
        """Holds client-specific configuration, potentially modifiable."""

        def __init__(self):
            """Initializes configuration from loaded settings."""
            self._load_settings()

        def _load_settings(self):
            """Loads relevant settings from the global 'settings' object."""
            try:
                self.host_address: str = settings["network"]["host_reachable_address"]
                self.host_port: int = settings["network"]["host_port"]
                self.host_ssh_proxy_port: int = settings["network"]["host_ssh_proxy_port"]
                # Default timeouts (can be overridden in requests if needed)
                self.default_timeout: float = 30.0
                self.status_timeout: float = 10.0
                self.kill_timeout: float = 15.0
                self.nodes_timeout: float = 10.0
                self.health_timeout: float = 15.0
            except KeyError as e:
                logger.error(
                    f"Error: Missing configuration key in config.toml: {e}",
                )
                logger.error("Exiting.", )
                sys.exit(1)
            except Exception as e:
                logger.error(f"Error processing configuration: {e}", )
                logger.error("Exiting.", )
                sys.exit(1)

        @property
        def host_url(self) -> str:
            """Constructs the full base URL for the host API."""
            return f"http://{self.host_address}:{self.host_port}"

        def update_setting(self, key: str, value: any):
            """Allows updating a configuration value 'on the fly' (use with caution)."""
            if hasattr(self, key):
                logger.info(
                    f"Updating config '{key}' from '{getattr(self, key)}' to '{value}'"
                )
                setattr(self, key, value)
            else:
                logger.warning(
                    f"Warning: Config key '{key}' not found.",
                )

except Exception as e:
    logger.warning("Failed to load config for client")
    logger.debug(f"Error: {e}", exc_info=True)

    class ClientConfig:
        pass


RUNNER_CONFIG = RunnerConfig()
HOST_CONFIG = HostConfig()
CLIENT_CONFIG = ClientConfig()
