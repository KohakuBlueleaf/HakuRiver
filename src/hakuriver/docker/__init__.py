"""Docker SDK integration for HakuRiver."""
from hakuriver.docker import utils
from hakuriver.docker.client import DockerManager, get_docker_manager
from hakuriver.docker.exceptions import (
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
from hakuriver.docker.naming import (
    HAKURIVER_PREFIX,
    LABEL_MANAGED,
    LABEL_NODE,
    LABEL_TASK_ID,
    LABEL_TASK_TYPE,
    TASK_PREFIX,
    VPS_PREFIX,
    extract_task_id_from_name,
    image_tag,
    is_hakuriver_container,
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
    "HAKURIVER_PREFIX",
    "LABEL_MANAGED",
    "LABEL_NODE",
    "LABEL_TASK_ID",
    "LABEL_TASK_TYPE",
    "TASK_PREFIX",
    "VPS_PREFIX",
    "extract_task_id_from_name",
    "image_tag",
    "is_hakuriver_container",
    "make_labels",
    "parse_image_tag",
    "task_container_name",
    "vps_container_name",
]
