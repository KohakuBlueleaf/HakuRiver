from pydantic import BaseModel, Field


class TaskInfo(BaseModel):
    task_id: int
    command: str
    arguments: list[str] = Field(default_factory=list)
    env_vars: dict[str, str] = Field(default_factory=dict)
    required_cores: int
    required_gpus: list[int] | None = None  # Number of GPUs required (if any)
    stdout_path: str
    stderr_path: str
    required_memory_bytes: int | None = None
    target_numa_node_id: int | None = Field(
        default=None, description="Target NUMA node ID for execution"
    )
    docker_image_name: str  # Image tag to use (e.g., hakuriver/myenv:base)
    docker_privileged: bool
    docker_additional_mounts: list[str]  # ONLY additional mounts specified by host/task
