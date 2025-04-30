import asyncio
import datetime
import os
import json
import re
from collections import defaultdict
from typing import Iterable, List

import peewee
import httpx
from fastapi import FastAPI, HTTPException, Query, Path, WebSocket
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator

from hakuriver.utils.snowflake import Snowflake
from hakuriver.utils.logger import logger
from hakuriver.utils.gpu import GPUInfo
from hakuriver.utils import docker as docker_utils
from hakuriver.db.models import db, Node, Task, initialize_database
from hakuriver.core.config import HOST_CONFIG
from hakuriver.core.models import (
    TaskStatusUpdate,
    HeartbeatData,
    TaskInfo as TaskInfoForRunner,
    RunnerInfo,
    TaskRequest,
)

from .docker.host_api import router as docker_host_router
from .docker.host_terminal import terminal_websocket_endpoint


# --- global state ---
snowflake = Snowflake()
docker_lock = asyncio.Lock()


# --- FastAPI App ---
app = FastAPI(title="HakuRiver Cluster Manager")
# Include the Docker HTTP router
app.include_router(docker_host_router, prefix="/docker", tags=["Docker (Host)"])


# Register the Docker terminal WebSocket endpoint
@app.websocket("/docker/host/containers/{container_name}/terminal")
async def websocket_endpoint_wrapper(
    websocket: WebSocket, container_name: str = Path(...)
):
    await terminal_websocket_endpoint(websocket, container_name=container_name)


# --- Helper Functions (Logic remains the same, just use logger) ---
def get_node_available_cores(node: Node) -> int:
    running_tasks_cores = (
        Task.select(peewee.fn.SUM(Task.required_cores))
        .where((Task.assigned_node == node) & (Task.status == "running"))
        .scalar()
        or 0
    )
    return node.total_cores - running_tasks_cores


def get_node_available_memory(node: Node) -> int:
    running_tasks_memory = (
        Task.select(peewee.fn.SUM(Task.required_memory_bytes))
        .where(
            (Task.assigned_node == node)
            & ((Task.status == "running") | (Task.status == "pending"))
        )
        .scalar()
        or 0
    )
    return node.memory_total_bytes - running_tasks_memory


def get_node_available_gpus(node: Node) -> set[int]:
    running_tasks_gpus = (
        json.loads(task.required_gpus)
        for task in Task.select().where(
            (Task.assigned_node == node)
            & ((Task.status == "running") | (Task.status == "pending"))
        )
    )
    all_used_ids = set()
    for task_gpus in running_tasks_gpus:
        all_used_ids.update(set(task_gpus))
    all_ids = set(i["gpu_id"] for i in node.get_gpu_info())
    return all_ids - all_used_ids


def find_suitable_node(required_cores: int) -> Node | None:
    online_nodes: Node = Node.select().where(Node.status == "online")
    candidate_nodes = []
    for node in online_nodes:
        available_cores = get_node_available_cores(node)
        if available_cores >= required_cores:
            candidate_nodes.append((node, available_cores))

    if not candidate_nodes:
        logger.warning(f"No suitable online node found for {required_cores} cores.")
        return None

    # Simple strategy: Choose the node with the fewest available cores (but still enough)
    # This tries to fill up nodes more evenly. Could use other strategies.
    candidate_nodes.sort(key=lambda x: x[1])
    selected_node = candidate_nodes[0][0]
    logger.info(
        f"Selected node {selected_node.hostname} "
        f"(has {candidate_nodes[0][1]} available) "
        f"for {required_cores} core task."
    )
    return selected_node


async def send_task_to_runner(runner_url: str, task_info: TaskInfoForRunner):
    task_id = task_info.task_id
    logger.info(f"Attempting to send task {task_id} to runner at {runner_url}")
    try:
        # Use longer timeout for potentially slow runner start
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{runner_url}/run", json=task_info.model_dump(), timeout=30.0
            )
            response.raise_for_status()
        logger.info(f"Task {task_id} successfully sent to runner {runner_url}")
        # Let runner report 'running' status

        task: Task = Task.get_or_none(Task.task_id == task_id)
        if task and task.status == "assigning":
            # Keep as assigning until runner confirms start
            pass
    except httpx.RequestError as e:
        logger.error(f"Failed to contact runner {runner_url} for task {task_id}: {e}")

        task: Task = Task.get_or_none(Task.task_id == task_id)
        if task and task.status == "assigning":  # Only fail if it was still assigning
            task.status = "failed"
            task.error_message = f"Failed to contact runner: {e}"
            task.completed_at = datetime.datetime.now()
            task.save()
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Runner {runner_url} rejected task {task_id}: {e.response.status_code} - {e.response.text}"
        )

        task: Task = Task.get_or_none(Task.task_id == task_id)
        if task and task.status == "assigning":
            task.status = "failed"
            task.error_message = (
                f"Runner rejected task: {e.response.status_code} - {e.response.text}"
            )
            task.completed_at = datetime.datetime.now()
            task.save()
    except Exception as e:
        logger.exception(
            f"Unexpected error sending task {task_id} to {runner_url}: {e}"
        )

        task: Task = Task.get_or_none(Task.task_id == task_id)
        if task and task.status == "assigning":
            task.status = "failed"
            task.error_message = f"Unexpected error during task dispatch: {e}"
            task.completed_at = datetime.datetime.now()
            task.save()


