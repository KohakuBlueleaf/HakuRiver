"""
VPS management service.

Handles VPS container creation and lifecycle management.
Uses subprocess-based Docker execution (matching old behavior).
"""

import asyncio
import datetime
import logging
import subprocess

from kohakuriver.docker.naming import image_tag, vps_container_name
from kohakuriver.models.requests import TaskStatusUpdate
from kohakuriver.runner.config import config
from kohakuriver.runner.services.task_executor import (
    ensure_docker_image_synced,
    report_status_to_host,
)
from kohakuriver.storage.vault import TaskStateStore
from kohakuriver.utils.logger import format_traceback

logger = logging.getLogger(__name__)


def _detect_package_manager(image_name: str) -> str:
    """Detect package manager from Docker image name."""
    image_lower = image_name.lower()

    if any(x in image_lower for x in ["alpine"]):
        return "apk"
    elif any(x in image_lower for x in ["ubuntu", "debian"]):
        return "apt"
    elif any(x in image_lower for x in ["fedora"]):
        return "dnf"
    elif any(x in image_lower for x in ["centos", "rhel", "redhat", "rocky", "alma"]):
        return "yum"
    elif any(x in image_lower for x in ["opensuse", "suse"]):
        return "zypper"
    elif any(x in image_lower for x in ["arch"]):
        return "pacman"
    else:
        # Default to apt for common images
        return "apt"


def _get_ssh_install_cmd(pkg_manager: str) -> str:
    """Get the SSH installation command for a package manager."""
    match pkg_manager:
        case "apk":
            return "apk update && apk add --no-cache openssh"
        case "apt":
            return "apt update && apt install -y openssh-server"
        case "dnf":
            return "dnf install -y openssh-server"
        case "yum":
            return "yum install -y openssh-server"
        case "zypper":
            return "zypper refresh && zypper install -y openssh"
        case "pacman":
            return "pacman -Syu --noconfirm openssh"
        case _:
            return "apt update && apt install -y openssh-server"


