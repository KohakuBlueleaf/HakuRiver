"""Docker SDK integration for HakuRiver."""

from kohakuriver.docker import utils
from kohakuriver.docker.client import DockerManager, get_docker_manager
from kohakuriver.docker.exceptions import (
    ContainerCreationError,
    ContainerNotFoundError,
    DockerConnectionError,
    DockerError,
    ImageBuildError,
    ImageExportError,
    ImageImportError,
    ImageNotFoundError,
    ResourceAllocationError,
)
from kohakuriver.docker.naming import (
    KOHAKURIVER_PREFIX,
    LABEL_MANAGED,
    LABEL_NODE,
    LABEL_TASK_ID,
    LABEL_TASK_TYPE,
    TASK_PREFIX,
    VPS_PREFIX,
    extract_task_id_from_name,
    image_tag,
    is_kohakuriver_container,
    make_labels,
    parse_image_tag,
    task_container_name,
    vps_container_name,
)

__all__ = [
    # Utils module
    "utils",
    # Client
    "DockerManager",
    "get_docker_manager",
    # Exceptions
    "ContainerCreationError",
    "ContainerNotFoundError",
    "DockerConnectionError",
    "DockerError",
    "ImageBuildError",
    "ImageExportError",
    "ImageImportError",
    "ImageNotFoundError",
    "ResourceAllocationError",
    # Naming
    "KOHAKURIVER_PREFIX",
    "LABEL_MANAGED",
    "LABEL_NODE",
    "LABEL_TASK_ID",
    "LABEL_TASK_TYPE",
    "TASK_PREFIX",
    "VPS_PREFIX",
    "extract_task_id_from_name",
    "image_tag",
    "is_kohakuriver_container",
    "make_labels",
    "parse_image_tag",
    "task_container_name",
    "vps_container_name",
]