async def send_vps_task_to_runner(runner_url: str, task_info: TaskInfoForRunner):
    task_id = task_info.task_id
    logger.info(f"Attempting to send task {task_id} to runner at {runner_url}")
    try:
        # Use longer timeout for potentially slow runner start
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{runner_url}/run", json=task_info.model_dump(), timeout=30.0
            )
            response.raise_for_status()
        logger.info(f"Task {task_id} successfully sent to runner {runner_url}")
        # Let runner report 'running' status

        task: Task = Task.get_or_none(Task.task_id == task_id)
        if task and task.status == "assigning":
            # Keep as assigning until runner confirms start
            pass
    except httpx.RequestError as e:
        logger.error(f"Failed to contact runner {runner_url} for task {task_id}: {e}")

        task: Task = Task.get_or_none(Task.task_id == task_id)
        if task and task.status == "assigning":  # Only fail if it was still assigning
            task.status = "failed"
            task.error_message = f"Failed to contact runner: {e}"
            task.completed_at = datetime.datetime.now()
            task.save()
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Runner {runner_url} rejected task {task_id}: {e.response.status_code} - {e.response.text}"
        )

        task: Task = Task.get_or_none(Task.task_id == task_id)
        if task and task.status == "assigning":
            task.status = "failed"
            task.error_message = (
                f"Runner rejected task: {e.response.status_code} - {e.response.text}"
            )
            task.completed_at = datetime.datetime.now()
            task.save()
    except Exception as e:
        logger.exception(
            f"Unexpected error sending task {task_id} to {runner_url}: {e}"
        )

        task: Task = Task.get_or_none(Task.task_id == task_id)
        if task and task.status == "assigning":
            task.status = "failed"
            task.error_message = f"Unexpected error during task dispatch: {e}"
            task.completed_at = datetime.datetime.now()
            task.save()


def get_secure_log_path(task: Task, log_type: str) -> str | None:
    """
    Validates the log path stored in the DB and returns the full, secure path.
    Returns None if the path is invalid or outside the expected directory.
    """
    if log_type == "stdout":
        base_dir = os.path.join(HOST_CONFIG.SHARED_DIR, "task_outputs")
        db_path = task.stdout_path
    elif log_type == "stderr":
        base_dir = os.path.join(HOST_CONFIG.SHARED_DIR, "task_errors")
        db_path = task.stderr_path
    else:
        return None

    if not db_path:
        logger.warning(f"Task {task.task_id} has no {log_type} path in DB.")
        return None

    # Basic check: ensure the stored path is just a filename
    filename = os.path.basename(db_path)
    if not filename or filename != db_path.split(os.sep)[-1]:
        logger.error(
            f"Invalid log path format in DB for task {task.task_id} {log_type}: {db_path}"
        )
        return None

    # Construct full path
    full_path = os.path.abspath(os.path.join(base_dir, filename))

    # Security Check: Ensure the resolved path is still within the intended base directory
    if os.path.commonpath([full_path, os.path.abspath(base_dir)]) != os.path.abspath(
        base_dir
    ):
        logger.error(
            f"Path traversal attempt detected for task {task.task_id} {log_type}: {full_path}"
        )
        return None

    return full_path


# --- API Endpoints (Logic remains the same, use logger) ---
@app.post("/register")
async def register_runner(info: RunnerInfo):
    node: Node
    defaults = {
        "url": info.runner_url,
        "total_cores": info.total_cores,
        "last_heartbeat": datetime.datetime.now(),
        "status": "online",
        "memory_total_bytes": info.total_ram_bytes,
        "numa_topology": (
            json.dumps(info.numa_topology) if info.numa_topology else None
        ),  # Store as JSON
        "gpu_info": (
            json.dumps([gpu.model_dump() for gpu in info.gpu_info])
            if info.gpu_info
            else None
        ),
    }
    node, created = Node.get_or_create(hostname=info.hostname, defaults=defaults)

    if not created:
        # Update info if node re-registers
        node.url = info.runner_url
        node.total_cores = info.total_cores
        node.memory_total_bytes = info.total_ram_bytes
        node.last_heartbeat = datetime.datetime.now()
        node.status = "online"
        # Update NUMA topology on re-registration as well
        node.set_numa_topology(info.numa_topology)  # Use the setter method
        node.save()
        logger.info(
            f"Runner {info.hostname} re-registered/updated (NUMA: {'Yes' if info.numa_topology else 'No'})."
        )
    else:
        logger.info(
            f"Runner {info.hostname} registered successfully (NUMA: {'Yes' if info.numa_topology else 'No'})."
        )
    return {"message": f"Runner {info.hostname} acknowledged."}


@app.put("/heartbeat/{hostname}")
async def receive_heartbeat(
    hostname: str, data: HeartbeatData
):  # Accept new data model
    node: Node = Node.get_or_none(Node.hostname == hostname)
    if not node:
        logger.warning(f"Heartbeat received from unknown hostname: {hostname}")
        raise HTTPException(status_code=404, detail="Node not registered")

    now = datetime.datetime.now()
    node.last_heartbeat = now
    if node.status != "online":
        logger.info(f"Runner {hostname} came back online.")
        node.status = "online"
    node.cpu_percent = data.cpu_percent
    node.memory_percent = data.memory_percent
    node.memory_used_bytes = data.memory_used_bytes
    node.current_max_temp = data.current_max_temp
    node.current_avg_temp = data.current_avg_temp
    node.gpu_info = (
        json.dumps([gpu.model_dump() for gpu in data.gpu_info])
        if data.gpu_info
        else None
    )
    node.save()

    # --- 1. Process Completed Tasks reported by Runner ---
    if data.killed_tasks:
        logger.info(
            f"Heartbeat from {hostname} reported killed tasks: {data.killed_tasks}"
        )
        for killed_info in data.killed_tasks:
            task_to_update: Task = Task.get_or_none(Task.task_id == killed_info.task_id)
            if task_to_update and task_to_update.status not in [
                "completed",
                "failed",
                "killed",
                "lost",
                "killed_oom",
            ]:
                original_status = task_to_update.status
                new_status = (
                    "killed_oom" if killed_info.reason == "oom" else "failed"
                )  # Or map other reasons
                task_to_update.status = new_status
                task_to_update.exit_code = -9  # Or specific code for OOM
                task_to_update.error_message = f"Killed by runner: {killed_info.reason}"
                task_to_update.completed_at = now
                task_to_update.save()
                logger.warning(
                    f"Task {killed_info.task_id} on {hostname} marked as '{new_status}' (was '{original_status}') due to runner report: {killed_info.reason}"
                )
            elif task_to_update:
                logger.debug(
                    f"Runner reported killed task {killed_info.task_id}, but it was already in final state '{task_to_update.status}'."
                )
            else:
                logger.warning(
                    f"Runner reported killed task {killed_info.task_id}, but task not found in DB."
                )

    # --- 2. Reconcile 'assigning' Tasks ---
    assigning_tasks_on_node: list[Task] = list(
        Task.select().where((Task.assigned_node == node) & (Task.status == "assigning"))
    )
    if assigning_tasks_on_node:
        runner_running_set = set(data.running_tasks)
        logger.debug(
            f"Reconciling {len(assigning_tasks_on_node)} assigning tasks on {hostname}. Runner reports running: {runner_running_set}"
        )
        for task in assigning_tasks_on_node:
            # If runner now reports it running, the /update call should handle it.
            # If runner DOESN'T report it running after a while, suspect assignment.
            if task.task_id not in runner_running_set:
                time_since_submit = now - task.submitted_at
                # Increase suspicion if assigning for too long without confirmation
                if time_since_submit > datetime.timedelta(
                    seconds=HOST_CONFIG.HEARTBEAT_INTERVAL_SECONDS * 3
                ):  # Example threshold
                    if task.assignment_suspicion_count < 2:
                        task.assignment_suspicion_count += 1
                        logger.warning(
                            f"Task {task.task_id} (on {hostname}) still 'assigning' and not reported running. Marked as suspect ({task.assignment_suspicion_count})."
                        )
                        task.save()
                    else:
                        # Mark as failed if suspect count is high
                        task.status = "failed"
                        task.error_message = f"Task assignment failed. Runner {hostname} did not confirm start after multiple checks."
                        task.completed_at = now
                        task.exit_code = -1
                        logger.error(
                            f"Task {task.task_id} (on {hostname}) failed assignment. Marked as failed (suspect {task.assignment_suspicion_count})."
                        )
                        task.save()
            else:
                # If runner reports it running while DB says assigning, clear suspicion
                if task.assignment_suspicion_count > 0:
                    task.assignment_suspicion_count = 0
                    task.save()

    return {"message": "Heartbeat received"}


