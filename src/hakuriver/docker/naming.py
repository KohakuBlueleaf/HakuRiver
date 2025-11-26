"""Container and image naming conventions for HakuRiver."""

# Prefixes for container names
HAKURIVER_PREFIX: str = "hakuriver"
TASK_PREFIX: str = f"{HAKURIVER_PREFIX}-task"
VPS_PREFIX: str = f"{HAKURIVER_PREFIX}-vps"
ENV_PREFIX: str = f"{HAKURIVER_PREFIX}-env"

# Docker label keys
LABEL_MANAGED: str = "hakuriver.managed"
LABEL_TASK_ID: str = "hakuriver.task_id"
LABEL_TASK_TYPE: str = "hakuriver.task_type"
LABEL_NODE: str = "hakuriver.node"


def task_container_name(task_id: int) -> str:
    """Generate container name for a task."""
    return f"{TASK_PREFIX}-{task_id}"


def vps_container_name(task_id: int) -> str:
    """Generate container name for a VPS session."""
    return f"{VPS_PREFIX}-{task_id}"


def env_container_name(env_name: str) -> str:
    """Generate container name for environment building."""
    return f"{ENV_PREFIX}-{env_name}"


def image_tag(env_name: str, tag: str = "base") -> str:
    """Generate image tag for an environment."""
    return f"{HAKURIVER_PREFIX}/{env_name}:{tag}"


def parse_image_tag(full_tag: str) -> tuple[str, str, str]:
    """
    Parse image tag into components.

    Args:
        full_tag: Full image tag like "hakuriver/myenv:base"

    Returns:
        Tuple of (namespace, name, tag)

    Examples:
        >>> parse_image_tag("hakuriver/myenv:base")
        ('hakuriver', 'myenv', 'base')
        >>> parse_image_tag("python:3.11")
        ('', 'python', '3.11')
        >>> parse_image_tag("ubuntu")
        ('', 'ubuntu', 'latest')
    """
    parts = full_tag.split("/")

    match len(parts):
        case 1:
            namespace = ""
            name_tag = parts[0]
        case 2:
            namespace = parts[0]
            name_tag = parts[1]
        case _:
            namespace = parts[0]
            name_tag = "/".join(parts[1:])

    if ":" in name_tag:
        name, tag = name_tag.rsplit(":", 1)
    else:
        name = name_tag
        tag = "latest"

    return namespace, name, tag


def make_labels(
    task_id: int,
    task_type: str,
    node: str | None = None,
) -> dict[str, str]:
    """
    Create Docker labels for a HakuRiver container.

    Args:
        task_id: The task ID
        task_type: Either "command" or "vps"
        node: Optional node hostname

    Returns:
        Dictionary of Docker labels
    """
    labels = {
        LABEL_MANAGED: "true",
        LABEL_TASK_ID: str(task_id),
        LABEL_TASK_TYPE: task_type,
    }
    if node:
        labels[LABEL_NODE] = node
    return labels


def is_hakuriver_container(container_name: str) -> bool:
    """
    Check if a container name matches HakuRiver naming convention.

    HakuRiver containers use the prefix "hakuriver-" followed by:
    - "task-{task_id}" for command tasks
    - "vps-{task_id}" for VPS sessions
    - "env-{name}" for environment building
    """
    return container_name.startswith(HAKURIVER_PREFIX)


def extract_task_id_from_name(container_name: str) -> int | None:
    """
    Extract task ID from container name.

    Args:
        container_name: Container name like "hakuriver-task-12345"

    Returns:
        Task ID or None if not a valid HakuRiver container name
    """
    for prefix in (TASK_PREFIX, VPS_PREFIX):
        if container_name.startswith(f"{prefix}-"):
            try:
                return int(container_name[len(prefix) + 1 :])
            except ValueError:
                return None
    return None
