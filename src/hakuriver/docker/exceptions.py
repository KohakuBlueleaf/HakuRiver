"""Docker-related exceptions for HakuRiver."""


class DockerError(Exception):
    """Base exception for Docker-related errors."""

    pass


class ContainerNotFoundError(DockerError):
    """Raised when a container is not found."""

    def __init__(self, container_name: str):
        self.container_name = container_name
        super().__init__(f"Container not found: {container_name}")


class ImageNotFoundError(DockerError):
    """Raised when an image is not found."""

    def __init__(self, image_name: str):
        self.image_name = image_name
        super().__init__(f"Image not found: {image_name}")


class ContainerCreationError(DockerError):
    """Raised when container creation fails."""

    def __init__(self, message: str, container_name: str | None = None):
        self.container_name = container_name
        super().__init__(message)


class ContainerExecutionError(DockerError):
    """Raised when command execution in container fails."""

    def __init__(self, message: str, exit_code: int | None = None):
        self.exit_code = exit_code
        super().__init__(message)


class ImageBuildError(DockerError):
    """Raised when image build fails."""

    def __init__(self, message: str, image_tag: str | None = None):
        self.image_tag = image_tag
        super().__init__(message)


class ImageExportError(DockerError):
    """Raised when image export (save to tarball) fails."""

    def __init__(self, message: str, image_tag: str | None = None):
        self.image_tag = image_tag
        super().__init__(message)


class ImageImportError(DockerError):
    """Raised when image import (load from tarball) fails."""

    def __init__(self, message: str, tarball_path: str | None = None):
        self.tarball_path = tarball_path
        super().__init__(message)


class DockerConnectionError(DockerError):
    """Raised when connection to Docker daemon fails."""

    pass


class ResourceAllocationError(DockerError):
    """Raised when resource allocation fails (CPU, memory, GPU)."""

    def __init__(self, message: str, resource_type: str | None = None):
        self.resource_type = resource_type
        super().__init__(message)