@app.get("/task/{task_id}/stdout", response_class=PlainTextResponse)
async def get_task_stdout(task_id: int):
    """Retrieves the standard output log file content for a given task."""
    logger.debug(f"Request received for stdout of task {task_id}")
    task: Task = Task.get_or_none(Task.task_id == task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.task_type == "vps":
        raise HTTPException(status_code=400, detail="VPS tasks do not have stdout.")

    log_path = get_secure_log_path(task, "stdout")
    if not log_path:
        raise HTTPException(
            status_code=404,
            detail="Standard output path not found or invalid for this task.",
        )

    try:
        if not os.path.exists(log_path):
            logger.warning(f"Stdout file not found for task {task_id} at {log_path}")
            raise HTTPException(
                status_code=404,
                detail="Standard output file not found (might not be generated yet).",
            )

        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        logger.debug(f"Successfully read stdout for task {task_id}")
        return PlainTextResponse(content=content)

    except FileNotFoundError:
        logger.warning(
            f"Stdout file not found race condition for task {task_id} at {log_path}"
        )
        raise HTTPException(status_code=404, detail="Standard output file not found.")
    except IOError as e:
        logger.error(f"IOError reading stdout for task {task_id} from {log_path}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error reading standard output file: {e}"
        )
    except Exception as e:
        logger.exception(
            f"Unexpected error reading stdout for task {task_id} from {log_path}: {e}"
        )
        raise HTTPException(
            status_code=500, detail="Unexpected error reading standard output file."
        )


@app.get("/task/{task_id}/stderr", response_class=PlainTextResponse)
async def get_task_stderr(task_id: int):
    """Retrieves the standard error log file content for a given task."""
    logger.debug(f"Request received for stderr of task {task_id}")
    task: Task = Task.get_or_none(Task.task_id == task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task entry not found")
    if task.task_type == "vps":
        raise HTTPException(status_code=400, detail="VPS tasks do not have stdout.")

    log_path = get_secure_log_path(task, "stderr")
    if not log_path:
        raise HTTPException(
            status_code=404,
            detail="Standard error path not found or invalid for this task.",
        )

    try:
        if not os.path.exists(log_path):
            logger.warning(f"Stderr file not found for task {task_id} at {log_path}")
            raise HTTPException(
                status_code=404,
                detail="Standard error file not found (might not be generated yet).",
            )

        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        logger.debug(f"Successfully read stderr for task {task_id}")
        return PlainTextResponse(content=content)

    except FileNotFoundError:
        logger.warning(
            f"Stderr file not found race condition for task {task_id} at {log_path}"
        )
        raise HTTPException(status_code=404, detail="Standard error file not found.")
    except IOError as e:
        logger.error(f"IOError reading stderr for task {task_id} from {log_path}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error reading standard error file: {e}"
        )
    except Exception as e:
        logger.exception(
            f"Unexpected error reading stderr for task {task_id} from {log_path}: {e}"
        )
        raise HTTPException(
            status_code=500, detail="Unexpected error reading standard error file."
        )


@app.get("/tasks")
async def get_tasks():
    """Retrieves a list of tasks, including NUMA target and batch ID."""
    logger.debug("Received request to fetch tasks list.")
    try:
        query: Iterable[Task] = (
            Task.select(Task, Node.hostname)
            .join(
                Node, peewee.JOIN.LEFT_OUTER, on=(Task.assigned_node == Node.hostname)
            )
            .where(Task.task_type == "command")
            .order_by(Task.submitted_at.desc())
        )

        tasks_data = []
        for task in query:
            node_hostname = task.assigned_node.hostname if task.assigned_node else None
            tasks_data.append(
                {
                    "task_id": str(task.task_id),  # Keep as string for consistency
                    "batch_id": (
                        str(task.batch_id) if task.batch_id else None
                    ),  # Add batch ID
                    "command": task.command,
                    "arguments": task.get_arguments(),
                    "env_vars": task.get_env_vars(),
                    "required_cores": task.required_cores,
                    "required_gpus": (
                        json.loads(task.required_gpus) if task.required_gpus else []
                    ),
                    "required_memory_bytes": task.required_memory_bytes,
                    "status": task.status,
                    "assigned_node": node_hostname,
                    "target_numa_node_id": task.target_numa_node_id,  # Add target NUMA ID
                    "stdout_path": task.stdout_path,
                    "stderr_path": task.stderr_path,
                    "exit_code": task.exit_code,
                    "error_message": task.error_message,
                    "submitted_at": task.submitted_at,
                    "started_at": task.started_at,
                    "completed_at": task.completed_at,
                    "systemd_unit_name": task.systemd_unit_name,
                    "assignment_suspicion_count": task.assignment_suspicion_count,
                }
            )
        return tasks_data

    except peewee.PeeweeException as e:
        logger.error(f"Database error fetching tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error fetching tasks.")
    except Exception as e:
        logger.error(f"Unexpected error fetching tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unexpected error fetching tasks.")


@app.get("/vps")
async def get_vps():
    """Retrieves a list of tasks, including NUMA target and batch ID."""
    logger.debug("Received request to fetch tasks list.")
    try:
        query: Iterable[Task] = (
            Task.select(Task, Node.hostname)
            .join(
                Node, peewee.JOIN.LEFT_OUTER, on=(Task.assigned_node == Node.hostname)
            )
            .where(Task.task_type == "vps")
            .order_by(Task.submitted_at.desc())
        )

        tasks_data = []
        for task in query:
            node_hostname = task.assigned_node.hostname if task.assigned_node else None
            tasks_data.append(
                {
                    "task_id": str(task.task_id),  # Keep as string for consistency
                    "required_cores": task.required_cores,
                    "required_gpus": (
                        json.loads(task.required_gpus) if task.required_gpus else []
                    ),
                    "required_memory_bytes": task.required_memory_bytes,
                    "status": task.status,
                    "assigned_node": node_hostname,
                    "target_numa_node_id": task.target_numa_node_id,  # Add target NUMA ID
                    "exit_code": task.exit_code,
                    "error_message": task.error_message,
                    "submitted_at": task.submitted_at,
                    "started_at": task.started_at,
                    "completed_at": task.completed_at,
                }
            )
        return tasks_data

    except peewee.PeeweeException as e:
        logger.error(f"Database error fetching tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Database error fetching tasks.")
    except Exception as e:
        logger.error(f"Unexpected error fetching tasks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unexpected error fetching tasks.")


@app.post("/submit", status_code=202)
async def submit_task(req: TaskRequest):
    """Accepts a task request and dispatches it to one or more target nodes/NUMA nodes."""
    if req.task_type not in {"command", "vps"}:
        raise HTTPException(
            status_code=400,
            detail="Invalid task type. Only 'command' and 'vps' are supported.",
        )
    elif req.task_type == "vps":
        req.command = ""
        req.arguments = []  # VPS tasks don't need a command or arguments
        req.env_vars = {}
    created_task_ids = []
    failed_targets = []
    first_task_id_for_batch = None

    output_dir = os.path.join(HOST_CONFIG.SHARED_DIR, "task_outputs")
    errors_dir = os.path.join(HOST_CONFIG.SHARED_DIR, "task_errors")
    try:
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(errors_dir, exist_ok=True)
    except OSError as e:
        logger.error(
            f"Cannot create output/error directories in {HOST_CONFIG.SHARED_DIR}: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: Cannot create log directories.",
        )

    if req.container_name == "NULL":
        if req.task_type == "vps":
            raise HTTPException(
                status_code=400,
                detail="VPS tasks require a Docker container.",
            )
        task_container_name = None
    else:
        task_container_name = req.container_name or HOST_CONFIG.DEFAULT_CONTAINER_NAME
    task_docker_image_tag = f"hakuriver/{task_container_name}:base"
    task_privileged = (
        HOST_CONFIG.TASKS_PRIVILEGED if req.privileged is None else req.privileged
    )
    task_additional_mounts = (
        HOST_CONFIG.ADDITIONAL_MOUNTS
        if req.additional_mounts is None
        else req.additional_mounts
    )

    # --- Loop through each target specified in the request ---
    targets = req.targets
    if not targets:
        if req.required_gpus:
            raise HTTPException(
                status_code=400,
                detail="No target node specified for GPU task is not allowed.",
            )
        targets = find_suitable_node(req.required_cores).hostname
        targets = [targets]

    required_gpus = req.required_gpus or [[] for _ in targets]

    if len(targets) > 1 and req.task_type == "vps":
        raise HTTPException(
            status_code=400,
            detail="VPS tasks cannot be submitted to multiple targets.",
        )

    for target_str, target_gpus in zip(targets, required_gpus, strict=True):
        target_numa_id: int | None = None
        parts = target_str.split(":")
        target_hostname = parts[0]
        if len(parts) > 1:
            try:
                target_numa_id = int(parts[1])
                if target_numa_id < 0:
                    raise ValueError("NUMA ID cannot be negative")
            except ValueError:
                logger.warning(
                    f"Invalid NUMA ID format in target '{target_str}'. Skipping this target."
                )
                failed_targets.append(
                    {"target": target_str, "reason": "Invalid NUMA ID format"}
                )
                continue

        # --- Find and Validate Node ---
        node: Node = Node.get_or_none(Node.hostname == target_hostname)
        if not node:
            logger.warning(
                f"Target node '{target_hostname}' not registered. Skipping target '{target_str}'."
            )
            failed_targets.append(
                {"target": target_str, "reason": "Node not registered"}
            )
            continue
        if node.status != "online":
            logger.warning(
                f"Target node '{target_hostname}' is not online (status: {node.status}). Skipping target '{target_str}'."
            )
            failed_targets.append(
                {"target": target_str, "reason": f"Node status is {node.status}"}
            )
            continue

        # --- Validate NUMA Target (if specified) ---
        node_topology = node.get_numa_topology()
        if target_numa_id is not None:
            if node_topology is None:
                logger.warning(
                    f"Target '{target_str}' specified NUMA ID {target_numa_id}, but node '{target_hostname}' has no NUMA topology reported. Skipping."
                )
                failed_targets.append(
                    {"target": target_str, "reason": "Node has no NUMA topology"}
                )
                continue
            # Check if the NUMA ID is valid within the reported topology (keys are integers after json.loads)
            if target_numa_id not in node_topology:
                logger.warning(
                    f"Target '{target_str}' specified NUMA ID {target_numa_id}, which is invalid for node '{target_hostname}' (Valid: {list(node_topology.keys())}). Skipping."
                )
                failed_targets.append(
                    {
                        "target": target_str,
                        "reason": f"Invalid NUMA ID for node (Valid: {list(node_topology.keys())})",
                    }
                )
                continue
            # Optional: Could add NUMA-specific resource checks here later

        gpu_info = node.get_gpu_info()
        if gpu_info and target_gpus:
            # Check if the requested GPUs are valid for the node
            invalid_gpus = [
                gpu_id
                for gpu_id in target_gpus
                if gpu_id >= len(gpu_info) or gpu_id < 0
            ]
            if invalid_gpus:
                logger.warning(
                    f"Invalid GPU IDs {invalid_gpus} specified for target '{target_str}' on node '{target_hostname}'. Skipping."
                )
                failed_targets.append(
                    {
                        "target": target_str,
                        "reason": f"Invalid GPU IDs: {invalid_gpus}",
                    }
                )
                continue
            if set(target_gpus) - get_node_available_gpus(node) != set():
                logger.warning(
                    f"Requested GPUs {target_gpus} for target '{target_str}' on node '{target_hostname}' are not available. Skipping."
                )
                failed_targets.append(
                    {
                        "target": target_str,
                        "reason": "Requested GPUs not available",
                    }
                )
                continue

        # --- Resource Check (Simple total cores on node for now) ---
        available_cores = get_node_available_cores(node)
        if req.required_cores and available_cores < req.required_cores:
            logger.warning(
                f"Insufficient cores on node '{target_hostname}' ({available_cores} avail < {req.required_cores} req). Skipping target '{target_str}'."
            )
            failed_targets.append(
                {"target": target_str, "reason": "Insufficient available cores"}
            )
            continue

        available_memory = get_node_available_memory(node)
        if req.required_memory_bytes and available_memory < req.required_memory_bytes:
            logger.warning(
                f"Insufficient memory on node '{target_hostname}' ({available_memory} avail < {req.required_memory_bytes} req). Skipping target '{target_str}'."
            )
            failed_targets.append(
                {
                    "target": target_str,
                    "reason": "Insufficient available memory",
                }
            )
            continue

        # --- Generate ID and Create Task Record ---
        task_id = snowflake()
        if first_task_id_for_batch is None:
            first_task_id_for_batch = task_id  # Use first task's ID as the batch ID
        current_batch_id = first_task_id_for_batch

        stdout_path = os.path.join(output_dir, f"{task_id}.out")
        stderr_path = os.path.join(errors_dir, f"{task_id}.err")
        unit_name = f"hakuriver-task-{task_id}.scope"

        try:
            # Use peewee transaction for safety if multiple operations needed per task
            with db.atomic():
                task = Task.create(
                    task_id=task_id,
                    task_type=req.task_type,
                    batch_id=current_batch_id,
                    arguments="",  # Will be set below
                    env_vars="",  # Will be set below
                    command=req.command,
                    required_cores=req.required_cores,
                    required_gpus=json.dumps(target_gpus),
                    required_memory_bytes=req.required_memory_bytes,  # Store memory limit
                    assigned_node=node,
                    status="assigning",
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    submitted_at=datetime.datetime.now(),
                    systemd_unit_name=unit_name,
                    target_numa_node_id=target_numa_id,
                    container_name=task_container_name,
                    docker_image_name=task_docker_image_tag,
                    docker_privileged=task_privileged,
                    docker_mount_dirs=json.dumps(task_additional_mounts),
                )
            task.set_arguments(req.arguments)
            task.set_env_vars(req.env_vars)
            task.save()
            logger.info(
                f"Task {task_id} created, "
                f"Container: {task_container_name}, "
                f"Req Cores: {req.required_cores}, "
                f"Req Mem: {req.required_memory_bytes // 1e6 if req.required_memory_bytes else 'N/A'}MB. "
                f"Assigning to {node.hostname} (Unit: {unit_name})."
            )

        except Exception as e:
            logger.exception(
                f"Failed to create task record in database for target '{target_str}': {e}"
            )
            failed_targets.append(
                {"target": target_str, "reason": "Database error during task creation"}
            )
            continue  # Skip dispatching this task

        # --- Prepare Runner Payload and Dispatch ---
        task_info_for_runner = TaskInfoForRunner(
            task_id=task_id,
            task_type=req.task_type,
            command=req.command,
            arguments=req.arguments,
            env_vars=req.env_vars,
            required_cores=req.required_cores,
            required_gpus=target_gpus,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            required_memory_bytes=req.required_memory_bytes,
            target_numa_node_id=target_numa_id,  # Pass the specific target NUMA ID
            docker_image_name=task_docker_image_tag,  # Use the determined image tag
            docker_privileged=task_privileged,  # Use the determined privileged setting
            docker_additional_mounts=task_additional_mounts,
        )

        if req.task_type == "vps":
            # VPS tasks are dispatched differently (e.g., to a different runner or endpoint)
            asyncio.create_task(send_vps_task_to_runner(node.url, task_info_for_runner))
        else:
            asyncio.create_task(send_task_to_runner(node.url, task_info_for_runner))
        created_task_ids.append(str(task_id))  # Add successfully launched task ID

    # --- Construct Final Response ---
    if not created_task_ids and failed_targets:
        # If all targets failed, return an error
        detail = f"Failed to schedule task for any target. Failures: {failed_targets}"
        logger.error(
            f"Task submission failed for all targets: {req.targets}. Failures: {failed_targets}"
        )
        raise HTTPException(status_code=503, detail=detail)
    elif failed_targets:
        # Partial success
        message = f"Task batch submitted. {len(created_task_ids)} tasks created. Some targets failed."
        logger.warning(
            f"Partial task batch submission. Succeeded: {created_task_ids}. Failed targets: {failed_targets}"
        )
        return {
            "message": message,
            "task_ids": created_task_ids,
            "failed_targets": failed_targets,
        }
    else:
        # Full success
        message = (
            f"Task batch submitted successfully. {len(created_task_ids)} tasks created."
        )
        logger.info(f"Task batch submission successful. Task IDs: {created_task_ids}")
        return {"message": message, "task_ids": created_task_ids}


@app.post("/update")
async def update_task_status(update: TaskStatusUpdate):
    logger.info(f"Received status update for task {update.task_id}: {update.status}")

    task: Task = Task.get_or_none(Task.task_id == update.task_id)
    if not task:
        logger.warning(
            f"Received update for unknown task ID: {update.task_id}. Ignoring."
        )
        return {"message": "Task ID not recognized"}

    # Prevent overwriting final states accidentally?
    final_states = ["completed", "failed", "killed", "lost"]
    if task.status in final_states and update.status not in final_states:
        logger.warning(
            f"Ignoring status update '{update.status}' "
            f"for task {update.task_id} which is already in final state '{task.status}'."
        )
        return {"message": "Task already in a final state"}

    task.status = update.status
    task.exit_code = update.exit_code
    task.error_message = update.message
    if update.started_at and not task.started_at:
        task.started_at = update.started_at
        logger.info(f"Task {update.task_id} confirmed started at {update.started_at}")
    if update.completed_at:
        task.completed_at = update.completed_at
    # Ensure completion time is set for final states reported by runner
    elif update.status in final_states and not task.completed_at:
        task.completed_at = datetime.datetime.now()

    if task.assignment_suspicion_count > 0:
        logger.info(
            f"Clearing assignment suspicion for task {task.task_id} "
            f"due to status update '{update.status}'."
        )
        task.assignment_suspicion_count = 0

    task.save()
    logger.info(f"Task {update.task_id} status updated to {update.status} in DB.")

    return {"message": "Task status updated successfully."}


@app.get("/status/{task_id}")
async def get_task_status(task_id: int):
    try:
        # Task ID is now BigInt/Snowflake
        task_uuid = int(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Task ID format.")

    query = (
        Task.select(Task, Node.hostname.alias("node_hostname"))
        .left_outer_join(Node, on=(Task.assigned_node == Node.hostname))  # Join on PK
        .where(Task.task_id == task_uuid)
        .first()
    )

    if not query:
        raise HTTPException(status_code=404, detail="Task id not found")
    task: Task = query  # The query itself is the Task object here

    response = {
        "task_id": str(task.task_id),  # Return as string
        "batch_id": str(task.batch_id) if task.batch_id else None,  # Add batch ID
        "command": task.command,
        "arguments": task.get_arguments(),
        "env_vars": task.get_env_vars(),
        "required_cores": task.required_cores,
        "required_gpus": json.loads(task.required_gpus) if task.required_gpus else [],
        "required_memory_bytes": task.required_memory_bytes,
        "status": task.status,
        "assigned_node": (
            task.node_hostname if hasattr(task, "node_hostname") else None
        ),  # Use alias if joined
        "target_numa_node_id": task.target_numa_node_id,  # Add target NUMA ID
        "stdout_path": task.stdout_path,
        "stderr_path": task.stderr_path,
        "exit_code": task.exit_code,
        "error_message": task.error_message,
        "submitted_at": task.submitted_at.isoformat() if task.submitted_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "systemd_unit_name": task.systemd_unit_name,
        "assignment_suspicion_count": task.assignment_suspicion_count,
    }
    return response


# Kill endpoint and helper (logic same, use logger)
async def send_kill_to_runner(runner_url: str, task_id: int, unit_name: str | None):
    if not unit_name:
        logger.warning(
            f"Cannot send kill for task {task_id} to {runner_url}, systemd unit name unknown."
        )
        return

    logger.info(
        f"Sending kill request for task {task_id} (Unit: {unit_name}) to runner {runner_url}"
    )
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{runner_url}/kill",
                json={"task_id": task_id, "unit_name": unit_name},
                timeout=10.0,
            )
            response.raise_for_status()
            logger.info(
                f"Kill command for task {task_id} acknowledged by runner {runner_url}."
            )
    except httpx.RequestError as e:
        logger.error(
            f"Failed to send kill command for task {task_id} to {runner_url}: {e}"
        )
        # Update task message in DB? Host already marked 'killed'.

        task: Task = Task.get_or_none(Task.task_id == task_id)
        if task and task.status == "killed":
            task.error_message += f" | Runner unreachable for kill confirmation: {e}"
            task.save()
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Runner {runner_url} failed kill for "
            f"task {task_id}: {e.response.status_code} - {e.response.text}"
        )

        task = Task.get_or_none(Task.task_id == task_id)
        if task and task.status == "killed":
            task.error_message += (
                f" | Runner error during kill: {e.response.status_code}"
            )
            task.save()
    except Exception as e:
        logger.exception(
            f"Unexpected error sending kill for task {task_id} to {runner_url}: {e}"
        )


async def send_pause_to_runner(runner_url: str, task_id: int, unit_name: str | None):
    if not unit_name:
        logger.warning(
            f"Cannot send pause for task {task_id} to {runner_url}, systemd unit name unknown."
        )
        return

    logger.info(
        f"Sending pause request for task {task_id} (Unit: {unit_name}) to runner {runner_url}"
    )
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{runner_url}/pause",
                json={"task_id": task_id, "unit_name": unit_name},
                timeout=10.0,
            )
            response.raise_for_status()
            logger.info(
                f"Pause command for task {task_id} acknowledged by runner {runner_url}."
            )
            return "Pause command sent successfully."
    except httpx.RequestError as e:
        logger.error(
            f"Failed to send pause command for task {task_id} to {runner_url}: {e}"
        )
        return "Failed to send pause command."
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Runner {runner_url} failed pause for "
            f"task {task_id}: {e.response.status_code} - {e.response.text}"
        )
        return "Runner error during pause command."
    except Exception as e:
        logger.exception(
            f"Unexpected error sending pause for task {task_id} to {runner_url}: {e}"
        )
        return "Unexpected error sending pause command."