def _build_vps_docker_command(
    docker_image_tag: str,
    task_id: int,
    ssh_key_mode: str,
    ssh_public_key: str | None,
    mount_dirs: list[str],
    working_dir: str,
    cpu_cores: int,
    memory_limit_bytes: int | None,
    gpu_ids: list[int],
    privileged: bool,
) -> list[str]:
    """
    Build docker run command for VPS container.

    Args:
        docker_image_tag: Docker image tag to use.
        task_id: Task ID for the VPS.
        ssh_key_mode: SSH key mode ("none", "upload", or "generate").
        ssh_public_key: SSH public key (None for "none" mode).
        mount_dirs: List of mount directories.
        working_dir: Working directory in container.
        cpu_cores: Number of CPU cores.
        memory_limit_bytes: Memory limit in bytes.
        gpu_ids: List of GPU indices.
        privileged: Run with --privileged.

    Returns:
        Docker command as list of strings.
    """
    docker_cmd = ["docker", "run", "--restart", "unless-stopped", "-d"]

    # Container name
    docker_cmd.extend(["--name", vps_container_name(task_id)])

    # SSH port mapping - only if SSH is enabled
    if ssh_key_mode != "disabled":
        docker_cmd.extend(["-p", "0:22"])

    # Privileged mode or CAP_SYS_NICE
    if privileged:
        docker_cmd.append("--privileged")
        logger.warning(f"VPS {task_id}: Running with --privileged flag!")
    else:
        docker_cmd.extend(["--cap-add", "SYS_NICE"])

    # Mount directories
    for mount_spec in mount_dirs:
        parts = mount_spec.split(":")
        if len(parts) < 2:
            logger.warning(f"Invalid mount format: '{mount_spec}'. Skipping.")
            continue
        host_path, container_path, *options = parts
        option_str = ("," + ",".join(options)) if options else ""
        docker_cmd.extend(
            [
                "--mount",
                f"type=bind,source={host_path},target={container_path}{option_str}",
            ]
        )

    # Working directory
    if working_dir:
        docker_cmd.extend(["--workdir", working_dir])

    # CPU cores
    if cpu_cores > 0:
        docker_cmd.extend(["--cpus", str(cpu_cores)])

    # Memory limit
    if memory_limit_bytes:
        docker_cmd.extend(["--memory", str(memory_limit_bytes)])

    # GPU allocation
    if gpu_ids:
        id_string = ",".join(map(str, gpu_ids))
        docker_cmd.extend(["--gpus", f'"device={id_string}"'])

    # Build setup command based on SSH key mode
    match ssh_key_mode:
        case "disabled":
            # No SSH at all - just run a shell that stays alive (TTY-only mode)
            # Use tail -f /dev/null to keep container running, users connect via docker exec
            setup_cmd = "tail -f /dev/null"
            logger.info(f"VPS {task_id}: Configured for TTY-only mode (no SSH)")

        case "none":
            # No SSH key mode - enable password-less root login
            pkg_manager = _detect_package_manager(docker_image_tag)
            setup_cmd = _get_ssh_install_cmd(pkg_manager)
            setup_cmd += " && ssh-keygen -A && "
            setup_cmd += (
                "echo 'PasswordAuthentication yes' >> /etc/ssh/sshd_config && "
                "echo 'PermitRootLogin yes' >> /etc/ssh/sshd_config && "
                "echo 'PermitEmptyPasswords yes' >> /etc/ssh/sshd_config && "
                "passwd -d root && "
                "mkdir -p /run/sshd && "
                "chmod 0755 /run/sshd && "
                "/usr/sbin/sshd -D -e"
            )
            logger.info(
                f"VPS {task_id}: Configured for passwordless root login (no SSH key)"
            )

        case "upload" | "generate":
            # SSH key mode - standard pubkey auth
            if not ssh_public_key:
                raise ValueError(f"ssh_public_key required for mode '{ssh_key_mode}'")

            pkg_manager = _detect_package_manager(docker_image_tag)
            setup_cmd = _get_ssh_install_cmd(pkg_manager)
            setup_cmd += " && ssh-keygen -A && "
            setup_cmd += (
                "echo 'PasswordAuthentication no' >> /etc/ssh/sshd_config && "
                "echo 'PermitRootLogin yes' >> /etc/ssh/sshd_config && "
                "mkdir -p /run/sshd && "
                "chmod 0755 /run/sshd && "
                "mkdir -p /root/.ssh && "
                f"echo '{ssh_public_key}' > /root/.ssh/authorized_keys && "
                "chmod 700 /root/.ssh && "
                "chmod 600 /root/.ssh/authorized_keys && "
                "/usr/sbin/sshd -D -e"
            )
            logger.info(f"VPS {task_id}: Configured with SSH public key authentication")

        case _:
            raise ValueError(f"Invalid ssh_key_mode: {ssh_key_mode}")

    # Add image and command
    docker_cmd.append(docker_image_tag)
    docker_cmd.extend(["/bin/sh", "-c", setup_cmd])

    logger.debug(f"VPS {task_id} docker command: {' '.join(docker_cmd)}")
    return docker_cmd


async def _find_ssh_port(
    container_name: str, retries: int = 5, delay: float = 0.5
) -> int:
    """
    Find the mapped SSH port for a container.

    Args:
        container_name: Docker container name.
        retries: Number of retry attempts.
        delay: Delay between retries in seconds.

    Returns:
        SSH port number, or 0 if not found (VPS will still work via TTY).
    """
    for attempt in range(retries):
        try:
            result = subprocess.run(
                ["docker", "port", container_name, "22"],
                capture_output=True,
                text=True,
                check=True,
            )
            # Parse: "0.0.0.0:32792\n[::]:32792\n"
            port_mapping = result.stdout.splitlines()[0].strip()
            port = int(port_mapping.split(":")[1])
            logger.debug(
                f"Found SSH port {port} for container '{container_name}' on attempt {attempt + 1}"
            )
            return port
        except subprocess.CalledProcessError:
            if attempt < retries - 1:
                logger.debug(
                    f"SSH port not ready for '{container_name}', retrying ({attempt + 1}/{retries})..."
                )
                await asyncio.sleep(delay)
            else:
                logger.warning(
                    f"Failed to find SSH port for container '{container_name}' after {retries} attempts. VPS will work via TTY only."
                )
                return 0
        except (IndexError, ValueError) as e:
            if attempt < retries - 1:
                logger.debug(
                    f"Failed to parse SSH port: {e}, retrying ({attempt + 1}/{retries})..."
                )
                await asyncio.sleep(delay)
            else:
                logger.warning(
                    f"Failed to parse SSH port for '{container_name}': {e}. VPS will work via TTY only."
                )
                return 0
    return 0


