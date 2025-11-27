"""Enumeration types for HakuRiver."""

from enum import Enum


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"
    ASSIGNING = "assigning"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"
    KILLED_OOM = "killed_oom"
    LOST = "lost"
    STOPPED = "stopped"


class NodeStatus(str, Enum):
    """Node health status."""

    ONLINE = "online"
    OFFLINE = "offline"


class TaskType(str, Enum):
    """Task type."""

    COMMAND = "command"
    VPS = "vps"


class LogLevel(str, Enum):
    """Logging verbosity levels (higher = less logging)."""

    FULL = "full"  # Everything including trace
    DEBUG = "debug"  # Debug and above
    INFO = "info"  # Info and above
    WARNING = "warning"  # Warning and above only


class SSHKeyMode(str, Enum):
    """SSH key mode for VPS creation."""

    NONE = "none"  # No SSH key, passwordless root login
    UPLOAD = "upload"  # User provides their public key
    GENERATE = "generate"  # Generate keypair, return private key to user
