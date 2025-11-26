"""KohakuVault-based persistent storage for HakuRiver."""
from kohakuvault import KVault

from hakuriver.exceptions import StorageError


class RunnerStateStore:
    """
    Persistent state storage for runner using KohakuVault.

    Provides a dict-like interface for storing and retrieving task state.
    Used for recovery after runner restart.
    """

    def __init__(self, db_path: str, table: str = "runner_state"):
        """
        Initialize the state store.

        Args:
            db_path: Path to the SQLite database file
            table: Table name for this store
        """
        try:
            self.vault = KVault(db_path, table=table)
        except Exception as e:
            raise StorageError(f"Failed to initialize storage at {db_path}: {e}") from e
        self._table = table

    def __getitem__(self, key: str) -> dict:
        """Get a value by key."""
        return self.vault[key]

    def __setitem__(self, key: str, value: dict) -> None:
        """Set a value by key."""
        self.vault[key] = value

    def __delitem__(self, key: str) -> None:
        """Delete a value by key."""
        del self.vault[key]

    def __contains__(self, key: str) -> bool:
        """Check if key exists."""
        try:
            _ = self.vault[key]
            return True
        except KeyError:
            return False

    def __iter__(self):
        """Iterate over keys."""
        return iter(self.vault)

    def __len__(self) -> int:
        """Return number of items."""
        return len(list(self.vault))

    def get(self, key: str, default: dict | None = None) -> dict | None:
        """Get a value with optional default."""
        try:
            return self.vault[key]
        except KeyError:
            return default

    def keys(self) -> list[str]:
        """Return all keys."""
        return list(self.vault)

    def items(self) -> list[tuple[str, dict]]:
        """Return all key-value pairs."""
        return [(k, self.vault[k]) for k in self.vault]

    def values(self) -> list[dict]:
        """Return all values."""
        return [self.vault[k] for k in self.vault]

    def clear(self) -> None:
        """Remove all items."""
        for key in list(self.vault):
            del self.vault[key]

    def pop(self, key: str, default: dict | None = None) -> dict | None:
        """Remove and return a value."""
        try:
            value = self.vault[key]
            del self.vault[key]
            return value
        except KeyError:
            return default


class TaskStateStore(RunnerStateStore):
    """Store for tracking running task containers."""

    def __init__(self, db_path: str):
        super().__init__(db_path, table="running_tasks")

    def add_task(
        self,
        task_id: int,
        container_name: str,
        allocated_cores: list[int] | None = None,
        allocated_gpus: list[int] | None = None,
        numa_node: int | None = None,
    ) -> None:
        """
        Add a running task to the store.

        Args:
            task_id: Task ID
            container_name: Docker container name
            allocated_cores: List of allocated CPU core IDs
            allocated_gpus: List of allocated GPU IDs
            numa_node: NUMA node ID if bound
        """
        self[str(task_id)] = {
            "task_id": task_id,
            "container_name": container_name,
            "allocated_cores": allocated_cores or [],
            "allocated_gpus": allocated_gpus or [],
            "numa_node": numa_node,
        }

    def remove_task(self, task_id: int) -> dict | None:
        """Remove a task and return its data."""
        return self.pop(str(task_id))

    def get_task(self, task_id: int) -> dict | None:
        """Get task data by ID."""
        return self.get(str(task_id))

    def list_tasks(self) -> list[dict]:
        """List all running tasks."""
        return self.values()

    def get_all_task_ids(self) -> list[int]:
        """Get all running task IDs."""
        return [int(k) for k in self.keys()]


class VPSStateStore(RunnerStateStore):
    """Store for tracking VPS sessions."""

    def __init__(self, db_path: str):
        super().__init__(db_path, table="vps_sessions")

    def add_vps(
        self,
        task_id: int,
        container_name: str,
        ssh_port: int,
        has_key: bool = False,
        allocated_cores: list[int] | None = None,
        allocated_gpus: list[int] | None = None,
        numa_node: int | None = None,
    ) -> None:
        """
        Add a VPS session to the store.

        Args:
            task_id: Task ID
            container_name: Docker container name
            ssh_port: SSH port on host
            has_key: Whether SSH key was provided
            allocated_cores: List of allocated CPU core IDs
            allocated_gpus: List of allocated GPU IDs
            numa_node: NUMA node ID if bound
        """
        self[str(task_id)] = {
            "task_id": task_id,
            "container_name": container_name,
            "ssh_port": ssh_port,
            "has_key": has_key,
            "allocated_cores": allocated_cores or [],
            "allocated_gpus": allocated_gpus or [],
            "numa_node": numa_node,
        }

    def remove_vps(self, task_id: int) -> dict | None:
        """Remove a VPS session and return its data."""
        return self.pop(str(task_id))

    def get_vps(self, task_id: int) -> dict | None:
        """Get VPS session data by ID."""
        return self.get(str(task_id))

    def list_vps(self) -> list[dict]:
        """List all VPS sessions."""
        return self.values()


class PausedTaskStore(RunnerStateStore):
    """Store for tracking paused tasks."""

    def __init__(self, db_path: str):
        super().__init__(db_path, table="paused_tasks")

    def add_paused(self, task_id: int, container_name: str) -> None:
        """Add a paused task."""
        self[str(task_id)] = {
            "task_id": task_id,
            "container_name": container_name,
        }

    def remove_paused(self, task_id: int) -> dict | None:
        """Remove a paused task and return its data."""
        return self.pop(str(task_id))

    def is_paused(self, task_id: int) -> bool:
        """Check if a task is paused."""
        return str(task_id) in self
