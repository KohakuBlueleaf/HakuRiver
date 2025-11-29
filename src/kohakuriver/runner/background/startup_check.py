"""
Startup check background task.

Verifies running containers on startup and reports status.
Handles VPS port recovery after runner restart.

All Docker operations are wrapped in asyncio.to_thread to prevent blocking.
"""

import asyncio
import datetime
import subprocess

from kohakuriver.docker.client import DockerManager
from kohakuriver.docker.naming import (
    VPS_PREFIX,
    extract_task_id_from_name,
    is_kohakuriver_container,
)
from kohakuriver.models.requests import TaskStatusUpdate
from kohakuriver.runner.services.task_executor import report_status_to_host
from kohakuriver.storage.vault import TaskStateStore
from kohakuriver.utils.logger import get_logger

logger = get_logger(__name__)


def _find_ssh_port(container_name: str) -> int:
    """
    Find the mapped SSH port for a container.

    Returns:
        SSH port number, or 0 if not found (VPS will still work via TTY).
    """
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
        logger.warning(
            f"SSH port not available for container '{container_name}'. VPS will work via TTY only."
        )
        return 0
    except (IndexError, ValueError) as e:
        logger.warning(
            f"Failed to parse SSH port for '{container_name}': {e}. VPS will work via TTY only."
        )
        return 0


def _get_running_containers() -> tuple[list, set[str]]:
    """Get running containers (blocking, run in executor)."""
    docker_manager = DockerManager()
    all_running = docker_manager.list_containers(all=False)
    running_container_names = {
        c.name for c in all_running if is_kohakuriver_container(c.name)
    }
    return all_running, running_container_names


def _stop_and_remove_container(container_name: str, timeout: int = 10):
    """Stop and remove container (blocking, run in executor)."""
    docker_manager = DockerManager()
    docker_manager.stop_container(container_name, timeout=timeout)
    docker_manager.remove_container(container_name)


async def startup_check(task_store: TaskStateStore):
    """
    Check all running containers on startup and reconcile state.

    This function:
    1. Gets all tracked tasks from the store
    2. Checks if their containers are still running
    3. Reports stopped status for missing containers
    4. For VPS containers still running, recovers SSH port binding
    5. Updates store for containers that are still running
    """
    # Get all running containers in executor
    all_running, running_container_names = await asyncio.to_thread(
        _get_running_containers
    )

    # Check tracked tasks
    tracked_tasks = list(task_store.items())  # Copy to avoid mutation during iteration

    for task_id_str, task_data in tracked_tasks:
        task_id = int(task_id_str)
        container_name = task_data.get("container_name")

        if container_name not in running_container_names:
            # Container is not running - report as "stopped"
            logger.warning(
                f"Container {container_name} for task {task_id} not found. "
                "Reporting as stopped."
            )

            await report_status_to_host(
                TaskStatusUpdate(
                    task_id=task_id,
                    status="stopped",
                    exit_code=-1,
                    message="Container not found on runner startup (runner may have restarted).",
                    completed_at=datetime.datetime.now(),
                )
            )

            task_store.remove_task(task_id)

        else:
            # Container is still running
            # For VPS containers, recover the SSH port and report to host
            if container_name.startswith(VPS_PREFIX):
                ssh_port = _find_ssh_port(container_name)
                if ssh_port > 0:
                    logger.info(
                        f"VPS container {container_name} for task {task_id} recovered, "
                        f"SSH port: {ssh_port}"
                    )
                else:
                    # VPS without SSH port - still usable via TTY
                    logger.warning(
                        f"VPS container {container_name} for task {task_id} has no SSH port. "
                        "VPS will work via TTY only."
                    )

                # Report running status to host (host may have marked as "lost" during downtime)
                recovery_message = f"VPS recovered after runner restart" + (
                    "" if ssh_port > 0 else " (TTY-only, no SSH)"
                )
                logger.info(
                    f"[VPS Recovery] Reporting tracked VPS {task_id} as 'running' to host. "
                    f"Message: {recovery_message}"
                )
                await report_status_to_host(
                    TaskStatusUpdate(
                        task_id=task_id,
                        status="running",
                        message=recovery_message,
                        ssh_port=ssh_port if ssh_port > 0 else None,
                    )
                )
                logger.info(
                    f"[VPS Recovery] Successfully reported tracked VPS {task_id} recovery to host."
                )

            logger.info(
                f"Container {container_name} for task {task_id} is still running."
            )

    # Check for orphan HakuRiver containers (running but not tracked)
    # For VPS containers, try to recover them; for task containers, clean them up
    for container in all_running:
        # Check name matches HakuRiver pattern
        if not is_kohakuriver_container(container.name):
            continue

        # Extract task ID from container name
        task_id = extract_task_id_from_name(container.name)
        if task_id is None:
            logger.warning(
                f"Could not extract task ID from container name: {container.name}. "
                "Skipping."
            )
            continue

        # Check if tracked in our store
        task_data = task_store.get_task(task_id)
        if task_data is None:
            # Orphan container - check if it's a VPS
            if container.name.startswith(VPS_PREFIX):
                # Try to recover VPS - it can work without SSH port via TTY
                ssh_port = _find_ssh_port(container.name)
                if ssh_port > 0:
                    logger.info(
                        f"Recovering orphan VPS container {container.name} "
                        f"(task_id={task_id}), SSH port: {ssh_port}"
                    )
                else:
                    logger.info(
                        f"Recovering orphan VPS container {container.name} "
                        f"(task_id={task_id}), no SSH port (TTY-only mode)"
                    )

                # Add back to tracking (works with or without SSH)
                task_store.add_task(
                    task_id=task_id,
                    container_name=container.name,
                    allocated_cores=None,
                    allocated_gpus=None,
                    numa_node=None,
                )
                logger.debug(
                    f"[VPS Recovery] Added VPS {task_id} back to local task store."
                )

                # Report running status to host with SSH port (0 means no SSH)
                recovery_message = f"VPS recovered after runner restart" + (
                    "" if ssh_port > 0 else " (TTY-only, no SSH)"
                )
                logger.info(
                    f"[VPS Recovery] Reporting VPS {task_id} as 'running' to host. "
                    f"Message: {recovery_message}"
                )
                await report_status_to_host(
                    TaskStatusUpdate(
                        task_id=task_id,
                        status="running",
                        message=recovery_message,
                        ssh_port=ssh_port if ssh_port > 0 else None,
                    )
                )
                logger.info(
                    f"[VPS Recovery] Successfully reported VPS {task_id} recovery to host."
                )
            else:
                # Regular task container - clean up
                logger.warning(
                    f"Found orphan task container {container.name} (task_id={task_id}). "
                    "Stopping and removing."
                )
                try:
                    await asyncio.to_thread(
                        _stop_and_remove_container, container.name, 10
                    )
                    logger.info(
                        f"Successfully cleaned up orphan container {container.name}"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to cleanup orphan container {container.name}: {e}"
                    )
