"""
Custom exceptions for HakuRiver.

This module defines a hierarchical exception system for the HakuRiver cluster
manager, enabling precise error handling and meaningful error messages.

Exception Hierarchy:
    HakuRiverError (base)
    ├── TaskError
    │   ├── TaskNotFoundError
    │   ├── TaskExecutionError
    │   └── TaskConfigurationError
    ├── NodeError
    │   ├── NodeNotFoundError
    │   ├── NodeOfflineError
    │   └── NodeResourceError
    ├── ConfigurationError
    └── StorageError
"""

# =============================================================================
# Base Exception
# =============================================================================


class HakuRiverError(Exception):
    """
    Base exception for all HakuRiver errors.

    All custom exceptions in HakuRiver inherit from this class,
    enabling catch-all handling of HakuRiver-specific errors.
    """


# =============================================================================
# Task Exceptions
# =============================================================================


class TaskError(HakuRiverError):
    """Base exception for task-related errors."""


class TaskNotFoundError(TaskError):
    """
    Raised when a requested task does not exist.

    Attributes:
        task_id: The ID of the task that was not found.
    """

    def __init__(self, task_id: int):
        self.task_id = task_id
        super().__init__(f"Task not found: {task_id}")


class TaskExecutionError(TaskError):
    """
    Raised when task execution fails.

    This includes errors during container creation, command execution,
    or resource allocation for the task.
    """


class TaskConfigurationError(TaskError):
    """
    Raised when task configuration is invalid.

    Examples include invalid resource requirements, malformed commands,
    or incompatible option combinations.
    """


# =============================================================================
# Node Exceptions
# =============================================================================


class NodeError(HakuRiverError):
    """Base exception for node-related errors."""


class NodeNotFoundError(NodeError):
    """
    Raised when a requested node does not exist.

    Attributes:
        hostname: The hostname of the node that was not found.
    """

    def __init__(self, hostname: str):
        self.hostname = hostname
        super().__init__(f"Node not found: {hostname}")


class NodeOfflineError(NodeError):
    """
    Raised when attempting to use an offline node.

    Attributes:
        hostname: The hostname of the offline node.
    """

    def __init__(self, hostname: str):
        self.hostname = hostname
        super().__init__(f"Node is offline: {hostname}")


class NodeResourceError(NodeError):
    """
    Raised when a node lacks sufficient resources.

    Attributes:
        hostname: The hostname of the node.
        resource: Type of resource (e.g., 'cores', 'memory', 'gpus').
        required: Amount of resource required.
        available: Amount of resource available.
    """

    def __init__(self, hostname: str, resource: str, required: int, available: int):
        self.hostname = hostname
        self.resource = resource
        self.required = required
        self.available = available
        super().__init__(
            f"Node {hostname} has insufficient {resource}: "
            f"required={required}, available={available}"
        )


# =============================================================================
# Configuration and Storage Exceptions
# =============================================================================


class ConfigurationError(HakuRiverError):
    """
    Raised when configuration is invalid or missing.

    This includes missing config files, invalid config values,
    or incompatible configuration combinations.
    """


class StorageError(HakuRiverError):
    """
    Raised when storage operations fail.

    This includes database connection failures, read/write errors,
    or data corruption issues.
    """
