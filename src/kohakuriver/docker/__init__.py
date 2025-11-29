"""
Docker SDK integration for HakuRiver.

This package provides Docker management capabilities including:
    - Container lifecycle management (DockerManager)
    - Image operations (pull, commit, save, load)
    - HakuRiver-specific naming conventions
    - Container synchronization via shared storage

Submodules:
    - client: DockerManager class for container/image operations
    - exceptions: Docker-related exception classes
    - naming: Container/image naming utilities
    - utils: Tarball and sync utilities
"""

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
    # Naming constants
    "KOHAKURIVER_PREFIX",
    "LABEL_MANAGED",
    "LABEL_NODE",
    "LABEL_TASK_ID",
    "LABEL_TASK_TYPE",
    "TASK_PREFIX",
    "VPS_PREFIX",
    # Naming functions
    "extract_task_id_from_name",
    "image_tag",
    "is_kohakuriver_container",
    "make_labels",
    "parse_image_tag",
    "task_container_name",
    "vps_container_name",
]
