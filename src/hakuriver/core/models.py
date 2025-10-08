import datetime
import re

from pydantic import BaseModel, Field, field_validator
from hakuriver.utils.gpu import GPUInfo


# --- Pydantic Models for runner-host connection ---
class TaskInfo(BaseModel):
    task_id: int
    task_type: str = "command"  # command or vps
    command: str = ""
    arguments: list[str] = Field(default_factory=list)
    env_vars: dict[str, str] = Field(default_factory=dict)
    required_cores: int
    required_gpus: list[int] | None = None  # Number of GPUs required (if any)
    stdout_path: str = "/dev/null"
    stderr_path: str = "/dev/null"
    required_memory_bytes: int | None = None
    target_numa_node_id: int | None = Field(
        default=None, description="Target NUMA node ID for execution"
    )
    docker_image_name: str  # Image tag to use (e.g., hakuriver/myenv:base)
    docker_privileged: bool
    docker_additional_mounts: list[str]  # ONLY additional mounts specified by host/task


class TaskStatusUpdate(BaseModel):
    task_id: int
    status: str
    exit_code: int | None = None
    message: str | None = None
    started_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None = None


class HeartbeatKilledTaskInfo(BaseModel):
    task_id: int
    reason: str  # e.g., "oom", "killed_by_host"


class HeartbeatData(BaseModel):
    running_tasks: list[int]
    killed_tasks: list[HeartbeatKilledTaskInfo] = Field(default_factory=list)
    cpu_percent: float | None = None
    memory_percent: float | None = None
    memory_used_bytes: int | None = None
    memory_total_bytes: int | None = None
    current_avg_temp: float | None = None
    current_max_temp: float | None = None
    gpu_info: list[GPUInfo] = Field(default_factory=list)


# --- Pydantic Models for Host ---
class RunnerInfo(BaseModel):
    hostname: str
    total_cores: int
    total_ram_bytes: int
    runner_url: str
    numa_topology: dict | None = None
    gpu_info: list[GPUInfo] | None = Field(default_factory=list)


class TaskRequest(BaseModel):
    task_type: str = "command"  # command or vps
    command: str = ""
    arguments: list[str] = Field(default_factory=list)
    env_vars: dict[str, str] = Field(default_factory=dict)
    required_cores: int = Field(
        default=1, ge=0, description="Number of CPU cores required"
    )
    required_gpus: list[list[int]] | None = Field(
        default=None,
        description="List of GPU IDs required for the task for all targets (if any)",
    )
    required_memory_bytes: int | None = Field(
        default=None, ge=0, description="Memory limit in bytes"
    )
    targets: list[str] | None = Field(
        default=None,
        min_length=0,
        description='List of targets, e.g., ["host1", "host2:0", "host1:1"]',
    )
    container_name: str | None = Field(
        default=None,
        description="Optional: Override the default container name for this task batch.",
    )
    privileged: bool | None = Field(
        default=None,
        description="Optional: Override the default privileged setting for this task batch.",
    )
    additional_mounts: list[str] | None = Field(
        default=None,
        description="Optional: Override the default additional mounts for this task batch.",
    )

    @field_validator("targets")
    @classmethod
    def validate_targets_format(cls, v):
        if v is None:
            return None
        pattern = r"^[a-zA-Z0-9.-]+(:\d+)?$"  # hostname[:numa_id]
        for target in v:
            if not re.match(pattern, target):
                raise ValueError(
                    f"Invalid target format: '{target}'. Use 'hostname' or 'hostname:numa_id'."
                )
        return v