async def create_vps(
    task_id: int,
    required_cores: int,
    required_gpus: list[int],
    required_memory_bytes: int | None,
    target_numa_node_id: int | None,
    container_name: str,
    ssh_key_mode: str,
    ssh_public_key: str | None,
    ssh_port: int,
    task_store: TaskStateStore,
) -> dict:
    """
    Create a VPS container with SSH access using subprocess.

    Args:
        task_id: Task ID for this VPS.
        required_cores: Number of cores to allocate.
        required_gpus: List of GPU indices to allocate.
        required_memory_bytes: Memory limit in bytes.
        target_numa_node_id: Target NUMA node ID.
        container_name: Base container image name.
        ssh_key_mode: SSH key mode ("none", "upload", or "generate").
        ssh_public_key: SSH public key for access (None for "none" mode).
        ssh_port: SSH port to expose.
        task_store: Task state store.

    Returns:
        Dictionary with VPS creation result.
    """
    start_time = datetime.datetime.now()

    # Report pending status
    await report_status_to_host(
        TaskStatusUpdate(
            task_id=task_id,
            status="pending",
        )
    )

    # =========================================================================
    # Step 1: Ensure Docker image is synced from shared storage
    # =========================================================================
    logger.info(
        f"VPS {task_id}: Checking Docker image sync status for '{container_name}'"
    )

    if not await ensure_docker_image_synced(task_id, container_name):
        error_message = f"Docker image sync failed for container '{container_name}'"
        logger.error(f"VPS {task_id}: {error_message}")
        await report_status_to_host(
            TaskStatusUpdate(
                task_id=task_id,
                status="failed",
                message=error_message,
                completed_at=datetime.datetime.now(),
            )
        )
        return {
            "success": False,
            "error": error_message,
        }

    # =========================================================================
    # Step 2: Build mount directories
    # shared_data subdirectory is mounted as /shared inside container
    # =========================================================================
    mount_dirs = [
        f"{config.SHARED_DIR}/shared_data:/shared",
        f"{config.LOCAL_TEMP_DIR}:/local_temp",
    ]
    mount_dirs.extend(config.ADDITIONAL_MOUNTS)

    # Get the full Docker image tag
    docker_image_tag = image_tag(container_name)

    # =========================================================================
    # Step 3: Build and execute docker run command
    # (SSH port is assigned by Docker automatically, we query it after creation)
    # =========================================================================
    docker_cmd = _build_vps_docker_command(
        docker_image_tag=docker_image_tag,
        task_id=task_id,
        ssh_key_mode=ssh_key_mode,
        ssh_public_key=ssh_public_key,
        mount_dirs=mount_dirs,
        working_dir="/shared",
        cpu_cores=required_cores,
        memory_limit_bytes=required_memory_bytes,
        gpu_ids=required_gpus or [],
        privileged=config.TASKS_PRIVILEGED,
    )

    try:
        # Run docker command via subprocess
        process = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        exit_code = process.returncode

        logger.debug(
            f"VPS {task_id} docker run exit code: {exit_code}: "
            f"{stdout.decode(errors='replace').strip()} | "
            f"{stderr.decode(errors='replace').strip()}"
        )

        if exit_code != 0:
            error_message = (
                f"Docker run failed: {stderr.decode(errors='replace').strip()}"
            )
            logger.error(f"VPS {task_id}: {error_message}")
            await report_status_to_host(
                TaskStatusUpdate(
                    task_id=task_id,
                    status="failed",
                    message=error_message,
                    exit_code=exit_code,
                    completed_at=datetime.datetime.now(),
                )
            )
            return {
                "success": False,
                "error": error_message,
            }

        # Find the actual SSH port (only if SSH is enabled)
        container_name_full = vps_container_name(task_id)

        if ssh_key_mode == "disabled":
            # No SSH - TTY-only mode
            actual_ssh_port = 0
            logger.info(f"VPS {task_id}: TTY-only mode, no SSH port")
        else:
            # Find SSH port - returns 0 if not found
            actual_ssh_port = await _find_ssh_port(container_name_full)
            if actual_ssh_port == 0:
                logger.warning(
                    f"VPS {task_id}: SSH port not available, but VPS is running. "
                    "TTY terminal access will still work."
                )

        # Store VPS state
        task_store.add_task(
            task_id=task_id,
            container_name=container_name_full,
            allocated_cores=required_cores,
            allocated_gpus=required_gpus,
            numa_node=target_numa_node_id,
        )

        # Report running status with SSH port
        await report_status_to_host(
            TaskStatusUpdate(
                task_id=task_id,
                status="running",
                started_at=start_time,
                ssh_port=actual_ssh_port,
            )
        )

        logger.info(
            f"VPS {task_id} started in container {container_name_full}, SSH port: {actual_ssh_port}"
        )

        return {
            "success": True,
            "ssh_port": actual_ssh_port,
            "container_name": container_name_full,
        }

    except Exception as e:
        error_message = f"VPS creation failed: {e}"
        logger.error(error_message)
        logger.debug(format_traceback(e))

        # Report failure
        await report_status_to_host(
            TaskStatusUpdate(
                task_id=task_id,
                status="failed",
                message=error_message,
                completed_at=datetime.datetime.now(),
            )
        )

        return {
            "success": False,
            "error": error_message,
        }


