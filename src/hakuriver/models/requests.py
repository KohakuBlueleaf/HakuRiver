"""Pydantic models for API requests and responses."""
import datetime

from pydantic import BaseModel, Field

from hakuriver.models.enums import NodeStatus, TaskStatus, TaskType


# =============================================================================
# Task Request Models
# =============================================================================


class TaskSubmitRequest(BaseModel):
    """Request body for task submission (CLI to host)."""

    command: str = Field(..., description="Command to execute")
    arguments: list[str] = Field(default_factory=list, description="Command arguments")
    env_vars: dict[str, str] = Field(default_factory=dict, description="Environment variables")
    required_cores: int = Field(default=1, ge=1, description="Number of CPU cores required")
    required_gpus: int = Field(default=0, ge=0, description="Number of GPUs required")
    required_memory_bytes: int | None = Field(default=None, description="Memory requirement in bytes")
    target_node: str | None = Field(default=None, description="Target node hostname (None=auto)")
    target_numa_node_id: int | None = Field(default=None, description="Target NUMA node ID")
    container_name: str | None = Field(default=None, description="Container environment name")
    docker_privileged: bool = Field(default=False, description="Run with --privileged")
    docker_mount_dirs: list[str] = Field(default_factory=list, description="Additional mount dirs")


class TaskSubmission(BaseModel):
    """Task submission request (host API).

    Matches old TaskRequest model for compatibility.
    Supports both 'command' and 'vps' task types.
    For VPS: command field stores the SSH public key.
    """
    task_type: str = Field(default="command", description="Task type: 'command' or 'vps'")
    command: str = Field(default="", description="Command to execute (or SSH public key for VPS)")
    arguments: list[str] = Field(default_factory=list, description="Command arguments")
    env_vars: dict[str, str] = Field(default_factory=dict, description="Environment variables")
    required_cores: int = Field(default=1, ge=0, description="Number of CPU cores required")
    required_gpus: list[list[int]] | None = Field(
        default=None,
        description="List of GPU IDs for each target (one list per target)"
    )
    required_memory_bytes: int | None = Field(default=None, ge=0, description="Memory limit in bytes")
    targets: list[str] | None = Field(
        default=None,
        description='List of targets, e.g., ["host1", "host2:0", "host1:1"]'
    )
    container_name: str | None = Field(
        default=None,
        description="Override default container name"
    )
    privileged: bool | None = Field(
        default=None,
        description="Override default privileged setting"
    )
    additional_mounts: list[str] | None = Field(
        default=None,
        description="Override default additional mounts"
    )


class TaskExecuteRequest(BaseModel):
    """Task execution request (host to runner)."""

    task_id: int
    command: str
    arguments: list[str] | None = None
    env_vars: dict[str, str] | None = None
    required_cores: int = 1
    required_gpus: list[int] | None = None  # GPU indices as integers
    required_memory_bytes: int | None = None
    target_numa_node_id: int | None = None
    container_name: str
    working_dir: str = "/shared"
    stdout_path: str
    stderr_path: str


class VPSSubmission(BaseModel):
    """VPS submission request (host API) - kept for backward compatibility."""

    required_cores: int = 1
    required_gpus: list[int] | None = None  # GPU indices as integers
    required_memory_bytes: int | None = None
    target_hostname: str | None = None
    target_numa_node_id: int | None = None
    container_name: str | None = None
    ssh_public_key: str


class VPSCreateRequest(BaseModel):
    """VPS creation request (host to runner)."""

    task_id: int
    required_cores: int = 1
    required_gpus: list[int] | None = None  # GPU indices as integers
    required_memory_bytes: int | None = None
    target_numa_node_id: int | None = None
    container_name: str
    ssh_public_key: str
    ssh_port: int


class TaskKillRequest(BaseModel):
    """Request body for task kill."""

    signal: str = Field(default="SIGTERM", description="Signal to send (SIGTERM, SIGKILL, etc.)")


class TaskControlRequest(BaseModel):
    """Request body for task control operations (kill/pause/resume) from host to runner."""

    task_id: int
    container_name: str


# =============================================================================
# Task Response Models
# =============================================================================


class TaskResponse(BaseModel):
    """Response for a single task."""

    task_id: int
    task_type: str
    batch_id: int | None
    command: str
    arguments: list[str]
    env_vars: dict[str, str]
    required_cores: int
    required_gpus: list[int]
    required_memory_bytes: int | None
    target_numa_node_id: int | None
    status: str
    assigned_node: str | None
    container_name: str | None
    docker_image_name: str | None
    docker_privileged: bool
    docker_mount_dirs: list[str]
    ssh_port: int | None
    stdout_path: str
    stderr_path: str
    exit_code: int | None
    error_message: str | None
    submitted_at: str | None
    started_at: str | None
    completed_at: str | None


