"""
Task management endpoints.

Handles task submission, status queries, and control operations.
Matches old behavior from core/host.py for compatibility.
"""
import asyncio
import datetime
import json
import logging
import os

import peewee
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from hakuriver.db.node import Node
from hakuriver.db.task import Task
from hakuriver.docker.naming import task_container_name
from hakuriver.host.config import config
from hakuriver.host.services.node_manager import (
    find_suitable_node,
    get_node_available_cores,
    get_node_available_memory,
    get_node_available_gpus,
)
from hakuriver.host.services.task_scheduler import (
    mark_task_killed,
    send_kill_to_runner,
    send_pause_to_runner,
    send_resume_to_runner,
    send_task_to_runner,
    send_vps_task_to_runner,
    update_task_status,
)
from hakuriver.models.requests import TaskStatusUpdate, TaskSubmission
from hakuriver.utils.snowflake import generate_snowflake_id

logger = logging.getLogger(__name__)
router = APIRouter()

# Background tasks set
background_tasks: set[asyncio.Task] = set()


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

    logger.debug(f"Allocated SSH port: {port}")
    return port


@router.post("/submit", status_code=202)
async def submit_task(req: TaskSubmission):
    """Submit a task request and dispatch to one or more target nodes.

    Handles both 'command' and 'vps' task types.
    For VPS tasks, the 'command' field contains the SSH public key.

    This matches the old /submit endpoint behavior.
    """
    logger.info(f"Received task submission: type={req.task_type}, command={req.command[:50] if req.command else 'N/A'}...")
    logger.debug(f"Full submission: {req.model_dump()}")

    # Validate task type
    if req.task_type not in {"command", "vps"}:
        raise HTTPException(
            status_code=400,
            detail="Invalid task type. Only 'command' and 'vps' are supported.",
        )

    # VPS tasks don't need command/arguments
    if req.task_type == "vps":
        # For VPS, req.command stores the SSH public key
        req.arguments = []
        req.env_vars = {}

    created_task_ids = []
    failed_targets = []
    first_task_id_for_batch = None

    # Create output directories
    output_dir = os.path.join(config.SHARED_DIR, "logs")
    try:
        os.makedirs(output_dir, exist_ok=True)
        logger.debug(f"Output directory ensured: {output_dir}")
    except OSError as e:
        logger.error(f"Cannot create output directory {output_dir}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: Cannot create log directories.",
        )

    # Determine container name
    if req.container_name == "NULL":
        if req.task_type == "vps":
            raise HTTPException(
                status_code=400,
                detail="VPS tasks require a Docker container.",
            )
        task_container_name_str = None
    else:
        task_container_name_str = req.container_name or config.DEFAULT_CONTAINER_NAME

    task_docker_image_tag = f"hakuriver/{task_container_name_str}:base" if task_container_name_str else None
    task_privileged = config.TASKS_PRIVILEGED if req.privileged is None else req.privileged
    task_additional_mounts = config.ADDITIONAL_MOUNTS if req.additional_mounts is None else req.additional_mounts

    logger.debug(f"Container: {task_container_name_str}, Image: {task_docker_image_tag}")
    logger.debug(f"Privileged: {task_privileged}, Additional mounts: {task_additional_mounts}")

    # Determine targets
    targets = req.targets
    if not targets:
        if req.required_gpus:
            raise HTTPException(
                status_code=400,
                detail="No target node specified for GPU task is not allowed.",
            )
        # Auto-select a suitable node
        node = find_suitable_node(required_cores=req.required_cores)
        if not node:
            raise HTTPException(
                status_code=503,
                detail="No suitable node available for this task.",
            )
        targets = [node.hostname]
        logger.debug(f"Auto-selected target: {targets}")

    # Ensure required_gpus has one list per target
    required_gpus = req.required_gpus or [[] for _ in targets]
    if len(required_gpus) != len(targets):
        raise HTTPException(
            status_code=400,
            detail=f"required_gpus length ({len(required_gpus)}) must match targets length ({len(targets)}).",
        )

    # VPS tasks can only have one target
    if len(targets) > 1 and req.task_type == "vps":
        raise HTTPException(
            status_code=400,
            detail="VPS tasks cannot be submitted to multiple targets.",
        )

    logger.debug(f"Processing {len(targets)} targets: {targets}")

    # Process each target
    for target_str, target_gpus in zip(targets, required_gpus, strict=True):
        logger.debug(f"Processing target: {target_str}, GPUs: {target_gpus}")

        # Parse target string (hostname or hostname:numa_id)
        target_numa_id: int | None = None
        parts = target_str.split(":")
        target_hostname = parts[0]
        if len(parts) > 1:
            try:
                target_numa_id = int(parts[1])
                if target_numa_id < 0:
                    raise ValueError("NUMA ID cannot be negative")
            except ValueError:
                logger.warning(f"Invalid NUMA ID format in target '{target_str}'. Skipping.")
                failed_targets.append({"target": target_str, "reason": "Invalid NUMA ID format"})
                continue

        # Find and validate node
        node: Node | None = Node.get_or_none(Node.hostname == target_hostname)
        if not node:
            logger.warning(f"Target node '{target_hostname}' not registered. Skipping.")
            failed_targets.append({"target": target_str, "reason": "Node not registered"})
            continue
        if node.status != "online":
            logger.warning(f"Target node '{target_hostname}' is not online (status: {node.status}). Skipping.")
            failed_targets.append({"target": target_str, "reason": f"Node status is {node.status}"})
            continue

        # Validate NUMA target (if specified)
        node_topology = node.get_numa_topology()
        if target_numa_id is not None:
            if node_topology is None:
                logger.warning(f"Target '{target_str}' specified NUMA ID but node has no NUMA topology. Skipping.")
                failed_targets.append({"target": target_str, "reason": "Node has no NUMA topology"})
                continue
            if target_numa_id not in node_topology:
                logger.warning(f"Invalid NUMA ID {target_numa_id} for node (Valid: {list(node_topology.keys())}). Skipping.")
                failed_targets.append({"target": target_str, "reason": f"Invalid NUMA ID (Valid: {list(node_topology.keys())})"})
                continue

        # Validate GPU allocation
        gpu_info = node.get_gpu_info()
        if gpu_info and target_gpus:
            invalid_gpus = [gpu_id for gpu_id in target_gpus if gpu_id >= len(gpu_info) or gpu_id < 0]
            if invalid_gpus:
                logger.warning(f"Invalid GPU IDs {invalid_gpus} for target '{target_str}'. Skipping.")
                failed_targets.append({"target": target_str, "reason": f"Invalid GPU IDs: {invalid_gpus}"})
                continue
            available_gpus = get_node_available_gpus(node)
            if set(target_gpus) - available_gpus:
                logger.warning(f"Requested GPUs {target_gpus} not available. Skipping.")
                failed_targets.append({"target": target_str, "reason": "Requested GPUs not available"})
                continue

        # Check available cores
        available_cores = get_node_available_cores(node)
        if req.required_cores and available_cores < req.required_cores:
            logger.warning(f"Insufficient cores on node '{target_hostname}' ({available_cores} < {req.required_cores}). Skipping.")
            failed_targets.append({"target": target_str, "reason": "Insufficient available cores"})
            continue

        # Check available memory
        if req.required_memory_bytes:
            available_memory = get_node_available_memory(node)
            if available_memory < req.required_memory_bytes:
                logger.warning(f"Insufficient memory on node '{target_hostname}'. Skipping.")
                failed_targets.append({"target": target_str, "reason": "Insufficient available memory"})
                continue

        # Generate task ID
        task_id = generate_snowflake_id()
        if first_task_id_for_batch is None:
            first_task_id_for_batch = task_id
        current_batch_id = first_task_id_for_batch

        # Create output paths
        task_log_dir = os.path.join(output_dir, str(task_id))
        stdout_path = os.path.join(task_log_dir, "stdout.log")
        stderr_path = os.path.join(task_log_dir, "stderr.log")

        # Allocate SSH port for VPS tasks
        ssh_port = None
        if req.task_type == "vps":
            ssh_port = allocate_ssh_port()

        logger.debug(f"Task {task_id}: stdout={stdout_path}, stderr={stderr_path}, ssh_port={ssh_port}")

        # Create task record
        try:
            task = Task.create(
                task_id=task_id,
                task_type=req.task_type,
                batch_id=current_batch_id,
                command=req.command,
                arguments=json.dumps(req.arguments) if req.arguments else "[]",
                env_vars=json.dumps(req.env_vars) if req.env_vars else "{}",
                required_cores=req.required_cores,
                required_gpus=json.dumps(target_gpus),
                required_memory_bytes=req.required_memory_bytes,
                assigned_node=node.hostname,
                status="assigning",
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                submitted_at=datetime.datetime.now(),
                target_numa_node_id=target_numa_id,
                container_name=task_container_name_str,
                docker_image_name=task_docker_image_tag,
                docker_privileged=task_privileged,
                docker_mount_dirs=json.dumps(task_additional_mounts) if task_additional_mounts else "[]",
                ssh_port=ssh_port,
            )
            logger.info(f"Task {task_id} created, assigned to {node.hostname}")

        except Exception as e:
            logger.exception(f"Failed to create task record for target '{target_str}': {e}")
            failed_targets.append({"target": target_str, "reason": "Database error during task creation"})
            continue

        # Dispatch task to runner
        result = None
        if req.task_type == "vps":
            # VPS tasks - command contains SSH public key
            result = await send_vps_task_to_runner(
                runner_url=node.url,
                task=task,
                container_name=task_container_name_str,
                ssh_public_key=req.command,  # SSH key stored in command field
            )
            if result is None:
                task.status = "failed"
                task.error_message = "Failed to create VPS on runner."
                task.completed_at = datetime.datetime.now()
                task.save()
                failed_targets.append({"target": target_str, "reason": "Runner failed to create VPS"})
                continue
        else:
            # Regular command tasks - dispatch in background
            working_dir = "/shared"  # Default working directory
            dispatch_task = asyncio.create_task(
                send_task_to_runner(
                    runner_url=node.url,
                    task=task,
                    container_name=task_container_name_str,
                    working_dir=working_dir,
                )
            )
            background_tasks.add(dispatch_task)
            dispatch_task.add_done_callback(background_tasks.discard)

        created_task_ids.append(str(task_id))

    # Construct response
    if not created_task_ids and failed_targets:
        detail = f"Failed to schedule task for any target. Failures: {failed_targets}"
        logger.error(f"Task submission failed for all targets. Failures: {failed_targets}")
        raise HTTPException(status_code=503, detail=detail)

    if failed_targets:
        message = f"Task batch submitted. {len(created_task_ids)} tasks created. Some targets failed."
        logger.warning(f"Partial submission. Succeeded: {created_task_ids}. Failed: {failed_targets}")
        return {
            "message": message,
            "task_ids": created_task_ids,
            "failed_targets": failed_targets,
        }

    message = f"Task batch submitted successfully. {len(created_task_ids)} tasks created."
    logger.info(f"Task batch submission successful. Task IDs: {created_task_ids}")
    response = {
        "message": message,
        "task_ids": created_task_ids,
        "assigned_node": {
            "hostname": node.hostname,
            "url": node.url,
        },
    }
    if result:
        response["runner_response"] = result
    return response


