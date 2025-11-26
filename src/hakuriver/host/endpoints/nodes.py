"""
Node management endpoints.

Handles node registration, heartbeats, and status queries.
Matches old core/host.py behavior for compatibility.
"""

import datetime
import json
import logging

from fastapi import APIRouter, HTTPException

from hakuriver.db.node import Node
from hakuriver.db.task import Task
from hakuriver.host.config import config
from hakuriver.host.services.node_manager import get_all_nodes_status
from hakuriver.models.requests import HeartbeatRequest, RegisterRequest

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/register")
async def register_node(request: RegisterRequest):
    """Register a runner node with the host."""
    hostname = request.hostname
    url = request.url
    total_cores = request.total_cores
    numa_topology = request.numa_topology
    gpu_info = request.gpu_info

    logger.info(f"Registering node: {hostname} at {url} with {total_cores} cores")

    # Upsert node
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
        # Update existing node
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


@router.put("/heartbeat/{hostname}")
async def heartbeat(hostname: str, request: HeartbeatRequest):
    """Receive heartbeat from a runner node.

    Matches old PUT /heartbeat/{hostname} endpoint.
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

    # Update heartbeat timestamp
    node.last_heartbeat = now

    # Update resource metrics
    node.cpu_percent = request.cpu_percent
    node.memory_percent = request.memory_percent
    node.memory_used_bytes = request.memory_used_bytes
    node.memory_total_bytes = request.memory_total_bytes
    node.current_avg_temp = request.current_avg_temp
    node.current_max_temp = request.current_max_temp

    # Update GPU info if provided
    if request.gpu_info:
        node.gpu_info = json.dumps(request.gpu_info)

    # Mark as online if it was offline
    if node.status != "online":
        logger.info(f"Node {hostname} came back online.")
        node.status = "online"

    node.save()

    # --- 1. Process killed tasks reported by runner ---
    if request.killed_tasks:
        logger.info(
            f"Heartbeat from {hostname} reported killed tasks: {request.killed_tasks}"
        )
        for killed_info in request.killed_tasks:
            task: Task | None = Task.get_or_none(Task.task_id == killed_info.task_id)
            if task and task.status not in [
                "completed",
                "failed",
                "killed",
                "lost",
                "killed_oom",
                "stopped",
            ]:
                original_status = task.status
                new_status = "killed_oom" if killed_info.reason == "oom" else "failed"
                task.status = new_status
                task.exit_code = -9
                task.error_message = f"Killed by runner: {killed_info.reason}"
                task.completed_at = now
                task.save()
                logger.warning(
                    f"Task {killed_info.task_id} on {hostname} marked as '{new_status}' "
                    f"(was '{original_status}') due to runner report: {killed_info.reason}"
                )
            elif task:
                logger.debug(
                    f"Runner reported killed task {killed_info.task_id}, "
                    f"but it was already in final state '{task.status}'."
                )
            else:
                logger.warning(
                    f"Runner reported killed task {killed_info.task_id}, but task not found in DB."
                )

    # --- 2. Reconcile 'assigning' tasks ---
    assigning_tasks: list[Task] = list(
        Task.select().where(
            (Task.assigned_node == hostname) & (Task.status == "assigning")
        )
    )
    if assigning_tasks:
        runner_running_set = set(request.running_tasks)
        logger.debug(
            f"Reconciling {len(assigning_tasks)} assigning tasks on {hostname}. "
            f"Runner reports running: {runner_running_set}"
        )
        heartbeat_interval = getattr(config, "HEARTBEAT_INTERVAL_SECONDS", 30)

        for task in assigning_tasks:
            if task.task_id not in runner_running_set:
                time_since_submit = now - task.submitted_at
                # Increase suspicion if assigning for too long without confirmation
                if time_since_submit > datetime.timedelta(
                    seconds=heartbeat_interval * 3
                ):
                    if task.assignment_suspicion_count < 2:
                        task.assignment_suspicion_count += 1
                        logger.warning(
                            f"Task {task.task_id} (on {hostname}) still 'assigning' and not reported running. "
                            f"Marked as suspect ({task.assignment_suspicion_count})."
                        )
                        task.save()
                    else:
                        # Mark as failed if suspect count is high
                        task.status = "failed"
                        task.error_message = (
                            f"Task assignment failed. Runner {hostname} did not confirm start "
                            "after multiple checks."
                        )
                        task.completed_at = now
                        task.exit_code = -1
                        logger.error(
                            f"Task {task.task_id} (on {hostname}) failed assignment. "
                            f"Marked as failed (suspect {task.assignment_suspicion_count})."
                        )
                        task.save()
            else:
                # Runner reports task running while DB says assigning - update to running
                logger.info(
                    f"Task {task.task_id} confirmed running by {hostname}. "
                    "Updating status from 'assigning' to 'running'."
                )
                task.status = "running"
                if task.started_at is None:
                    task.started_at = now
                if task.assignment_suspicion_count > 0:
                    task.assignment_suspicion_count = 0
                task.save()

    return {"message": "Heartbeat received"}


@router.get("/nodes")
async def get_nodes_status():
    """Get status of all registered nodes."""
    return get_all_nodes_status()
