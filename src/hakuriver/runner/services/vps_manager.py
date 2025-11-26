"""
VPS management service.

Handles VPS container creation and lifecycle management.
Uses subprocess-based Docker execution (matching old behavior).
"""
import asyncio
import datetime
import logging
import subprocess

from hakuriver.docker.naming import image_tag, vps_container_name
from hakuriver.models.requests import TaskStatusUpdate
from hakuriver.runner.config import config
from hakuriver.runner.services.task_executor import (
    ensure_docker_image_synced,
    report_status_to_host,
)
from hakuriver.storage.vault import TaskStateStore
from hakuriver.utils.logger import format_traceback

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


def _build_vps_docker_command(
    docker_image_tag: str,
    task_id: int,
    ssh_public_key: str,
    mount_dirs: list[str],
    working_dir: str,
    cpu_cores: int,
    memory_limit_bytes: int | None,
    gpu_ids: list[int],
    privileged: bool,
) -> list[str]:
    """
    Build docker run command for VPS container.

    Matches old vps_command_for_docker behavior.
    Uses -p 0:22 to let Docker assign a random host port.
    """
    docker_cmd = ["docker", "run", "--restart", "unless-stopped", "-d"]

    # Container name
    docker_cmd.extend(["--name", vps_container_name(task_id)])

    # SSH port mapping - use 0 to let Docker assign random port
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
        docker_cmd.extend([
            "--mount",
            f"type=bind,source={host_path},target={container_path}{option_str}",
        ])

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

    # Detect package manager and build SSH setup command
    pkg_manager = _detect_package_manager(docker_image_tag)

    match pkg_manager:
        case "apk":
            setup_cmd = "apk update && apk add --no-cache openssh"
        case "apt":
            setup_cmd = "apt update && apt install -y openssh-server"
        case "dnf":
            setup_cmd = "dnf install -y openssh-server"
        case "yum":
            setup_cmd = "yum install -y openssh-server"
        case "zypper":
            setup_cmd = "zypper refresh && zypper install -y openssh"
        case "pacman":
            setup_cmd = "pacman -Syu --noconfirm openssh"
        case _:
            setup_cmd = "apt update && apt install -y openssh-server"

    # SSH setup and start
    setup_cmd += (
        " && "
        "ssh-keygen -A && "
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

    # Add image and command
    docker_cmd.append(docker_image_tag)
    docker_cmd.extend(["/bin/sh", "-c", setup_cmd])

    logger.debug(f"VPS {task_id} docker command: {' '.join(docker_cmd)}")
    return docker_cmd


def _find_ssh_port(container_name: str) -> int | None:
    """Find the mapped SSH port for a container."""
    try:
        result = subprocess.run(
            ["docker", "port", container_name, "22"],
            capture_output=True,
            text=True,
            check=True,
        )
        # Parse: "0.0.0.0:32792\n[::]:32792\n"
        port_mapping = result.stdout.splitlines()[0].strip()
        return int(port_mapping.split(":")[1])
    except subprocess.CalledProcessError:
        logger.error(f"Failed to find SSH port for container '{container_name}'")
        return None
    except (IndexError, ValueError) as e:
        logger.error(f"Failed to parse SSH port: {e}")
        return None


async def create_vps(
    task_id: int,
    required_cores: int,
    required_gpus: list[int],
    required_memory_bytes: int | None,
    target_numa_node_id: int | None,
    container_name: str,
    ssh_public_key: str,
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
        ssh_public_key: SSH public key for access.
        ssh_port: SSH port to expose.
        task_store: Task state store.

    Returns:
        Dictionary with VPS creation result.
    """
    start_time = datetime.datetime.now()

    # Report pending status
    await report_status_to_host(TaskStatusUpdate(
        task_id=task_id,
        status="pending",
    ))

    # =========================================================================
    # Step 1: Ensure Docker image is synced from shared storage
    # =========================================================================
    logger.info(f"VPS {task_id}: Checking Docker image sync status for '{container_name}'")

    if not await ensure_docker_image_synced(task_id, container_name):
        error_message = f"Docker image sync failed for container '{container_name}'"
        logger.error(f"VPS {task_id}: {error_message}")
        await report_status_to_host(TaskStatusUpdate(
            task_id=task_id,
            status="failed",
            message=error_message,
            completed_at=datetime.datetime.now(),
        ))
        return {
            "success": False,
            "error": error_message,
        }

    # =========================================================================
    # Step 2: Build mount directories
    # =========================================================================
    mount_dirs = [
        f"{config.SHARED_DIR}:/shared",
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
            error_message = f"Docker run failed: {stderr.decode(errors='replace').strip()}"
            logger.error(f"VPS {task_id}: {error_message}")
            await report_status_to_host(TaskStatusUpdate(
                task_id=task_id,
                status="failed",
                message=error_message,
                exit_code=exit_code,
                completed_at=datetime.datetime.now(),
            ))
            return {
                "success": False,
                "error": error_message,
            }

        # Find the actual SSH port (might differ if 0 was requested)
        container_name_full = vps_container_name(task_id)
        actual_ssh_port = _find_ssh_port(container_name_full)

        if not actual_ssh_port:
            error_message = "Failed to find SSH port after container started"
            logger.error(f"VPS {task_id}: {error_message}")
            await report_status_to_host(TaskStatusUpdate(
                task_id=task_id,
                status="failed",
                message=error_message,
                completed_at=datetime.datetime.now(),
            ))
            return {
                "success": False,
                "error": error_message,
            }

        # Store VPS state
        task_store.add_task(
            task_id=task_id,
            container_name=container_name_full,
            allocated_cores=required_cores,
            allocated_gpus=required_gpus,
            numa_node=target_numa_node_id,
        )

        # Report running status with SSH port
        await report_status_to_host(TaskStatusUpdate(
            task_id=task_id,
            status="running",
            started_at=start_time,
            ssh_port=actual_ssh_port,
        ))

        logger.info(f"VPS {task_id} started in container {container_name_full}, SSH port: {actual_ssh_port}")

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
        await report_status_to_host(TaskStatusUpdate(
            task_id=task_id,
            status="failed",
            message=error_message,
            completed_at=datetime.datetime.now(),
        ))

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
        logger.error(f"Failed to stop VPS {task_id}: {e.stderr.decode() if e.stderr else e}")
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
        logger.error(f"Failed to pause VPS {task_id}: {e.stderr.decode() if e.stderr else e}")
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
        logger.error(f"Failed to resume VPS {task_id}: {e.stderr.decode() if e.stderr else e}")
        return False
    except Exception as e:
        logger.error(f"Failed to resume VPS {task_id}: {e}")
        return False
