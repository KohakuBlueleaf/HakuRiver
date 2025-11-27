"""Custom exceptions for HakuRiver."""


class HakuRiverError(Exception):
    """Base exception for all HakuRiver errors."""

    pass


class TaskError(HakuRiverError):
    """Base exception for task-related errors."""

    pass


class TaskNotFoundError(TaskError):
    """Raised when a task is not found."""

    def __init__(self, task_id: int):
        self.task_id = task_id
        super().__init__(f"Task not found: {task_id}")


class TaskExecutionError(TaskError):
    """Raised when task execution fails."""

    pass


class TaskConfigurationError(TaskError):
    """Raised when task configuration is invalid."""

    pass


class NodeError(HakuRiverError):
    """Base exception for node-related errors."""

    pass


class NodeNotFoundError(NodeError):
    """Raised when a node is not found."""

    def __init__(self, hostname: str):
        self.hostname = hostname
        super().__init__(f"Node not found: {hostname}")


class NodeOfflineError(NodeError):
    """Raised when trying to use an offline node."""

    def __init__(self, hostname: str):
        self.hostname = hostname
        super().__init__(f"Node is offline: {hostname}")


class NodeResourceError(NodeError):
    """Raised when node doesn't have enough resources."""

    def __init__(self, hostname: str, resource: str, required: int, available: int):
        self.hostname = hostname
        self.resource = resource
        self.required = required
        self.available = available
        super().__init__(
            f"Node {hostname} doesn't have enough {resource}: "
            f"required={required}, available={available}"
        )


class ConfigurationError(HakuRiverError):
    """Raised when configuration is invalid."""

    pass


class StorageError(HakuRiverError):
    """Raised when storage operations fail."""

    pass
