"""Docker client wrapper using docker-py SDK."""

import datetime
import os
import re
import time

import docker
from docker.errors import APIError, ContainerError, ImageNotFound, NotFound
from docker.models.containers import Container
from docker.models.images import Image
from docker.types import DeviceRequest, Mount

from hakuriver.docker.exceptions import (
    ContainerCreationError,
    ContainerNotFoundError,
    DockerConnectionError,
    ImageBuildError,
    ImageExportError,
    ImageImportError,
    ImageNotFoundError,
)
from hakuriver.docker.naming import (
    LABEL_MANAGED,
    LABEL_NODE,
    LABEL_TASK_ID,
    LABEL_TASK_TYPE,
    TASK_PREFIX,
    VPS_PREFIX,
    image_tag,
    make_labels,
    task_container_name,
    vps_container_name,
)
from hakuriver.utils.logger import logger


class DockerManager:
    """
    Manages Docker operations for HakuRiver using docker-py SDK.

    Provides methods for:
    - Container lifecycle (create, start, stop, remove, pause, unpause)
    - Image management (pull, commit, save, load)
    - Container synchronization from shared storage
    """

    def __init__(self):
        """Initialize Docker client."""
        try:
            self.client = docker.from_env()
            self.client.ping()
        except Exception as e:
            raise DockerConnectionError(f"Failed to connect to Docker: {e}") from e

    # =========================================================================
    # Container Operations
    # =========================================================================

    def container_exists(self, name: str) -> bool:
        """Check if a container exists."""
        try:
            self.client.containers.get(name)
            return True
        except NotFound:
            return False

    def get_container(self, name: str) -> Container:
        """Get a container by name."""
        try:
            return self.client.containers.get(name)
        except NotFound:
            raise ContainerNotFoundError(name)

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
            image: Docker image name/tag
            name: Container name
            command: Command to run
            detach: Run in detached mode
            **kwargs: Additional arguments passed to containers.run()

        Returns:
            Container object
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
            logger.info(f"Image {image} not found locally, pulling...")
            self.client.images.pull(image)
            return self.client.containers.run(
                image,
                command,
                name=name,
                detach=detach,
                **kwargs,
            )
        except APIError as e:
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
            task_id: Task ID
            image: Docker image name/tag
            command: Command to run
            cpuset_cpus: CPUs to use (e.g., "0-3" or "0,1,2")
            cpuset_mems: NUMA nodes to use (e.g., "0" or "0,1")
            mem_limit: Memory limit (e.g., "2g")
            gpu_ids: List of GPU IDs to use
            mounts: List of Mount objects
            environment: Environment variables
            working_dir: Working directory inside container
            privileged: Run in privileged mode
            node: Node hostname (for labeling)

        Returns:
            Container object
        """
        container_name = task_container_name(task_id)
        labels = make_labels(task_id, "command", node)

        kwargs: dict = {
            "labels": labels,
            "network_mode": "host",
            # NOTE: We do NOT use remove=True (--rm) because it causes race conditions
            # with container.wait() for fast-exiting containers. Instead, we manually
            # remove containers after getting exit code. startup_check.py handles
            # orphan cleanup on runner restart.
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
            logger.warning(f"Task {task_id}: Running with --privileged flag!")
        else:
            kwargs["cap_add"] = ["SYS_NICE"]

        # GPU support via NVIDIA Container Toolkit
        if gpu_ids:
            kwargs["device_requests"] = [
                DeviceRequest(
                    device_ids=[str(gid) for gid in gpu_ids],
                    capabilities=[["gpu"]],
                )
            ]

        logger.debug(f"Creating task container {container_name} with image {image}")
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
            task_id: Task ID
            image: Docker image name/tag
            ssh_port: Host port for SSH (mapped to container port 22)
            public_key: SSH public key (None = no key, task_id as password concept)
            cpuset_cpus: CPUs to use
            cpuset_mems: NUMA nodes to use
            mem_limit: Memory limit
            gpu_ids: List of GPU IDs
            mounts: List of Mount objects
            working_dir: Working directory
            privileged: Run in privileged mode
            node: Node hostname

        Returns:
            Container object
        """
        container_name = vps_container_name(task_id)
        labels = make_labels(task_id, "vps", node)

        # Detect package manager and build SSH setup command
        setup_cmd = self._build_ssh_setup_command(image, public_key, task_id)

        kwargs: dict = {
            "labels": labels,
            "ports": {"22/tcp": ssh_port},
            "restart_policy": {"Name": "unless-stopped"},
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
        if privileged:
            kwargs["privileged"] = True
            logger.warning(f"VPS {task_id}: Running with --privileged flag!")
        else:
            kwargs["cap_add"] = ["SYS_NICE"]

        if gpu_ids:
            kwargs["device_requests"] = [
                DeviceRequest(
                    device_ids=[str(gid) for gid in gpu_ids],
                    capabilities=[["gpu"]],
                )
            ]

        logger.debug(f"Creating VPS container {container_name} with image {image}")
        return self.create_container(
            image,
            container_name,
            ["/bin/sh", "-c", setup_cmd],
            **kwargs,
        )

    def _build_ssh_setup_command(
        self,
        image: str,
        public_key: str | None,
        task_id: int,
    ) -> str:
        """Build SSH setup command based on detected package manager."""
        pkg_manager = self._detect_package_manager(image)

        match pkg_manager:
            case "apk":
                install_cmd = "apk update && apk add --no-cache openssh"
            case "apt" | "apt-get":
                install_cmd = (
                    f"{pkg_manager} update && {pkg_manager} install -y openssh-server"
                )
            case "dnf":
                install_cmd = "dnf install -y openssh-server"
            case "yum":
                install_cmd = "yum install -y openssh-server"
            case "zypper":
                install_cmd = "zypper refresh && zypper install -y openssh"
            case "pacman":
                install_cmd = "pacman -Syu --noconfirm openssh"
            case _:
                install_cmd = "echo 'SSH server should be pre-installed'"

        # Build auth configuration
        if public_key:
            # Key-based auth only
            auth_config = (
                "echo 'PasswordAuthentication no' >> /etc/ssh/sshd_config && "
                "echo 'PermitRootLogin prohibit-password' >> /etc/ssh/sshd_config && "
                "mkdir -p /root/.ssh && "
                f"echo '{public_key}' > /root/.ssh/authorized_keys && "
                "chmod 700 /root/.ssh && "
                "chmod 600 /root/.ssh/authorized_keys"
            )
        else:
            # No key - use task_id as password (the snowflake ID is long enough)
            auth_config = (
                "echo 'PasswordAuthentication yes' >> /etc/ssh/sshd_config && "
                "echo 'PermitRootLogin yes' >> /etc/ssh/sshd_config && "
                f"echo 'root:{task_id}' | chpasswd"
            )

        setup_cmd = (
            f"{install_cmd} && "
            "ssh-keygen -A && "
            f"{auth_config} && "
            "mkdir -p /run/sshd && "
            "chmod 0755 /run/sshd && "
            "/usr/sbin/sshd -D -e"
        )

        return setup_cmd

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
                    return manager
            except ContainerError:
                continue
            except Exception:
                continue

        return "unknown"

    def stop_container(self, name: str, timeout: int = 10) -> bool:
        """Stop a container."""
        try:
            container = self.client.containers.get(name)
            container.stop(timeout=timeout)
            logger.info(f"Container {name} stopped")
            return True
        except NotFound:
            logger.warning(f"Container {name} not found")
            return False
        except APIError as e:
            logger.error(f"Failed to stop container {name}: {e}")
            return False

    def start_container(self, name: str) -> bool:
        """Start a stopped container."""
        try:
            container = self.client.containers.get(name)
            container.start()
            logger.info(f"Container {name} started")
            return True
        except NotFound:
            logger.warning(f"Container {name} not found")
            return False
        except APIError as e:
            logger.error(f"Failed to start container {name}: {e}")
            return False

    def remove_container(self, name: str, force: bool = True) -> bool:
        """Remove a container."""
        try:
            container = self.client.containers.get(name)
            container.remove(force=force)
            logger.info(f"Container {name} removed")
            return True
        except NotFound:
            logger.debug(f"Container {name} not found (already removed?)")
            return True
        except APIError as e:
            logger.error(f"Failed to remove container {name}: {e}")
            return False

    def pause_container(self, name: str) -> bool:
        """Pause a container."""
        try:
            container = self.client.containers.get(name)
            container.pause()
            logger.info(f"Container {name} paused")
            return True
        except NotFound:
            raise ContainerNotFoundError(name)
        except APIError as e:
            logger.error(f"Failed to pause container {name}: {e}")
            return False

    def unpause_container(self, name: str) -> bool:
        """Unpause a container."""
        try:
            container = self.client.containers.get(name)
            container.unpause()
            logger.info(f"Container {name} unpaused")
            return True
        except NotFound:
            raise ContainerNotFoundError(name)
        except APIError as e:
            logger.error(f"Failed to unpause container {name}: {e}")
            return False

    def kill_container(self, name: str, signal: str = "SIGKILL") -> bool:
        """Kill a container with a signal."""
        try:
            container = self.client.containers.get(name)
            container.kill(signal=signal)
            logger.info(f"Container {name} killed with {signal}")
            return True
        except NotFound:
            logger.warning(f"Container {name} not found")
            return False
        except APIError as e:
            logger.error(f"Failed to kill container {name}: {e}")
            return False

    def get_container_port(self, name: str, container_port: int = 22) -> int | None:
        """Get host port mapped to a container port."""
        try:
            container = self.client.containers.get(name)
            ports = container.attrs["NetworkSettings"]["Ports"]
            port_key = f"{container_port}/tcp"
            if port_key in ports and ports[port_key]:
                return int(ports[port_key][0]["HostPort"])
            return None
        except NotFound:
            return None
        except (KeyError, IndexError, TypeError):
            return None

    def list_hakuriver_containers(self, all: bool = False) -> list[Container]:
        """List all HakuRiver-managed containers."""
        return self.client.containers.list(
            all=all,
            filters={"label": f"{LABEL_MANAGED}=true"},
        )

    def list_containers(
        self,
        all: bool = False,
        filters: dict | None = None,
    ) -> list[Container]:
        """List containers with optional filters."""
        return self.client.containers.list(all=all, filters=filters)

    def list_images(self) -> list[Image]:
        """List all local images."""
        return self.client.images.list()

    def cleanup_stopped_containers(self) -> int:
        """Remove stopped HakuRiver containers. Returns count of removed."""
        removed = 0
        for container in self.list_hakuriver_containers(all=True):
            if container.status in ("exited", "dead"):
                try:
                    container.remove()
                    removed += 1
                    logger.info(f"Removed stopped container {container.name}")
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
        """Get an image by tag."""
        try:
            return self.client.images.get(tag)
        except ImageNotFound:
            raise ImageNotFoundError(tag)

    def pull_image(self, tag: str) -> Image:
        """Pull an image from registry."""
        logger.info(f"Pulling image {tag}...")
        return self.client.images.pull(tag)

    def commit_container(
        self,
        container_name: str,
        repository: str,
        tag: str = "base",
    ) -> Image:
        """Commit a container to an image."""
        try:
            container = self.client.containers.get(container_name)
            image = container.commit(repository=repository, tag=tag)
            logger.info(f"Committed container {container_name} to {repository}:{tag}")
            return image
        except NotFound:
            raise ContainerNotFoundError(container_name)
        except APIError as e:
            raise ImageBuildError(str(e), f"{repository}:{tag}") from e

    def save_image(self, tag: str, output_path: str) -> None:
        """Save an image to a tarball."""
        try:
            image = self.client.images.get(tag)
            logger.info(f"Saving image {tag} to {output_path}...")

            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "wb") as f:
                for chunk in image.save():
                    f.write(chunk)

            logger.info(f"Image saved to {output_path}")
        except ImageNotFound:
            raise ImageNotFoundError(tag)
        except Exception as e:
            raise ImageExportError(str(e), tag) from e

    def load_image(self, tarball_path: str) -> list[Image]:
        """Load an image from a tarball."""
        if not os.path.exists(tarball_path):
            raise ImageImportError(f"Tarball not found: {tarball_path}", tarball_path)

        try:
            logger.info(f"Loading image from {tarball_path}...")
            with open(tarball_path, "rb") as f:
                images = self.client.images.load(f)
            logger.info(f"Loaded {len(images)} image(s) from {tarball_path}")
            return images
        except Exception as e:
            raise ImageImportError(str(e), tarball_path) from e

    def get_image_created_timestamp(self, tag: str) -> int | None:
        """Get the creation timestamp of an image."""
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
            logger.error(f"Error getting image timestamp for {tag}: {e}")
            return None

    def remove_image(self, tag: str, force: bool = False) -> bool:
        """Remove an image."""
        try:
            self.client.images.remove(tag, force=force)
            logger.info(f"Removed image {tag}")
            return True
        except ImageNotFound:
            return True
        except APIError as e:
            logger.error(f"Failed to remove image {tag}: {e}")
            return False

    def prune_dangling_images(self) -> int:
        """Remove dangling images. Returns bytes reclaimed."""
        result = self.client.images.prune(filters={"dangling": True})
        space_reclaimed = result.get("SpaceReclaimed", 0)
        logger.info(f"Pruned dangling images, reclaimed {space_reclaimed} bytes")
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

        Returns:
            List of (timestamp, path) tuples, sorted newest first
        """
        pattern = re.compile(rf"^{re.escape(container_name.lower())}-(\d+)\.tar$")
        tar_files = []

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

        Returns:
            (needs_sync, path_to_latest_tar)
        """
        hakuriver_tag = image_tag(container_name, "base")
        local_timestamp = self.get_image_created_timestamp(hakuriver_tag)
        shared_tars = self.list_shared_tarballs(container_tar_dir, container_name)

        if not shared_tars:
            return False, None

        latest_timestamp, latest_path = shared_tars[0]

        if local_timestamp is None:
            logger.info(f"Local image for {container_name} not found, sync needed")
            return True, latest_path
        elif latest_timestamp > local_timestamp:
            logger.info(
                f"Newer tarball found for {container_name} "
                f"(shared: {latest_timestamp}, local: {local_timestamp})"
            )
            return True, latest_path
        else:
            logger.debug(f"Local image for {container_name} is up-to-date")
            return False, None

    def sync_from_shared(self, container_name: str, tarball_path: str) -> bool:
        """Sync (load) an image from shared storage."""
        try:
            self.load_image(tarball_path)
            return True
        except ImageImportError as e:
            logger.error(f"Failed to sync {container_name}: {e}")
            return False

    def create_container_tarball(
        self,
        source_container: str,
        hakuriver_name: str,
        container_tar_dir: str,
    ) -> str | None:
        """
        Create a HakuRiver container tarball from an existing container.

        Args:
            source_container: Name of existing container to commit
            hakuriver_name: HakuRiver environment name
            container_tar_dir: Directory to store tarball

        Returns:
            Path to created tarball, or None on failure
        """
        hakuriver_tag = image_tag(hakuriver_name, "base")
        timestamp = int(time.time())
        tarball_filename = f"{hakuriver_name}-{timestamp}.tar"
        tarball_path = os.path.join(container_tar_dir, tarball_filename)

        try:
            # Stop container for consistency
            self.stop_container(source_container)

            # Commit container to image
            self.commit_container(
                source_container, f"hakuriver/{hakuriver_name}", "base"
            )

            # Save to tarball
            self.save_image(hakuriver_tag, tarball_path)

            # Clean up old tarballs
            for old_ts, old_path in self.list_shared_tarballs(
                container_tar_dir, hakuriver_name
            ):
                if old_ts < timestamp:
                    try:
                        os.remove(old_path)
                        logger.info(f"Removed old tarball: {old_path}")
                    except OSError as e:
                        logger.warning(f"Failed to remove old tarball {old_path}: {e}")

            # Prune dangling images
            self.prune_dangling_images()

            logger.info(f"Created container tarball at {tarball_path}")
            return tarball_path

        except Exception as e:
            logger.exception(f"Failed to create container tarball: {e}")
            # Cleanup on failure
            self.remove_image(hakuriver_tag, force=True)
            return None


# Global instance (lazy initialization)
_docker_manager: DockerManager | None = None


def get_docker_manager() -> DockerManager:
    """Get the global DockerManager instance."""
    global _docker_manager
    if _docker_manager is None:
        _docker_manager = DockerManager()
    return _docker_manager
