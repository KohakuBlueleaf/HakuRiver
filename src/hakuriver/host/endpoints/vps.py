"""
VPS (Virtual Private Server) endpoints.

Handles VPS container creation and management.
"""
import asyncio
import datetime
import json
import logging

import peewee
from fastapi import APIRouter, HTTPException

from hakuriver.db.node import Node
from hakuriver.db.task import Task
from hakuriver.docker.naming import vps_container_name
from hakuriver.host.config import config
from hakuriver.host.services.node_manager import find_suitable_node
from hakuriver.host.services.task_scheduler import mark_task_killed, send_kill_to_runner
from hakuriver.models.requests import VPSSubmission
from hakuriver.utils.snowflake import generate_snowflake_id

logger = logging.getLogger(__name__)
router = APIRouter()

# Background tasks set
background_tasks: set[asyncio.Task] = set()


async def send_vps_to_runner(
    runner_url: str,
    task: Task,
    container_name: str,
    ssh_public_key: str,
) -> dict | None:
    """
    Send VPS creation request to a runner.

    Args:
        runner_url: Runner's HTTP URL.
        task: Task record for the VPS.
        container_name: Docker container base image.
        ssh_public_key: SSH public key for VPS access.

    Returns:
        Runner response dict or None on failure.
    """
    import httpx

    payload = {
        "task_id": task.task_id,
        "required_cores": task.required_cores,
        "required_gpus": json.loads(task.required_gpus) if task.required_gpus else [],
        "required_memory_bytes": task.required_memory_bytes,
        "target_numa_node_id": task.target_numa_node_id,
        "container_name": container_name,
        "ssh_public_key": ssh_public_key,
        "ssh_port": task.ssh_port,
    }

    logger.info(f"Sending VPS {task.task_id} to runner at {runner_url}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{runner_url}/vps/create",
                json=payload,
                timeout=60.0,  # VPS creation may take longer
            )
            response.raise_for_status()
            return response.json()

    except httpx.RequestError as e:
        logger.error(f"Failed to send VPS {task.task_id} to {runner_url}: {e}")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Runner {runner_url} rejected VPS {task.task_id}: "
            f"{e.response.status_code} - {e.response.text}"
        )
        return None


def allocate_ssh_port() -> int:
    """
    Allocate a unique SSH port for VPS.

    Returns:
        Available SSH port number.
    """
    # Get existing VPS ports
    existing_ports = set()
    active_vps = Task.select(Task.ssh_port).where(
        (Task.task_type == "vps")
        & (Task.status.in_(["pending", "assigning", "running", "paused"]))
        & (Task.ssh_port.is_null(False))
    )
    for vps in active_vps:
        if vps.ssh_port:
            existing_ports.add(vps.ssh_port)

    # Find available port starting from 2222
    port = 2222
    while port in existing_ports:
        port += 1

    return port


@router.post("/vps/create")
async def submit_vps(submission: VPSSubmission):
    """Submit a new VPS for creation."""
    logger.info(f"Received VPS submission for {submission.required_cores} cores")

    # Find suitable node
    node = find_suitable_node(
        required_cores=submission.required_cores,
        required_gpus=submission.required_gpus,
        required_memory_bytes=submission.required_memory_bytes,
        target_hostname=submission.target_hostname,
        target_numa_node_id=submission.target_numa_node_id,
    )

    if not node:
        raise HTTPException(
            status_code=503,
            detail="No suitable node available for this VPS.",
        )

    # Generate task ID and allocate SSH port
    task_id = generate_snowflake_id()
    ssh_port = allocate_ssh_port()

    # Get container name
    container_name = submission.container_name or config.DEFAULT_CONTAINER_NAME

    # Create task record
    task = Task.create(
        task_id=task_id,
        task_type="vps",
        command="vps",
        required_cores=submission.required_cores,
        required_gpus=json.dumps(submission.required_gpus) if submission.required_gpus else "[]",
        required_memory_bytes=submission.required_memory_bytes,
        target_numa_node_id=submission.target_numa_node_id,
        assigned_node=node.hostname,
        status="assigning",
        ssh_port=ssh_port,
        submitted_at=datetime.datetime.now(),
    )

    logger.info(f"Created VPS task {task_id} assigned to {node.hostname}")

    # Send to runner
    result = await send_vps_to_runner(
        runner_url=node.url,
        task=task,
        container_name=container_name,
        ssh_public_key=submission.ssh_public_key,
    )

    if result is None:
        task.status = "failed"
        task.error_message = "Failed to create VPS on runner."
        task.completed_at = datetime.datetime.now()
        task.save()
        raise HTTPException(
            status_code=502,
            detail="Failed to create VPS on runner.",
        )

    return {
        "message": "VPS created successfully.",
        "task_id": str(task_id),
        "ssh_port": ssh_port,
        "assigned_node": {
            "hostname": node.hostname,
            "url": node.url,
        },
        "runner_response": result,
    }


