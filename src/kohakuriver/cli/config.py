"""
CLI configuration defaults.

These can be overridden via command line arguments or environment variables.
"""

import os

# Network Configuration
HOST_ADDRESS: str = os.environ.get("HAKURIVER_HOST", "localhost")
HOST_PORT: int = int(os.environ.get("HAKURIVER_PORT", "8000"))
HOST_SSH_PROXY_PORT: int = int(os.environ.get("HAKURIVER_SSH_PROXY_PORT", "8002"))

# Default paths
SHARED_DIR: str = os.environ.get("HAKURIVER_SHARED_DIR", "/mnt/cluster-share")

# Output format
OUTPUT_FORMAT: str = "table"  # table, json, yaml