def stop_vps(
    task_id: int,
    task_store: TaskStateStore,
) -> bool:
    """
    Stop a running VPS.

    Args:
        task_id: VPS task ID to stop.
        task_store: Task state store.

    Returns:
        True if stop was successful, False otherwise.
    """
    container_name = vps_container_name(task_id)

    try:
        # Stop the container
        subprocess.run(
            ["docker", "stop", container_name],
            check=True,
            capture_output=True,
            timeout=60,
        )

        # Remove the container
        subprocess.run(
            ["docker", "rm", container_name],
            check=True,
            capture_output=True,
            timeout=60,
        )

        # Remove from tracking
        task_store.remove_task(task_id)

        logger.info(f"Stopped VPS {task_id}")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(
            f"Failed to stop VPS {task_id}: {e.stderr.decode() if e.stderr else e}"
        )
        return False
    except Exception as e:
        logger.error(f"Failed to stop VPS {task_id}: {e}")
        return False


def pause_vps(
    task_id: int,
    task_store: TaskStateStore,
) -> bool:
    """
    Pause a running VPS.

    Args:
        task_id: VPS task ID to pause.
        task_store: Task state store.

    Returns:
        True if pause was successful, False otherwise.
    """
    container_name = vps_container_name(task_id)

    try:
        subprocess.run(
            ["docker", "pause", container_name],
            check=True,
            capture_output=True,
            timeout=10,
        )
        logger.info(f"Paused VPS {task_id}")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(
            f"Failed to pause VPS {task_id}: {e.stderr.decode() if e.stderr else e}"
        )
        return False
    except Exception as e:
        logger.error(f"Failed to pause VPS {task_id}: {e}")
        return False


def resume_vps(
    task_id: int,
    task_store: TaskStateStore,
) -> bool:
    """
    Resume a paused VPS.

    Args:
        task_id: VPS task ID to resume.
        task_store: Task state store.

    Returns:
        True if resume was successful, False otherwise.
    """
    container_name = vps_container_name(task_id)

    try:
        subprocess.run(
            ["docker", "unpause", container_name],
            check=True,
            capture_output=True,
            timeout=10,
        )
        logger.info(f"Resumed VPS {task_id}")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(
            f"Failed to resume VPS {task_id}: {e.stderr.decode() if e.stderr else e}"
        )
        return False
    except Exception as e:
        logger.error(f"Failed to resume VPS {task_id}: {e}")
        return False
