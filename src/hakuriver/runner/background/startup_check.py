"""
Startup check background task.

Verifies running containers on startup and reports status.
Handles VPS port recovery after runner restart.
"""

import datetime
import logging
import subprocess

from hakuriver.docker.client import DockerManager
from hakuriver.docker.naming import (
    LABEL_MANAGED,
    TASK_PREFIX,
    VPS_PREFIX,
    is_hakuriver_container,
    extract_task_id_from_name,
)
from hakuriver.models.requests import TaskStatusUpdate
from hakuriver.runner.services.task_executor import report_status_to_host
from hakuriver.storage.vault import TaskStateStore

logger = logging.getLogger(__name__)


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
    docker_manager = DockerManager()

    # Get all running HakuRiver containers
    running_containers = docker_manager.list_containers(
        all=False,  # Only running
        filters={"label": LABEL_MANAGED},
    )

    running_container_names = {c.name for c in running_containers}

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
            # For VPS containers, recover the SSH port
            if container_name.startswith(VPS_PREFIX):
                ssh_port = _find_ssh_port(container_name)
                if ssh_port:
                    logger.info(
                        f"VPS container {container_name} for task {task_id} recovered, "
                        f"SSH port: {ssh_port}"
                    )
                    # Port might have changed after restart, update in store
                    # (The store doesn't track SSH port, but we log it for monitoring)
                else:
                    # VPS without SSH port is broken - stop it
                    logger.error(
                        f"VPS container {container_name} for task {task_id} has no SSH port. "
                        "Stopping container."
                    )
                    try:
                        subprocess.run(
                            ["docker", "stop", container_name],
                            check=True,
                            capture_output=True,
                            timeout=60,
                        )
                        subprocess.run(
                            ["docker", "rm", container_name],
                            check=True,
                            capture_output=True,
                            timeout=60,
                        )
                    except Exception as e:
                        logger.error(f"Failed to stop broken VPS container: {e}")

                    await report_status_to_host(
                        TaskStatusUpdate(
                            task_id=task_id,
                            status="stopped",
                            exit_code=-1,
                            message="VPS lost SSH port binding after restart.",
                            completed_at=datetime.datetime.now(),
                        )
                    )

                    task_store.remove_task(task_id)
                    continue

            logger.info(
                f"Container {container_name} for task {task_id} is still running."
            )

    # Check for orphan HakuRiver containers (running but not tracked)
    # For VPS containers, try to recover them; for task containers, clean them up
    for container in running_containers:
        # Check name matches HakuRiver pattern
        if not is_hakuriver_container(container.name):
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
                # Try to recover VPS
                ssh_port = _find_ssh_port(container.name)
                if ssh_port:
                    logger.info(
                        f"Recovering orphan VPS container {container.name} "
                        f"(task_id={task_id}), SSH port: {ssh_port}"
                    )
                    # Add back to tracking
                    task_store.add_task(
                        task_id=task_id,
                        container_name=container.name,
                        allocated_cores=None,
                        allocated_gpus=None,
                        numa_node=None,
                    )
                    # Report running status to host with SSH port
                    await report_status_to_host(
                        TaskStatusUpdate(
                            task_id=task_id,
                            status="running",
                            message=f"VPS recovered after runner restart",
                            ssh_port=ssh_port,
                        )
                    )
                else:
                    # VPS without SSH port - clean up
                    logger.warning(
                        f"Orphan VPS container {container.name} has no SSH port. "
                        "Cleaning up."
                    )
                    try:
                        docker_manager.stop_container(container.name, timeout=10)
                        docker_manager.remove_container(container.name)
                        logger.info(
                            f"Successfully cleaned up broken VPS {container.name}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to cleanup broken VPS {container.name}: {e}"
                        )
            else:
                # Regular task container - clean up
                logger.warning(
                    f"Found orphan task container {container.name} (task_id={task_id}). "
                    "Stopping and removing."
                )
                try:
                    docker_manager.stop_container(container.name, timeout=10)
                    docker_manager.remove_container(container.name)
                    logger.info(
                        f"Successfully cleaned up orphan container {container.name}"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to cleanup orphan container {container.name}: {e}"
                    )
