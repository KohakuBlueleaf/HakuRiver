"""
Docker-related exceptions for HakuRiver.

This module defines exceptions for Docker operations including container
management, image operations, and resource allocation.

Exception Hierarchy:
    DockerError (base)
    ├── DockerConnectionError
    ├── ContainerNotFoundError
    ├── ContainerCreationError
    ├── ContainerExecutionError
    ├── ImageNotFoundError
    ├── ImageBuildError
    ├── ImageExportError
    ├── ImageImportError
    └── ResourceAllocationError
"""

# =============================================================================
# Base Exception
# =============================================================================


class DockerError(Exception):
    """Base exception for all Docker-related errors."""


# =============================================================================
# Connection Exceptions
# =============================================================================


class DockerConnectionError(DockerError):
    """
    Raised when connection to Docker daemon fails.

    Common causes:
        - Docker daemon not running
        - Permission denied (user not in docker group)
        - Docker socket not accessible
    """


# =============================================================================
# Container Exceptions
# =============================================================================


class ContainerNotFoundError(DockerError):
    """
    Raised when a container cannot be found.

    Attributes:
        container_name: Name of the container that was not found.
    """

    def __init__(self, container_name: str):
        self.container_name = container_name
        super().__init__(f"Container not found: {container_name}")


class ContainerCreationError(DockerError):
    """
    Raised when container creation fails.

    Attributes:
        container_name: Name of the container that failed to create.
    """

    def __init__(self, message: str, container_name: str | None = None):
        self.container_name = container_name
        super().__init__(message)


class ContainerExecutionError(DockerError):
    """
    Raised when command execution in a container fails.

    Attributes:
        exit_code: The exit code of the failed command.
    """

    def __init__(self, message: str, exit_code: int | None = None):
        self.exit_code = exit_code
        super().__init__(message)


# =============================================================================
# Image Exceptions
# =============================================================================


class ImageNotFoundError(DockerError):
    """
    Raised when an image cannot be found locally or in registry.

    Attributes:
        image_name: Name/tag of the image that was not found.
    """

    def __init__(self, image_name: str):
        self.image_name = image_name
        super().__init__(f"Image not found: {image_name}")


class ImageBuildError(DockerError):
    """
    Raised when image build or commit fails.

    Attributes:
        image_tag: Tag of the image that failed to build.
    """

    def __init__(self, message: str, image_tag: str | None = None):
        self.image_tag = image_tag
        super().__init__(message)


class ImageExportError(DockerError):
    """
    Raised when image export (save to tarball) fails.

    Attributes:
        image_tag: Tag of the image that failed to export.
    """

    def __init__(self, message: str, image_tag: str | None = None):
        self.image_tag = image_tag
        super().__init__(message)


class ImageImportError(DockerError):
    """
    Raised when image import (load from tarball) fails.

    Attributes:
        tarball_path: Path to the tarball that failed to load.
    """

    def __init__(self, message: str, tarball_path: str | None = None):
        self.tarball_path = tarball_path
        super().__init__(message)


# =============================================================================
# Resource Exceptions
# =============================================================================


class ResourceAllocationError(DockerError):
    """
    Raised when resource allocation fails (CPU, memory, GPU).

    Attributes:
        resource_type: Type of resource that failed to allocate
                      (e.g., 'cpu', 'memory', 'gpu').
    """

    def __init__(self, message: str, resource_type: str | None = None):
        self.resource_type = resource_type
        super().__init__(message)
