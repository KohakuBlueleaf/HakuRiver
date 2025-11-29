"""
Node Management Endpoints.

Handles node registration, heartbeats, and status queries.
Provides the core functionality for cluster node lifecycle management.
"""

import datetime
import json

from fastapi import APIRouter, HTTPException

from kohakuriver.db.node import Node
from kohakuriver.db.task import Task
from kohakuriver.host.config import config
from kohakuriver.host.services.node_manager import get_all_nodes_status
from kohakuriver.models.requests import HeartbeatRequest, RegisterRequest
from kohakuriver.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Node Registration
# =============================================================================


@router.post("/register")
async def register_node(request: RegisterRequest):
    """
    Register a runner node with the host.

    Creates a new node record or updates an existing one.
    Called by runners on startup to join the cluster.
    """
    hostname = request.hostname
    url = request.url
    total_cores = request.total_cores
    numa_topology = request.numa_topology
    gpu_info = request.gpu_info

    logger.info(f"Registering node: {hostname} at {url} with {total_cores} cores")

    # Upsert node record
    node, created = Node.get_or_create(
        hostname=hostname,
        defaults={
            "url": url,
            "total_cores": total_cores,
            "status": "online",
            "last_heartbeat": datetime.datetime.now(),
            "numa_topology": json.dumps(numa_topology) if numa_topology else "{}",
            "gpu_info": json.dumps(gpu_info) if gpu_info else "[]",
        },
    )

    if not created:
        # Update existing node with new information
        node.url = url
        node.total_cores = total_cores
        node.status = "online"
        node.last_heartbeat = datetime.datetime.now()
        if numa_topology:
            node.numa_topology = json.dumps(numa_topology)
        if gpu_info:
            node.gpu_info = json.dumps(gpu_info)
        node.save()
        logger.info(f"Updated existing node: {hostname}")
    else:
        logger.info(f"Created new node: {hostname}")

    return {
        "message": f"Node {hostname} registered successfully.",
        "created": created,
    }


# =============================================================================
# Heartbeat Processing
# =============================================================================


@router.put("/heartbeat/{hostname}")
async def heartbeat(hostname: str, request: HeartbeatRequest):
    """
    Receive heartbeat from a runner node.

    Updates node health metrics and reconciles task states.
    Processes killed_tasks and running_tasks for task reconciliation.
    """
    node: Node | None = Node.get_or_none(Node.hostname == hostname)
    if not node:
        logger.warning(f"Heartbeat from unknown node: {hostname}")
        raise HTTPException(
            status_code=404,
            detail=f"Node {hostname} not registered. Please register first.",
        )

    now = datetime.datetime.now()

    # Update heartbeat timestamp and metrics
    _update_node_metrics(node, request, now)

    # Process task reconciliation
    _process_killed_tasks(request.killed_tasks, hostname, now)
    _reconcile_assigning_tasks(request.running_tasks, hostname, now)

    return {"message": "Heartbeat received"}


def _update_node_metrics(
    node: Node, request: HeartbeatRequest, now: datetime.datetime
) -> None:
    """Update node with heartbeat metrics."""
    node.last_heartbeat = now
    node.cpu_percent = request.cpu_percent
    node.memory_percent = request.memory_percent
    node.memory_used_bytes = request.memory_used_bytes
    node.memory_total_bytes = request.memory_total_bytes
    node.current_avg_temp = request.current_avg_temp
    node.current_max_temp = request.current_max_temp

    if request.gpu_info:
        node.gpu_info = json.dumps(request.gpu_info)

    # Mark as online if it was offline
    if node.status != "online":
        logger.info(f"Node {node.hostname} came back online")
        node.status = "online"

    node.save()


def _process_killed_tasks(
    killed_tasks: list | None, hostname: str, now: datetime.datetime
) -> None:
    """Process killed tasks reported by runner."""
    if not killed_tasks:
        return

    logger.info(f"Heartbeat from {hostname} reported killed tasks: {killed_tasks}")

    terminal_statuses = {
        "completed",
        "failed",
        "killed",
        "lost",
        "killed_oom",
        "stopped",
    }

    for killed_info in killed_tasks:
        task: Task | None = Task.get_or_none(Task.task_id == killed_info.task_id)

        if not task:
            logger.warning(
                f"Runner reported killed task {killed_info.task_id}, but task not found"
            )
            continue

        if task.status in terminal_statuses:
            logger.debug(
                f"Runner reported killed task {killed_info.task_id}, "
                f"but already in terminal state '{task.status}'"
            )
            continue

        # Update task to failed/killed state
        original_status = task.status
        new_status = "killed_oom" if killed_info.reason == "oom" else "failed"

        task.status = new_status
        task.exit_code = -9
        task.error_message = f"Killed by runner: {killed_info.reason}"
        task.completed_at = now
        task.save()

        logger.warning(
            f"Task {killed_info.task_id} on {hostname} marked as '{new_status}' "
            f"(was '{original_status}'): {killed_info.reason}"
        )


def _reconcile_assigning_tasks(
    running_tasks: list[int], hostname: str, now: datetime.datetime
) -> None:
    """Reconcile tasks in 'assigning' state with runner's running tasks."""
    assigning_tasks: list[Task] = list(
        Task.select().where(
            (Task.assigned_node == hostname) & (Task.status == "assigning")
        )
    )

    if not assigning_tasks:
        return

    runner_running_set = set(running_tasks)
    heartbeat_interval = config.HEARTBEAT_INTERVAL_SECONDS

    logger.debug(
        f"Reconciling {len(assigning_tasks)} assigning tasks on {hostname}. "
        f"Runner reports running: {runner_running_set}"
    )

    for task in assigning_tasks:
        if task.task_id in runner_running_set:
            _confirm_task_running(task, hostname, now)
        else:
            _check_task_assignment_timeout(task, hostname, now, heartbeat_interval)


def _confirm_task_running(task: Task, hostname: str, now: datetime.datetime) -> None:
    """Confirm task is running based on runner report."""
    logger.info(
        f"Task {task.task_id} confirmed running by {hostname}. "
        "Updating status from 'assigning' to 'running'"
    )

    task.status = "running"
    if task.started_at is None:
        task.started_at = now
    if task.assignment_suspicion_count > 0:
        task.assignment_suspicion_count = 0
    task.save()


def _check_task_assignment_timeout(
    task: Task, hostname: str, now: datetime.datetime, heartbeat_interval: int
) -> None:
    """Check if assigning task has timed out."""
    time_since_submit = now - task.submitted_at
    timeout_threshold = datetime.timedelta(seconds=heartbeat_interval * 3)

    if time_since_submit <= timeout_threshold:
        return

    if task.assignment_suspicion_count < 2:
        # Increment suspicion counter
        task.assignment_suspicion_count += 1
        task.save()
        logger.warning(
            f"Task {task.task_id} (on {hostname}) still 'assigning' and not reported running. "
            f"Marked as suspect ({task.assignment_suspicion_count})"
        )
    else:
        # Mark as failed after too many suspicions
        task.status = "failed"
        task.error_message = (
            f"Task assignment failed. Runner {hostname} did not confirm start "
            "after multiple checks."
        )
        task.completed_at = now
        task.exit_code = -1
        task.save()
        logger.error(
            f"Task {task.task_id} (on {hostname}) failed assignment. "
            f"Marked as failed (suspect count: {task.assignment_suspicion_count})"
        )


# =============================================================================
# Node Status
# =============================================================================


@router.get("/nodes")
async def get_nodes_status():
    """Get status of all registered nodes."""
    return get_all_nodes_status()
