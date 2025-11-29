"""
Docker client wrapper using docker-py SDK.

This module provides the DockerManager class, a high-level wrapper around
the docker-py SDK for container and image management in HakuRiver.

Features:
    - Container lifecycle management (create, start, stop, remove, pause)
    - Task and VPS container creation with resource constraints
    - Image operations (pull, commit, save, load)
    - Container synchronization via shared storage tarballs
"""

import datetime
import os
import re
import time

import docker
from docker.errors import APIError, ContainerError, ImageNotFound, NotFound
from docker.models.containers import Container
from docker.models.images import Image
from docker.types import DeviceRequest, Mount

from kohakuriver.docker.exceptions import (
    ContainerCreationError,
    ContainerNotFoundError,
    DockerConnectionError,
    ImageBuildError,
    ImageExportError,
    ImageImportError,
    ImageNotFoundError,
)
from kohakuriver.docker.naming import (
    LABEL_MANAGED,
    image_tag,
    make_labels,
    task_container_name,
    vps_container_name,
)
from kohakuriver.utils.logger import get_logger

log = get_logger(__name__)


# =============================================================================
# DockerManager Class
# =============================================================================


class DockerManager:
    """
    Manages Docker operations for HakuRiver using docker-py SDK.

    Provides methods for:
        - Container lifecycle (create, start, stop, remove, pause, unpause)
        - Image management (pull, commit, save, load)
        - Container synchronization from shared storage

    Attributes:
        client: The docker-py client instance.
    """

    def __init__(self, timeout: int | None = None):
        """
        Initialize Docker client.

        Args:
            timeout: Request timeout in seconds. None means no timeout.

        Raises:
            DockerConnectionError: If connection to Docker daemon fails.
        """
        try:
            self.client = docker.from_env(timeout=timeout)
            self.client.ping()
            log.debug("Docker client initialized successfully")
        except Exception as e:
            log.error(f"Failed to connect to Docker daemon: {e}")
            raise DockerConnectionError(f"Failed to connect to Docker: {e}") from e

    # =========================================================================
    # Container Existence and Retrieval
    # =========================================================================

    def container_exists(self, name: str) -> bool:
        """
        Check if a container exists.

        Args:
            name: Container name.

        Returns:
            True if container exists, False otherwise.
        """
        try:
            self.client.containers.get(name)
            return True
        except NotFound:
            return False

    def get_container(self, name: str) -> Container:
        """
        Get a container by name.

        Args:
            name: Container name.

        Returns:
            Container object.

        Raises:
            ContainerNotFoundError: If container doesn't exist.
        """
        try:
            return self.client.containers.get(name)
        except NotFound:
            raise ContainerNotFoundError(name)

    # =========================================================================
    # Container Creation
    # =========================================================================

    def create_container(
        self,
        image: str,
        name: str,
        command: str | list[str] = "sleep infinity",
        detach: bool = True,
        **kwargs,
    ) -> Container:
        """
        Create and start a container.

        Args:
            image: Docker image name/tag.
            name: Container name.
            command: Command to run.
            detach: Run in detached mode.
            **kwargs: Additional arguments passed to containers.run().

        Returns:
            Container object.

        Raises:
            ContainerCreationError: If container creation fails.
        """
        try:
            return self.client.containers.run(
                image,
                command,
                name=name,
                detach=detach,
                **kwargs,
            )
        except ImageNotFound:
            log.info(f"Image {image} not found locally, pulling...")
            self.client.images.pull(image)
            return self.client.containers.run(
                image,
                command,
                name=name,
                detach=detach,
                **kwargs,
            )
        except APIError as e:
            log.error(f"Failed to create container {name}: {e}")
            raise ContainerCreationError(str(e), name) from e

    def create_task_container(
        self,
        task_id: int,
        image: str,
        command: list[str],
        cpuset_cpus: str | None = None,
        cpuset_mems: str | None = None,
        mem_limit: str | None = None,
        gpu_ids: list[int] | None = None,
        mounts: list[Mount] | None = None,
        environment: dict[str, str] | None = None,
        working_dir: str = "/shared",
        privileged: bool = False,
        node: str | None = None,
    ) -> Container:
        """
        Create a container for task execution.

        Args:
            task_id: Task ID.
            image: Docker image name/tag.
            command: Command to run.
            cpuset_cpus: CPUs to use (e.g., "0-3" or "0,1,2").
            cpuset_mems: NUMA nodes to use (e.g., "0" or "0,1").
            mem_limit: Memory limit (e.g., "2g").
            gpu_ids: List of GPU IDs to use.
            mounts: List of Mount objects.
            environment: Environment variables.
            working_dir: Working directory inside container.
            privileged: Run in privileged mode.
            node: Node hostname (for labeling).

        Returns:
            Container object.
        """
        container_name = task_container_name(task_id)
        labels = make_labels(task_id, "command", node)

        kwargs = self._build_container_kwargs(
            labels=labels,
            cpuset_cpus=cpuset_cpus,
            cpuset_mems=cpuset_mems,
            mem_limit=mem_limit,
            gpu_ids=gpu_ids,
            mounts=mounts,
            environment=environment,
            working_dir=working_dir,
            privileged=privileged,
            task_id=task_id,
        )
        kwargs["network_mode"] = "host"

        log.debug(f"Creating task container {container_name} with image {image}")
        return self.create_container(image, container_name, command, **kwargs)

    def create_vps_container(
        self,
        task_id: int,
        image: str,
        ssh_port: int,
        public_key: str | None = None,
        cpuset_cpus: str | None = None,
        cpuset_mems: str | None = None,
        mem_limit: str | None = None,
        gpu_ids: list[int] | None = None,
        mounts: list[Mount] | None = None,
        working_dir: str = "/shared",
        privileged: bool = False,
        node: str | None = None,
    ) -> Container:
        """
        Create a VPS container with SSH access.

        Args:
            task_id: Task ID.
            image: Docker image name/tag.
            ssh_port: Host port for SSH (mapped to container port 22).
            public_key: SSH public key (None = passwordless login).
            cpuset_cpus: CPUs to use.
            cpuset_mems: NUMA nodes to use.
            mem_limit: Memory limit.
            gpu_ids: List of GPU IDs.
            mounts: List of Mount objects.
            working_dir: Working directory.
            privileged: Run in privileged mode.
            node: Node hostname.

        Returns:
            Container object.
        """
        container_name = vps_container_name(task_id)
        labels = make_labels(task_id, "vps", node)

        setup_cmd = self._build_ssh_setup_command(image, public_key, task_id)

        kwargs = self._build_container_kwargs(
            labels=labels,
            cpuset_cpus=cpuset_cpus,
            cpuset_mems=cpuset_mems,
            mem_limit=mem_limit,
            gpu_ids=gpu_ids,
            mounts=mounts,
            environment=None,
            working_dir=working_dir,
            privileged=privileged,
            task_id=task_id,
        )
        kwargs["ports"] = {"22/tcp": ssh_port}
        kwargs["restart_policy"] = {"Name": "unless-stopped"}

        log.debug(f"Creating VPS container {container_name} with image {image}")
        return self.create_container(
            image,
            container_name,
            ["/bin/sh", "-c", setup_cmd],
            **kwargs,
        )

    def _build_container_kwargs(
        self,
        labels: dict[str, str],
        cpuset_cpus: str | None,
        cpuset_mems: str | None,
        mem_limit: str | None,
        gpu_ids: list[int] | None,
        mounts: list[Mount] | None,
        environment: dict[str, str] | None,
        working_dir: str,
        privileged: bool,
        task_id: int,
    ) -> dict:
        """Build common container creation kwargs."""
        kwargs: dict = {
            "labels": labels,
            "working_dir": working_dir,
        }

        if cpuset_cpus:
            kwargs["cpuset_cpus"] = cpuset_cpus
        if cpuset_mems:
            kwargs["cpuset_mems"] = cpuset_mems
        if mem_limit:
            kwargs["mem_limit"] = mem_limit
        if mounts:
            kwargs["mounts"] = mounts
        if environment:
            kwargs["environment"] = environment

        if privileged:
            kwargs["privileged"] = True
            log.warning(f"Task {task_id}: Running with --privileged flag")
        else:
            kwargs["cap_add"] = ["SYS_NICE"]

        if gpu_ids:
            kwargs["device_requests"] = [
                DeviceRequest(
                    device_ids=[str(gid) for gid in gpu_ids],
                    capabilities=[["gpu"]],
                )
            ]

        return kwargs

    def _build_ssh_setup_command(
        self,
        image: str,
        public_key: str | None,
        task_id: int,
    ) -> str:
        """Build SSH setup command based on detected package manager."""
        pkg_manager = self._detect_package_manager(image)
        install_cmd = self._get_ssh_install_command(pkg_manager)
        auth_config = self._get_ssh_auth_config(public_key, task_id)

        return (
            f"{install_cmd} && "
            "ssh-keygen -A && "
            f"{auth_config} && "
            "mkdir -p /run/sshd && "
            "chmod 0755 /run/sshd && "
            "/usr/sbin/sshd -D -e"
        )

    def _get_ssh_install_command(self, pkg_manager: str) -> str:
        """Get SSH server install command for package manager."""
        match pkg_manager:
            case "apk":
                return "apk update && apk add --no-cache openssh"
            case "apt" | "apt-get":
                return (
                    f"{pkg_manager} update && {pkg_manager} install -y openssh-server"
                )
            case "dnf":
                return "dnf install -y openssh-server"
            case "yum":
                return "yum install -y openssh-server"
            case "zypper":
                return "zypper refresh && zypper install -y openssh"
            case "pacman":
                return "pacman -Syu --noconfirm openssh"
            case _:
                return "echo 'SSH server should be pre-installed'"

    def _get_ssh_auth_config(self, public_key: str | None, task_id: int) -> str:
        """Get SSH authentication configuration."""
        if public_key:
            return (
                "echo 'PasswordAuthentication no' >> /etc/ssh/sshd_config && "
                "echo 'PermitRootLogin prohibit-password' >> /etc/ssh/sshd_config && "
                "mkdir -p /root/.ssh && "
                f"echo '{public_key}' > /root/.ssh/authorized_keys && "
                "chmod 700 /root/.ssh && "
                "chmod 600 /root/.ssh/authorized_keys"
            )
        return (
            "echo 'PasswordAuthentication yes' >> /etc/ssh/sshd_config && "
            "echo 'PermitRootLogin yes' >> /etc/ssh/sshd_config && "
            f"echo 'root:{task_id}' | chpasswd"
        )

    def _detect_package_manager(self, image: str) -> str:
        """Detect package manager in an image."""
        managers = ["apk", "apt-get", "apt", "dnf", "yum", "zypper", "pacman"]

        for manager in managers:
            try:
                result = self.client.containers.run(
                    image,
                    ["which", manager],
                    remove=True,
                    detach=False,
                )
                if result:
                    log.debug(f"Detected package manager: {manager}")
                    return manager
            except (ContainerError, Exception):
                continue

        log.debug("Could not detect package manager, assuming SSH pre-installed")
        return "unknown"

    # =========================================================================
    # Container Lifecycle
    # =========================================================================

    def stop_container(self, name: str, timeout: int = 10) -> bool:
        """
        Stop a container.

        Args:
            name: Container name.
            timeout: Seconds to wait before killing.

        Returns:
            True if stopped successfully, False otherwise.
        """
        try:
            container = self.client.containers.get(name)
            container.stop(timeout=timeout)
            log.info(f"Container {name} stopped")
            return True
        except NotFound:
            log.warning(f"Container {name} not found")
            return False
        except APIError as e:
            log.error(f"Failed to stop container {name}: {e}")
            return False

    def start_container(self, name: str) -> bool:
        """
        Start a stopped container.

        Args:
            name: Container name.

        Returns:
            True if started successfully, False otherwise.
        """
        try:
            container = self.client.containers.get(name)
            container.start()
            log.info(f"Container {name} started")
            return True
        except NotFound:
            log.warning(f"Container {name} not found")
            return False
        except APIError as e:
            log.error(f"Failed to start container {name}: {e}")
            return False

    def remove_container(self, name: str, force: bool = True) -> bool:
        """
        Remove a container.

        Args:
            name: Container name.
            force: Force removal even if running.

        Returns:
            True if removed successfully, False otherwise.
        """
        try:
            container = self.client.containers.get(name)
            container.remove(force=force)
            log.info(f"Container {name} removed")
            return True
        except NotFound:
            log.debug(f"Container {name} already removed")
            return True
        except APIError as e:
            log.error(f"Failed to remove container {name}: {e}")
            return False

    def pause_container(self, name: str) -> bool:
        """
        Pause a container.

        Args:
            name: Container name.

        Returns:
            True if paused successfully, False otherwise.

        Raises:
            ContainerNotFoundError: If container doesn't exist.
        """
        try:
            container = self.client.containers.get(name)
            container.pause()
            log.info(f"Container {name} paused")
            return True
        except NotFound:
            raise ContainerNotFoundError(name)
        except APIError as e:
            log.error(f"Failed to pause container {name}: {e}")
            return False

    def unpause_container(self, name: str) -> bool:
        """
        Unpause a container.

        Args:
            name: Container name.

        Returns:
            True if unpaused successfully, False otherwise.

        Raises:
            ContainerNotFoundError: If container doesn't exist.
        """
        try:
            container = self.client.containers.get(name)
            container.unpause()
            log.info(f"Container {name} unpaused")
            return True
        except NotFound:
            raise ContainerNotFoundError(name)
        except APIError as e:
            log.error(f"Failed to unpause container {name}: {e}")
            return False

    def kill_container(self, name: str, signal: str = "SIGKILL") -> bool:
        """
        Kill a container with a signal.

        Args:
            name: Container name.
            signal: Signal to send (default: SIGKILL).

        Returns:
            True if killed successfully, False otherwise.
        """
        try:
            container = self.client.containers.get(name)
            container.kill(signal=signal)
            log.info(f"Container {name} killed with {signal}")
            return True
        except NotFound:
            log.warning(f"Container {name} not found")
            return False
        except APIError as e:
            log.error(f"Failed to kill container {name}: {e}")
            return False

    # =========================================================================
    # Container Queries
    # =========================================================================

    def get_container_port(self, name: str, container_port: int = 22) -> int | None:
        """
        Get host port mapped to a container port.

        Args:
            name: Container name.
            container_port: Container port to look up.

        Returns:
            Host port number, or None if not found.
        """
        try:
            container = self.client.containers.get(name)
            ports = container.attrs["NetworkSettings"]["Ports"]
            port_key = f"{container_port}/tcp"
            if port_key in ports and ports[port_key]:
                return int(ports[port_key][0]["HostPort"])
            return None
        except (NotFound, KeyError, IndexError, TypeError):
            return None

    def list_kohakuriver_containers(self, all: bool = False) -> list[Container]:
        """
        List all HakuRiver-managed containers.

        Args:
            all: Include stopped containers.

        Returns:
            List of Container objects.
        """
        return self.client.containers.list(
            all=all,
            filters={"label": f"{LABEL_MANAGED}=true"},
        )

    def list_containers(
        self,
        all: bool = False,
        filters: dict | None = None,
    ) -> list[Container]:
        """
        List containers with optional filters.

        Args:
            all: Include stopped containers.
            filters: Docker filters dict.

        Returns:
            List of Container objects.
        """
        return self.client.containers.list(all=all, filters=filters)

    def list_images(self) -> list[Image]:
        """List all local images."""
        return self.client.images.list()

    def cleanup_stopped_containers(self) -> int:
        """
        Remove stopped HakuRiver containers.

        Returns:
            Number of containers removed.
        """
        removed = 0
        for container in self.list_kohakuriver_containers(all=True):
            if container.status in ("exited", "dead"):
                try:
                    container.remove()
                    removed += 1
                    log.info(f"Removed stopped container {container.name}")
                except APIError:
                    pass
        return removed

    # =========================================================================
    # Image Operations
    # =========================================================================

    def image_exists(self, tag: str) -> bool:
        """Check if an image exists locally."""
        try:
            self.client.images.get(tag)
            return True
        except ImageNotFound:
            return False

    def get_image(self, tag: str) -> Image:
        """
        Get an image by tag.

        Raises:
            ImageNotFoundError: If image doesn't exist.
        """
        try:
            return self.client.images.get(tag)
        except ImageNotFound:
            raise ImageNotFoundError(tag)

    def pull_image(self, tag: str) -> Image:
        """Pull an image from registry."""
        log.info(f"Pulling image {tag}...")
        return self.client.images.pull(tag)

    def commit_container(
        self,
        container_name: str,
        repository: str,
        tag: str = "base",
    ) -> Image:
        """
        Commit a container to an image.

        Args:
            container_name: Container to commit.
            repository: Image repository name.
            tag: Image tag.

        Returns:
            Image object.

        Raises:
            ContainerNotFoundError: If container doesn't exist.
            ImageBuildError: If commit fails.
        """
        try:
            container = self.client.containers.get(container_name)
            image = container.commit(repository=repository, tag=tag)
            log.info(f"Committed container {container_name} to {repository}:{tag}")
            return image
        except NotFound:
            raise ContainerNotFoundError(container_name)
        except APIError as e:
            raise ImageBuildError(str(e), f"{repository}:{tag}") from e

    def save_image(self, tag: str, output_path: str) -> None:
        """
        Save an image to a tarball.

        Args:
            tag: Image tag.
            output_path: Path for the tarball.

        Raises:
            ImageNotFoundError: If image doesn't exist.
            ImageExportError: If save fails.
        """
        try:
            image = self.client.images.get(tag)
            log.info(f"Saving image {tag} to {output_path}...")

            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                for chunk in image.save():
                    f.write(chunk)

            log.info(f"Image saved to {output_path}")
        except ImageNotFound:
            raise ImageNotFoundError(tag)
        except Exception as e:
            raise ImageExportError(str(e), tag) from e

    def load_image(self, tarball_path: str) -> list[Image]:
        """
        Load an image from a tarball.

        Args:
            tarball_path: Path to the tarball.

        Returns:
            List of loaded Image objects.

        Raises:
            ImageImportError: If load fails.
        """
        if not os.path.exists(tarball_path):
            raise ImageImportError(f"Tarball not found: {tarball_path}", tarball_path)

        try:
            log.info(f"Loading image from {tarball_path}...")
            with open(tarball_path, "rb") as f:
                images = self.client.images.load(f)
            log.info(f"Loaded {len(images)} image(s) from {tarball_path}")
            return images
        except Exception as e:
            raise ImageImportError(str(e), tarball_path) from e

    def get_image_created_timestamp(self, tag: str) -> int | None:
        """
        Get the creation timestamp of an image.

        Args:
            tag: Image tag.

        Returns:
            Unix timestamp, or None if not found.
        """
        try:
            image = self.client.images.get(tag)
            created_str = image.attrs.get("Created", "")
            if created_str:
                dt = datetime.datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                return int(dt.timestamp())
            return None
        except ImageNotFound:
            return None
        except Exception as e:
            log.error(f"Error getting image timestamp for {tag}: {e}")
            return None

    def remove_image(self, tag: str, force: bool = False) -> bool:
        """
        Remove an image.

        Args:
            tag: Image tag.
            force: Force removal.

        Returns:
            True if removed successfully, False otherwise.
        """
        try:
            self.client.images.remove(tag, force=force)
            log.info(f"Removed image {tag}")
            return True
        except ImageNotFound:
            return True
        except APIError as e:
            log.error(f"Failed to remove image {tag}: {e}")
            return False

    def prune_dangling_images(self) -> int:
        """
        Remove dangling images.

        Returns:
            Bytes reclaimed.
        """
        result = self.client.images.prune(filters={"dangling": True})
        space_reclaimed = result.get("SpaceReclaimed", 0)
        log.debug(f"Pruned dangling images, reclaimed {space_reclaimed} bytes")
        return space_reclaimed

    # =========================================================================
    # Container Sync Operations
    # =========================================================================

    def list_shared_tarballs(
        self,
        container_tar_dir: str,
        container_name: str,
    ) -> list[tuple[int, str]]:
        """
        List available tarballs for a container in shared storage.

        Args:
            container_tar_dir: Directory containing tarballs.
            container_name: Container name to search for.

        Returns:
            List of (timestamp, path) tuples, sorted newest first.
        """
        pattern = re.compile(rf"^{re.escape(container_name.lower())}-(\d+)\.tar$")
        tar_files: list[tuple[int, str]] = []

        if not os.path.isdir(container_tar_dir):
            return []

        for filename in os.listdir(container_tar_dir):
            match = pattern.match(filename)
            if match:
                try:
                    timestamp = int(match.group(1))
                    tar_path = os.path.join(container_tar_dir, filename)
                    tar_files.append((timestamp, tar_path))
                except ValueError:
                    continue

        tar_files.sort(key=lambda x: x[0], reverse=True)
        return tar_files

    def needs_sync(
        self,
        container_name: str,
        container_tar_dir: str,
    ) -> tuple[bool, str | None]:
        """
        Check if local image needs sync from shared storage.

        Args:
            container_name: Container name.
            container_tar_dir: Directory containing tarballs.

        Returns:
            Tuple of (needs_sync, path_to_latest_tar).
        """
        kohakuriver_tag = image_tag(container_name, "base")
        local_timestamp = self.get_image_created_timestamp(kohakuriver_tag)
        shared_tars = self.list_shared_tarballs(container_tar_dir, container_name)

        if not shared_tars:
            return False, None

        latest_timestamp, latest_path = shared_tars[0]

        if local_timestamp is None:
            log.info(f"Local image for {container_name} not found, sync needed")
            return True, latest_path

        if latest_timestamp > local_timestamp:
            log.info(
                f"Newer tarball for {container_name} "
                f"(shared: {latest_timestamp}, local: {local_timestamp})"
            )
            return True, latest_path

        log.debug(f"Local image for {container_name} is up-to-date")
        return False, None

    def sync_from_shared(self, container_name: str, tarball_path: str) -> bool:
        """
        Sync (load) an image from shared storage.

        Args:
            container_name: Container name.
            tarball_path: Path to the tarball.

        Returns:
            True if sync succeeded, False otherwise.
        """
        try:
            self.load_image(tarball_path)
            return True
        except ImageImportError as e:
            log.error(f"Failed to sync {container_name}: {e}")
            return False

    def create_container_tarball(
        self,
        source_container: str,
        kohakuriver_name: str,
        container_tar_dir: str,
    ) -> str | None:
        """
        Create a HakuRiver container tarball from an existing container.

        Args:
            source_container: Name of existing container to commit.
            kohakuriver_name: HakuRiver environment name.
            container_tar_dir: Directory to store tarball.

        Returns:
            Path to created tarball, or None on failure.
        """
        kohakuriver_tag = image_tag(kohakuriver_name, "base")
        timestamp = int(time.time())
        tarball_filename = f"{kohakuriver_name}-{timestamp}.tar"
        tarball_path = os.path.join(container_tar_dir, tarball_filename)

        try:
            self.stop_container(source_container)
            self.commit_container(
                source_container, f"kohakuriver/{kohakuriver_name}", "base"
            )
            self.save_image(kohakuriver_tag, tarball_path)

            # Clean up old tarballs
            for old_ts, old_path in self.list_shared_tarballs(
                container_tar_dir, kohakuriver_name
            ):
                if old_ts < timestamp:
                    try:
                        os.remove(old_path)
                        log.info(f"Removed old tarball: {old_path}")
                    except OSError as e:
                        log.warning(f"Failed to remove old tarball {old_path}: {e}")

            self.prune_dangling_images()

            log.info(f"Created container tarball at {tarball_path}")
            return tarball_path

        except Exception as e:
            log.error(f"Failed to create container tarball: {e}")
            self.remove_image(kohakuriver_tag, force=True)
            return None


# =============================================================================
# Global Instance
# =============================================================================

_docker_manager: DockerManager | None = None


def get_docker_manager() -> DockerManager:
    """
    Get the global DockerManager instance.

    Returns:
        Lazily initialized DockerManager singleton.
    """
    global _docker_manager
    if _docker_manager is None:
        _docker_manager = DockerManager()
    return _docker_manager