async def send_resume_to_runner(runner_url: str, task_id: int, unit_name: str | None):
    if not unit_name:
        logger.warning(
            f"Cannot send resume for task {task_id} to {runner_url}, systemd unit name unknown."
        )
        return

    logger.info(
        f"Sending resume request for task {task_id} (Unit: {unit_name}) to runner {runner_url}"
    )
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{runner_url}/resume",
                json={"task_id": task_id, "unit_name": unit_name},
                timeout=10.0,
            )
            response.raise_for_status()
            logger.info(
                f"Resume command for task {task_id} acknowledged by runner {runner_url}."
            )
            return "Resume command sent successfully."
    except httpx.RequestError as e:
        logger.error(
            f"Failed to send resume command for task {task_id} to {runner_url}: {e}"
        )
        return "Failed to send resume command."
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Runner {runner_url} failed resume for "
            f"task {task_id}: {e.response.status_code} - {e.response.text}"
        )
        return "Runner error during resume command."
    except Exception as e:
        logger.exception(
            f"Unexpected error sending resume for task {task_id} to {runner_url}: {e}"
        )
        return "Unexpected error sending resume command."


@app.post("/kill/{task_id}", status_code=202)
async def request_kill_task(task_id: int):
    try:
        task_uuid = int(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Task ID format.")

    task: Task = (
        Task.select(Task, Node)
        .join(
            Node, peewee.JOIN.LEFT_OUTER, on=(Task.assigned_node == Node.hostname)
        )  # Use LEFT JOIN
        .where(Task.task_id == task_uuid)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    # Check if task is in a state that can be killed
    killable_states = ["pending", "assigning", "running"]
    if task.status not in killable_states:
        raise HTTPException(
            status_code=409, detail=f"Task cannot be killed (state: {task.status})"
        )

    original_status = task.status
    unit_name = task.systemd_unit_name  # Get the stored unit name

    task.status = "killed"  # Mark as killed immediately in DB
    task.error_message = "Kill requested by user."
    task.completed_at = datetime.datetime.now()  # Set completion time for killed tasks
    task.save()
    logger.info(f"Marked task {task_id} as 'killed' in DB (was {original_status}).")

    # If the task was actually running on an online node, tell the runner
    if (
        original_status == "running"
        and task.assigned_node
        and task.assigned_node.status == "online"
    ):
        runner_url = task.assigned_node.url
        logger.info(
            "Requesting kill confirmation from runner "
            f"{task.assigned_node.hostname} for task {task_id}"
        )
        asyncio.create_task(send_kill_to_runner(runner_url, task_id, unit_name))
    else:
        logger.info(
            "No kill signal sent to runner for task "
            f"{task_id} (was not running or node offline/unknown)."
        )

    return {"message": f"Kill requested for task {task_id}. Task marked as killed."}


@app.post("/command/{task_id}/{command}")
async def send_command_to_task(task_id: int, command: str):
    """Send a command to a task."""
    logger.info(f"Received command '{command}' for task {task_id}")
    task: Task = Task.get_or_none(Task.task_id == task_id)
    if not task:
        logger.warning(f"Received command for unknown task ID: {task_id}. Ignoring.")
        raise HTTPException(status_code=404, detail="Task id not found")
    match (command, task.status):
        case ("pause", "running"):
            unit_name = task.systemd_unit_name
            response = await send_pause_to_runner(
                task.assigned_node.url, task_id, unit_name
            )
            return {"message": f"Pause for task {task_id} sent to runner: {response}"}
        case ("resume", "paused"):
            unit_name = task.systemd_unit_name
            response = await send_resume_to_runner(
                task.assigned_node.url, task_id, unit_name
            )
            return {"message": f"Resume for task {task_id} sent to runner: {response}"}
        case _:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid command or task state: {command} for {task.status}",
            )


@app.get("/nodes")
async def get_nodes_status():
    nodes_status = []
    nodes: list[Node] = list(Node.select())
    online_nodes = {n.hostname: n for n in nodes if n.status == "online"}
    cores_in_use = defaultdict(int)
    if online_nodes:
        # Calculate cores in use for online nodes
        running_tasks_usage = (
            Task.select(
                Task.assigned_node,  # This selects the Node object (or its PK)
                peewee.fn.SUM(Task.required_cores).alias("used_cores"),
            )
            .where(
                (Task.status.in_(["running", "assigning"]))
                & (
                    Task.assigned_node << list(online_nodes.values())
                )  # Filter by Node objects
            )
            .group_by(Task.assigned_node)
        )
        for usage in running_tasks_usage:
            # Access the joined Node object directly
            if usage.assigned_node:
                cores_in_use[usage.assigned_node.hostname] = usage.used_cores

    for node in nodes:
        available = 0
        used = "N/A"
        if node.status == "online":
            used = cores_in_use.get(node.hostname, 0)
            available = node.total_cores - used

        nodes_status.append(
            {
                "hostname": node.hostname,
                "url": node.url,
                "total_cores": node.total_cores,
                "cores_in_use": used,
                "available_cores": available,
                "status": node.status,
                "last_heartbeat": (
                    node.last_heartbeat.isoformat() if node.last_heartbeat else None
                ),
                "numa_topology": node.get_numa_topology(),  # Parse JSON from DB
                "gpu_info": node.get_gpu_info(),  # Parse JSON from DB
            }
        )
    return nodes_status


@app.get("/health")
async def get_cluster_health(
    hostname: str | None = Query(
        None, description="Optional: Filter by specific hostname"
    )
):
    """Provides the last known health status (heartbeat data) and NUMA info for nodes."""
    logger.debug(f"Received health request. Filter hostname: {hostname}")
    try:
        if hostname and hostname in health_datas:
            return [health_datas[-1][hostname]]
        return {
            "nodes": [
                [v for k, v in data.items() if k != "aggregate"]
                for data in health_datas
            ],
            "aggregate": [data["aggregate"] for data in health_datas],
        }

    except peewee.PeeweeException as e:
        logger.error(f"Database error fetching node health: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Database error fetching node health."
        )
    except Exception as e:
        logger.error(f"Unexpected error fetching node health: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Unexpected error fetching node health."
        )


# --- Background Tasks (Logic same, use logger) ---
health_datas = []


async def collate_health_data():
    global health_datas
    """
    Calculate aggregate health data for all nodes.
    Record history data as well (keep recent 60sec, 1s intervals).
    """
    while True:
        await asyncio.sleep(1)
        new_node_health = {}
        aggregate_health = {
            "totalNodes": 0,
            "onlineNodes": 0,
            "totalCores": 0,
            "totalMemBytes": 0,
            "usedMemBytes": 0,
            "avgCpuPercent": 0,
            "avgMemPercent": 0,
            "maxAvgCpuTemp": 0,
            "maxMaxCpuTemp": 0,
            "lastUpdated": datetime.datetime.now().isoformat(),
        }
        for node in Node.select():
            new_node_health[node.hostname] = {
                "hostname": node.hostname,
                "status": node.status,
                "last_heartbeat": (
                    node.last_heartbeat.isoformat() if node.last_heartbeat else None
                ),
                "cpu_percent": node.cpu_percent,
                "memory_percent": node.memory_percent,
                "memory_used_bytes": node.memory_used_bytes,
                "memory_total_bytes": node.memory_total_bytes,
                "total_cores": node.total_cores,
                "numa_topology": node.get_numa_topology(),
                "current_avg_temp": node.current_avg_temp,
                "current_max_temp": node.current_max_temp,
                "gpu_info": node.get_gpu_info(),
            }
            aggregate_health["totalNodes"] += 1
            if node.status == "online":
                aggregate_health["onlineNodes"] += 1
            aggregate_health["totalCores"] += node.total_cores or 0
            aggregate_health["totalMemBytes"] += node.memory_total_bytes or 0
            aggregate_health["usedMemBytes"] += node.memory_used_bytes or 0
            aggregate_health["avgCpuPercent"] += (node.cpu_percent or 0) * (
                node.total_cores or 0
            )
            if node.last_heartbeat.isoformat() > aggregate_health["lastUpdated"]:
                aggregate_health["lastUpdated"] = node.last_heartbeat.isoformat()
            aggregate_health["maxAvgCpuTemp"] = max(
                aggregate_health["maxAvgCpuTemp"], node.current_avg_temp
            )
            aggregate_health["maxMaxCpuTemp"] = max(
                aggregate_health["maxMaxCpuTemp"], node.current_max_temp
            )
        aggregate_health["avgCpuPercent"] /= max(1, aggregate_health["totalCores"])
        aggregate_health["avgMemPercent"] = (
            aggregate_health["usedMemBytes"]
            / max(1, aggregate_health["totalMemBytes"])
            * 100
        )
        new_node_health["aggregate"] = aggregate_health
        health_datas.append(new_node_health)
        health_datas = health_datas[-60:]  # Keep only the last 60 seconds of data


async def check_dead_runners():
    while True:
        await asyncio.sleep(HOST_CONFIG.CLEANUP_CHECK_INTERVAL_SECONDS)
        # Calculate timeout threshold based on current time
        timeout_threshold = datetime.datetime.now() - datetime.timedelta(
            seconds=HOST_CONFIG.HEARTBEAT_INTERVAL_SECONDS
            * HOST_CONFIG.HEARTBEAT_TIMEOUT_FACTOR
        )

        # Find nodes marked 'online' whose last heartbeat is older than the threshold
        dead_nodes_query = Node.select().where(
            (Node.status == "online") & (Node.last_heartbeat < timeout_threshold)
        )
        # Execute query to get the list
        dead_nodes: list[Node] = list(dead_nodes_query)

        if not dead_nodes:
            continue

        for node in dead_nodes:
            logger.warning(
                f"Runner {node.hostname} missed heartbeat threshold "
                f"(last seen: {node.last_heartbeat}). Marking as offline."
            )
            node.status = "offline"
            node.save()

            # Find tasks that were 'running' or 'assigning' on this node
            tasks_to_fail: list[Task] = Task.select().where(
                (Task.assigned_node == node)
                & (Task.status.in_(["running", "assigning"]))
            )
            for task in tasks_to_fail:
                logger.warning(
                    f"Marking task {task.task_id} as 'lost' "
                    f"because node {node.hostname} went offline."
                )
                task.status = "lost"
                task.error_message = (
                    f"Node {node.hostname} went offline (heartbeat timeout)."
                )
                task.completed_at = datetime.datetime.now()
                task.exit_code = -1  # Indicate abnormal termination
                task.save()


async def startup_event():
    # Initialize DB using path from config BEFORE starting app
    initialize_database(HOST_CONFIG.DB_FILE)
    logger.info("Host server starting up.")

    # refresh default Container

    default_container_name = HOST_CONFIG.DEFAULT_CONTAINER_NAME
    container_tar_dir = HOST_CONFIG.CONTAINER_DIR
    initial_base_image = HOST_CONFIG.INITIAL_BASE_IMAGE

    if not os.path.isdir(container_tar_dir):
        logger.warning(
            f"Shared directory '{container_tar_dir}' does not exist. Creating..."
        )
        try:
            os.makedirs(container_tar_dir, exist_ok=True)
            logger.info(f"Shared directory created: {container_tar_dir}")
        except OSError as e:
            logger.critical(
                f"FATAL: Cannot create shared directory '{container_tar_dir}': {e}. Host cannot start."
            )

    # Check if any tarball for the default container name exists
    shared_tars = docker_utils.list_shared_container_tars(
        container_tar_dir, default_container_name
    )

    if not shared_tars:
        logger.info(
            f"No shared tarball found for default container '{default_container_name}'. "
            f"Attempting to create from initial image '{initial_base_image}'."
        )
        # Call the utility to create tarball from initial image
        docker_utils.create_container(
            image_name=initial_base_image,
            container_name=default_container_name,
        )
        tarball_path = docker_utils.create_container_tar(
            source_container_name=default_container_name,
            hakuriver_container_name=default_container_name,
            container_tar_dir=container_tar_dir,
        )
        if tarball_path:
            logger.info(
                f"Default container tarball created successfully at {tarball_path}. "
                "Runners can now sync this base image."
            )
        else:
            logger.error(
                f"Failed to create default container tarball from '{initial_base_image}'. "
                "Runners may not be able to fetch the base image."
            )
    else:
        logger.info(
            f"Found existing shared tarball for default container '{default_container_name}' "
        )

    # Start background task AFTER app starts running
    asyncio.create_task(check_dead_runners())
    asyncio.create_task(collate_health_data())


app.add_event_handler("startup", startup_event)


async def shutdown_event():
    if not db.is_closed():
        db.close()
    logger.info("Host server shutting down.")


app.add_event_handler("shutdown", shutdown_event)
