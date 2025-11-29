"""
Container and image naming conventions for HakuRiver.

This module defines naming conventions and utilities for Docker containers
and images managed by HakuRiver. Consistent naming enables:
- Easy identification of HakuRiver-managed resources
- Task/VPS tracking via container names
- Image versioning and distribution

Naming Patterns:
    - Task containers: kohakuriver-task-{task_id}
    - VPS containers:  kohakuriver-vps-{task_id}
    - Environment containers: kohakuriver-env-{name}
    - Images: kohakuriver/{name}:{tag}
    - Snapshots: kohakuriver-snapshot/vps-{task_id}:{timestamp}
"""

# =============================================================================
# Name Prefixes
# =============================================================================

KOHAKURIVER_PREFIX: str = "kohakuriver"
TASK_PREFIX: str = f"{KOHAKURIVER_PREFIX}-task"
VPS_PREFIX: str = f"{KOHAKURIVER_PREFIX}-vps"
ENV_PREFIX: str = f"{KOHAKURIVER_PREFIX}-env"
SNAPSHOT_PREFIX: str = f"{KOHAKURIVER_PREFIX}-snapshot"


# =============================================================================
# Docker Labels
# =============================================================================

LABEL_MANAGED: str = "kohakuriver.managed"
LABEL_TASK_ID: str = "kohakuriver.task_id"
LABEL_TASK_TYPE: str = "kohakuriver.task_type"
LABEL_NODE: str = "kohakuriver.node"


# =============================================================================
# Container Name Generators
# =============================================================================


def task_container_name(task_id: int) -> str:
    """
    Generate container name for a command task.

    Args:
        task_id: Unique task identifier.

    Returns:
        Container name like "kohakuriver-task-12345".
    """
    return f"{TASK_PREFIX}-{task_id}"


def vps_container_name(task_id: int) -> str:
    """
    Generate container name for a VPS session.

    Args:
        task_id: Unique task identifier.

    Returns:
        Container name like "kohakuriver-vps-12345".
    """
    return f"{VPS_PREFIX}-{task_id}"


def env_container_name(env_name: str) -> str:
    """
    Generate container name for environment building.

    Args:
        env_name: Environment name.

    Returns:
        Container name like "kohakuriver-env-myenv".
    """
    return f"{ENV_PREFIX}-{env_name}"


# =============================================================================
# Image Tag Generators
# =============================================================================


def image_tag(env_name: str, tag: str = "base") -> str:
    """
    Generate image tag for an environment.

    Args:
        env_name: Environment name.
        tag: Image tag (default: "base").

    Returns:
        Image tag like "kohakuriver/myenv:base".
    """
    return f"{KOHAKURIVER_PREFIX}/{env_name}:{tag}"


def snapshot_image_tag(task_id: int, timestamp: int) -> str:
    """
    Generate image tag for a VPS snapshot.

    Args:
        task_id: VPS task ID.
        timestamp: Unix timestamp when snapshot was created.

    Returns:
        Image tag like "kohakuriver-snapshot/vps-12345:1234567890".
    """
    return f"{SNAPSHOT_PREFIX}/vps-{task_id}:{timestamp}"


# =============================================================================
# Tag Parsing Functions
# =============================================================================


def parse_snapshot_tag(tag: str) -> tuple[int, int] | None:
    """
    Parse a snapshot image tag to extract task_id and timestamp.

    Args:
        tag: Image tag like "kohakuriver-snapshot/vps-12345:1234567890".

    Returns:
        Tuple of (task_id, timestamp), or None if not a valid snapshot tag.
    """
    prefix = f"{SNAPSHOT_PREFIX}/vps-"
    if not tag.startswith(prefix):
        return None

    try:
        rest = tag[len(prefix) :]
        if ":" not in rest:
            return None
        task_id_str, timestamp_str = rest.split(":", 1)
        return int(task_id_str), int(timestamp_str)
    except (ValueError, IndexError):
        return None


def parse_image_tag(full_tag: str) -> tuple[str, str, str]:
    """
    Parse a full image tag into its components.

    Args:
        full_tag: Full image tag (e.g., "kohakuriver/myenv:base").

    Returns:
        Tuple of (namespace, name, tag).

    Examples:
        >>> parse_image_tag("kohakuriver/myenv:base")
        ('kohakuriver', 'myenv', 'base')
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


# =============================================================================
# Label Functions
# =============================================================================


def make_labels(
    task_id: int,
    task_type: str,
    node: str | None = None,
) -> dict[str, str]:
    """
    Create Docker labels for a HakuRiver container.

    Labels enable filtering and identification of managed containers.

    Args:
        task_id: The task ID.
        task_type: Task type ("command" or "vps").
        node: Optional node hostname.

    Returns:
        Dictionary of Docker labels.
    """
    labels = {
        LABEL_MANAGED: "true",
        LABEL_TASK_ID: str(task_id),
        LABEL_TASK_TYPE: task_type,
    }
    if node:
        labels[LABEL_NODE] = node
    return labels


# =============================================================================
# Name Validation Functions
# =============================================================================


def is_kohakuriver_container(container_name: str) -> bool:
    """
    Check if a container name matches HakuRiver naming convention.

    Args:
        container_name: Container name to check.

    Returns:
        True if the container is managed by HakuRiver.
    """
    return container_name.startswith(KOHAKURIVER_PREFIX)


def extract_task_id_from_name(container_name: str) -> int | None:
    """
    Extract task ID from a HakuRiver container name.

    Args:
        container_name: Container name like "kohakuriver-task-12345".

    Returns:
        Task ID as integer, or None if not a valid HakuRiver container.
    """
    for prefix in (TASK_PREFIX, VPS_PREFIX):
        full_prefix = f"{prefix}-"
        if container_name.startswith(full_prefix):
            try:
                return int(container_name[len(full_prefix) :])
            except ValueError:
                return None
    return None
