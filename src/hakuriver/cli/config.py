"""
Client CLI configuration defaults.

These can be overridden via command line arguments.
"""

# Network Configuration
HOST_ADDRESS: str = "localhost"
HOST_PORT: int = 8000
HOST_SSH_PROXY_PORT: int = 8002

# Default paths
SHARED_DIR: str = "/mnt/cluster-share"