@router.post("/update")
async def update_task_status_endpoint(update: TaskStatusUpdate):
    """Receive task status update from runner."""
    logger.info(f"Received status update for task {update.task_id}: {update.status}")
    logger.debug(f"Full update: {update.model_dump()}")

    success = update_task_status(
        task_id=update.task_id,
        status=update.status,
        exit_code=update.exit_code,
        message=update.message,
        started_at=update.started_at,
        completed_at=update.completed_at,
        ssh_port=update.ssh_port,
    )

    if not success:
        return {"message": "Task ID not recognized or invalid state transition."}

    return {"message": "Task status updated successfully."}


@router.get("/status/{task_id}")
async def get_task_status(task_id: int):
    """Get status of a specific task."""
    logger.debug(f"get_task_status called for task_id={task_id}")

    try:
        task_uuid = int(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Task ID format.")

    task: Task | None = (
        Task.select(Task, Node.hostname.alias("node_hostname"))
        .left_outer_join(Node, on=(Task.assigned_node == Node.hostname))
        .where(Task.task_id == task_uuid)
        .first()
    )

    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    return {
        "task_id": str(task.task_id),
        "batch_id": str(task.batch_id) if task.batch_id else None,
        "task_type": task.task_type,
        "command": task.command,
        "arguments": task.get_arguments(),
        "env_vars": task.get_env_vars(),
        "required_cores": task.required_cores,
        "required_gpus": json.loads(task.required_gpus) if task.required_gpus else [],
        "required_memory_bytes": task.required_memory_bytes,
        "status": task.status,
        "assigned_node": (
            task.node_hostname if hasattr(task, "node_hostname") else None
        ),
        "target_numa_node_id": task.target_numa_node_id,
        "stdout_path": task.stdout_path,
        "stderr_path": task.stderr_path,
        "exit_code": task.exit_code,
        "error_message": task.error_message,
        "submitted_at": task.submitted_at.isoformat() if task.submitted_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "assignment_suspicion_count": task.assignment_suspicion_count,
        "ssh_port": task.ssh_port,
    }


@router.get("/tasks")
async def list_tasks(
    status: str | None = None,
    task_type: str | None = None,  # No default filter - show all task types
    limit: int = 100,
    offset: int = 0,
):
    """List tasks with optional filtering.

    Returns all fields that frontend expects (matching old code behavior).
    """
    logger.debug(f"list_tasks called: status={status}, task_type={task_type}, limit={limit}, offset={offset}")

    query = Task.select().order_by(Task.submitted_at.desc())
    logger.debug(f"Initial query created")

    # Filter by task type if specified
    if task_type:
        query = query.where(Task.task_type == task_type)
        logger.debug(f"Added task_type filter: {task_type}")

    if status:
        query = query.where(Task.status == status)
        logger.debug(f"Added status filter: {status}")

    query = query.limit(limit).offset(offset)
    logger.debug(f"Applied limit={limit}, offset={offset}")

    # Debug: count total tasks in database
    try:
        total_count = Task.select().count()
        filtered_count = query.count()
        logger.debug(f"Total tasks in DB: {total_count}, After filters: {filtered_count}")
        # Show distinct task_types in DB for debugging
        distinct_types = [t.task_type for t in Task.select(Task.task_type).distinct()]
        logger.debug(f"Distinct task_types in DB: {distinct_types}")
    except Exception as e:
        logger.debug(f"Error counting tasks: {e}")

    tasks = []
    for task in query:
        logger.debug(f"Processing task: id={task.task_id}, type={task.task_type}, status={task.status}")
        tasks.append({
            "task_id": str(task.task_id),
            "batch_id": str(task.batch_id) if task.batch_id else None,
            "task_type": task.task_type,
            "command": task.command,
            "arguments": task.get_arguments(),
            "env_vars": task.get_env_vars(),
            "required_cores": task.required_cores,
            "required_gpus": json.loads(task.required_gpus) if task.required_gpus else [],
            "required_memory_bytes": task.required_memory_bytes,
            "status": task.status,
            "assigned_node": task.assigned_node,
            "target_numa_node_id": task.target_numa_node_id,
            "stdout_path": task.stdout_path,
            "stderr_path": task.stderr_path,
            "exit_code": task.exit_code,
            "error_message": task.error_message,
            "submitted_at": task.submitted_at.isoformat() if task.submitted_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "assignment_suspicion_count": task.assignment_suspicion_count,
            "ssh_port": task.ssh_port,
        })

    logger.debug(f"Returning {len(tasks)} tasks")
    return tasks


@router.post("/kill/{task_id}", status_code=202)
async def request_kill_task(task_id: int):
    """Request to kill a running task."""
    logger.debug(f"request_kill_task called for task_id={task_id}")

    try:
        task_uuid = int(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Task ID format.")

    task: Task | None = Task.get_or_none(Task.task_id == task_uuid)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    # Check if task can be killed
    killable_states = ["pending", "assigning", "running", "paused"]
    if task.status not in killable_states:
        raise HTTPException(
            status_code=409,
            detail=f"Task cannot be killed (state: {task.status})",
        )

    original_status = task.status
    container_name = task_container_name(task.task_id)

    # Mark as killed
    mark_task_killed(task)

    # If running on an online node, tell the runner
    if original_status in ["running", "paused"] and task.assigned_node:
        node = Node.get_or_none(Node.hostname == task.assigned_node)
        if node and node.status == "online":
            logger.info(
                f"Requesting kill from runner {node.hostname} "
                f"for task {task_id}"
            )
            kill_task = asyncio.create_task(
                send_kill_to_runner(node.url, task_id, container_name)
            )
            background_tasks.add(kill_task)
            kill_task.add_done_callback(background_tasks.discard)

    return {"message": f"Kill requested for task {task_id}. Task marked as killed."}


@router.post("/command/{task_id}/{command}")
async def send_command_to_task(task_id: int, command: str):
    """Send a command (pause/resume) to a task."""
    logger.info(f"Received command '{command}' for task {task_id}")

    task: Task | None = Task.get_or_none(Task.task_id == task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    if not task.assigned_node:
        raise HTTPException(status_code=400, detail="Task has no assigned node.")

    node = Node.get_or_none(Node.hostname == task.assigned_node)
    if not node:
        raise HTTPException(status_code=400, detail="Assigned node not found.")

    container_name = task_container_name(task.task_id)

    match (command, task.status):
        case ("pause", "running"):
            response = await send_pause_to_runner(
                node.url, task_id, container_name
            )
            if "successfully" in response:
                task.status = "paused"
                task.save()
            return {"message": f"Pause for task {task_id}: {response}"}

        case ("resume", "paused"):
            response = await send_resume_to_runner(
                node.url, task_id, container_name
            )
            if "successfully" in response:
                task.status = "running"
                task.save()
            return {"message": f"Resume for task {task_id}: {response}"}

        case _:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid command or task state: {command} for {task.status}",
            )


@router.get("/task/{task_id}/stdout", response_class=PlainTextResponse)
async def get_task_stdout(task_id: int, lines: int = 100):
    """Get stdout output from a task.

    Returns plain text (matching old code behavior for frontend compatibility).
    """
    logger.debug(f"get_task_stdout called for task_id={task_id}, lines={lines}")

    task: Task | None = Task.get_or_none(Task.task_id == task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    if task.task_type == "vps":
        raise HTTPException(status_code=400, detail="VPS tasks do not have stdout.")

    if not task.stdout_path or not os.path.exists(task.stdout_path):
        logger.debug(f"stdout file not found: {task.stdout_path}")
        return ""  # Return empty string for missing output

    try:
        with open(task.stdout_path, "r") as f:
            content = f.readlines()[-lines:]
        return "".join(content)
    except Exception as e:
        logger.error(f"Error reading stdout for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail="Error reading stdout.")


@router.get("/task/{task_id}/stderr", response_class=PlainTextResponse)
async def get_task_stderr(task_id: int, lines: int = 100):
    """Get stderr output from a task.

    Returns plain text (matching old code behavior for frontend compatibility).
    """
    logger.debug(f"get_task_stderr called for task_id={task_id}, lines={lines}")

    task: Task | None = Task.get_or_none(Task.task_id == task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    if task.task_type == "vps":
        raise HTTPException(status_code=400, detail="VPS tasks do not have stderr.")

    if not task.stderr_path or not os.path.exists(task.stderr_path):
        logger.debug(f"stderr file not found: {task.stderr_path}")
        return ""  # Return empty string for missing output

    try:
        with open(task.stderr_path, "r") as f:
            content = f.readlines()[-lines:]
        return "".join(content)
    except Exception as e:
        logger.error(f"Error reading stderr for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail="Error reading stderr.")