class TaskListResponse(BaseModel):
    """Response for task list with pagination."""

    items: list[TaskResponse]
    total: int
    page: int
    page_size: int
    pages: int


class TaskSubmitResponse(BaseModel):
    """Response after task submission."""

    task_id: int
    status: str
    message: str


class BatchSubmitResponse(BaseModel):
    """Response after batch task submission."""

    batch_id: int
    task_ids: list[int]
    message: str


# =============================================================================
# Node Request Models
# =============================================================================


class NodeRegisterRequest(BaseModel):
    """Request body for node registration."""

    hostname: str
    url: str
    total_cores: int
    memory_total_bytes: int | None = None
    numa_topology: dict[int, list[int]] | None = None
    gpu_info: list[dict] | None = None


class HeartbeatKilledTaskInfo(BaseModel):
    """Information about a task killed by the runner (e.g., OOM)."""

    task_id: int
    reason: str  # e.g., "oom", "killed_by_host"


class HeartbeatRequest(BaseModel):
    """Request body for heartbeat update.

    Matches old HeartbeatData model for compatibility.
    """

    running_tasks: list[int] = Field(default_factory=list, description="List of running task IDs on this runner")
    killed_tasks: list[HeartbeatKilledTaskInfo] = Field(default_factory=list, description="Tasks killed by runner")
    cpu_percent: float | None = None
    memory_percent: float | None = None
    memory_used_bytes: int | None = None
    memory_total_bytes: int | None = None
    current_avg_temp: float | None = None
    current_max_temp: float | None = None
    gpu_info: list[dict] | None = None


class RegisterRequest(BaseModel):
    """Request body for runner registration."""

    hostname: str
    url: str
    total_cores: int
    total_ram_bytes: int | None = None
    numa_topology: dict | None = None
    gpu_info: list[dict] | None = None


class TaskStatusUpdate(BaseModel):
    """Request body for task status update from runner."""

    task_id: int
    status: str
    exit_code: int | None = None
    message: str | None = None
    started_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None = None
    ssh_port: int | None = None  # For VPS tasks - actual bound SSH port


# =============================================================================
# Node Response Models
# =============================================================================


class NodeResponse(BaseModel):
    """Response for a single node."""

    hostname: str
    url: str
    total_cores: int
    memory_total_bytes: int | None
    status: str
    last_heartbeat: str | None
    cpu_percent: float | None
    memory_percent: float | None
    memory_used_bytes: int | None
    current_avg_temp: float | None
    current_max_temp: float | None
    numa_topology: dict[int, list[int]] | None
    gpu_info: list[dict]


class NodeListResponse(BaseModel):
    """Response for node list."""

    items: list[NodeResponse]
    total: int


# =============================================================================
# Docker Request Models
# =============================================================================


class DockerCreateContainerRequest(BaseModel):
    """Request body for creating a Docker container."""

    image_name: str = Field(..., description="Base Docker image to use")
    container_name: str = Field(..., description="Name for the new container")


class DockerCommitRequest(BaseModel):
    """Request body for committing a container to image."""

    source_container: str = Field(..., description="Container to commit from")
    hakuriver_name: str = Field(..., description="HakuRiver environment name")


# =============================================================================
# Docker Response Models
# =============================================================================


class DockerImageResponse(BaseModel):
    """Response for a Docker image."""

    name: str
    tag: str
    full_tag: str
    created: str | None
    size_bytes: int | None


class DockerImageListResponse(BaseModel):
    """Response for Docker image list."""

    items: list[DockerImageResponse]


class DockerContainerResponse(BaseModel):
    """Response for a Docker container."""

    name: str
    image: str
    status: str
    created: str | None


class DockerContainerListResponse(BaseModel):
    """Response for Docker container list."""

    items: list[DockerContainerResponse]


# =============================================================================
# Health Response Models
# =============================================================================


class HealthResponse(BaseModel):
    """Response for health check."""

    status: str
    version: str
    uptime_seconds: float


class ClusterHealthResponse(BaseModel):
    """Response for cluster health overview."""

    total_nodes: int
    online_nodes: int
    offline_nodes: int
    total_tasks: int
    running_tasks: int
    pending_tasks: int
    completed_tasks: int
    failed_tasks: int


# =============================================================================
# Error Response Models
# =============================================================================


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str
    detail: str | None = None
    request_id: str | None = None


class ValidationErrorResponse(BaseModel):
    """Validation error response."""

    error: str = "Validation Error"
    detail: list[dict]