@router.get("/vps")
async def get_vps_list():
    """Get list of ALL VPS tasks (matching old /vps endpoint)."""
    logger.debug("Fetching all VPS list.")

    try:
        query = (
            Task.select(Task, Node.hostname)
            .join(
                Node, peewee.JOIN.LEFT_OUTER, on=(Task.assigned_node == Node.hostname)
            )
            .where(Task.task_type == "vps")
            .order_by(Task.submitted_at.desc())
        )

        vps_list = []
        for task in query:
            node_hostname = task.assigned_node if isinstance(task.assigned_node, str) else (
                task.assigned_node.hostname if task.assigned_node else None
            )
            vps_list.append({
                "task_id": str(task.task_id),
                "required_cores": task.required_cores,
                "required_gpus": (
                    json.loads(task.required_gpus) if task.required_gpus else []
                ),
                "required_memory_bytes": task.required_memory_bytes,
                "status": task.status,
                "assigned_node": node_hostname,
                "target_numa_node_id": task.target_numa_node_id,
                "exit_code": task.exit_code,
                "error_message": task.error_message,
                "submitted_at": task.submitted_at,
                "started_at": task.started_at,
                "completed_at": task.completed_at,
            })

        return vps_list

    except peewee.PeeweeException as e:
        logger.error(f"Database error fetching VPS: {e}")
        raise HTTPException(
            status_code=500,
            detail="Database error fetching VPS.",
        )


@router.get("/vps/status")
async def get_active_vps_status():
    """Get list of active VPS instances."""
    logger.debug("Fetching active VPS list.")

    try:
        active_statuses = ["pending", "assigning", "running", "paused"]
        query = (
            Task.select(Task, Node.hostname)
            .join(
                Node, peewee.JOIN.LEFT_OUTER, on=(Task.assigned_node == Node.hostname)
            )
            .where((Task.task_type == "vps") & (Task.status.in_(active_statuses)))
            .order_by(Task.submitted_at.desc())
        )

        vps_list = []
        for task in query:
            vps_list.append({
                "task_id": str(task.task_id),
                "status": task.status,
                "assigned_node": task.assigned_node,
                "target_numa_node_id": task.target_numa_node_id,
                "required_cores": task.required_cores,
                "required_gpus": (
                    json.loads(task.required_gpus) if task.required_gpus else []
                ),
                "required_memory_bytes": task.required_memory_bytes,
                "submitted_at": (
                    task.submitted_at.isoformat() if task.submitted_at else None
                ),
                "started_at": (
                    task.started_at.isoformat() if task.started_at else None
                ),
                "ssh_port": task.ssh_port,
            })

        return vps_list

    except peewee.PeeweeException as e:
        logger.error(f"Database error fetching active VPS: {e}")
        raise HTTPException(
            status_code=500,
            detail="Database error fetching active VPS.",
        )


@router.post("/vps/stop/{task_id}", status_code=202)
async def stop_vps(task_id: int):
    """Stop a VPS instance."""
    try:
        task_uuid = int(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Task ID format.")

    task: Task | None = Task.get_or_none(
        (Task.task_id == task_uuid) & (Task.task_type == "vps")
    )

    if not task:
        raise HTTPException(status_code=404, detail="VPS not found.")

    # Check if VPS can be stopped
    stoppable_states = ["pending", "assigning", "running", "paused"]
    if task.status not in stoppable_states:
        raise HTTPException(
            status_code=409,
            detail=f"VPS cannot be stopped (state: {task.status})",
        )

    original_status = task.status
    container_name = vps_container_name(task.task_id)

    # Mark as stopped
    task.status = "stopped"
    task.error_message = "Stopped by user."
    task.completed_at = datetime.datetime.now()
    task.save()
    logger.info(f"Marked VPS {task_id} as 'stopped'.")

    # Tell runner to stop the VPS container
    if original_status in ["running", "paused"] and task.assigned_node:
        node = Node.get_or_none(Node.hostname == task.assigned_node)
        if node and node.status == "online":
            logger.info(
                f"Requesting stop from runner {node.hostname} "
                f"for VPS {task_id}"
            )
            stop_task = asyncio.create_task(
                send_kill_to_runner(node.url, task_id, container_name)
            )
            background_tasks.add(stop_task)
            stop_task.add_done_callback(background_tasks.discard)

    return {"message": f"VPS {task_id} stop requested. VPS marked as stopped."}
