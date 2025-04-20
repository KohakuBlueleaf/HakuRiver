import asyncio
import datetime
import os
import json
import re
from collections import defaultdict
from typing import Iterable

import peewee
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, field_validator

from hakuriver.utils.snowflake import Snowflake
from hakuriver.utils.logger import logger
from hakuriver.utils.config_loader import settings
from hakuriver.db.models import db, Node, Task, initialize_database


# --- Configuration from settings ---
class HostConfig:
    # Network
    HOST_BIND_IP = settings["network"]["host_bind_ip"]
    HOST_PORT = settings["network"]["host_port"]
    # Paths
    SHARED_DIR = settings["paths"]["shared_dir"]
    # Database
    DB_FILE = settings["database"]["db_file"]
    # Timing
    HEARTBEAT_INTERVAL_SECONDS = settings["timing"]["heartbeat_interval"]
    HEARTBEAT_TIMEOUT_FACTOR = settings["timing"]["heartbeat_timeout_factor"]
    CLEANUP_CHECK_INTERVAL_SECONDS = settings["timing"]["cleanup_check_interval"]


HostConfig = HostConfig()  # Create an instance of the dataclass
snowflake = Snowflake()


# --- Pydantic Models (remain the same) ---
class RunnerInfo(BaseModel):
    hostname: str
    total_cores: int
    total_ram_bytes: int
    runner_url: str
    numa_topology: dict | None = None


class TaskRequest(BaseModel):
    command: str
    arguments: list[str] = Field(default_factory=list)
    env_vars: dict[str, str] = Field(default_factory=dict)
    required_cores: int = Field(
        default=1, ge=0, description="Number of CPU cores required"
    )
    required_memory_bytes: int | None = Field(
        default=None, ge=0, description="Memory limit in bytes"
    )
    targets: list[str] | None = Field(
        default=None,
        min_length=0,
        description='List of targets, e.g., ["host1", "host2:0", "host1:1"]',
    )

    @field_validator("targets")
    @classmethod
    def validate_targets_format(cls, v):
        if v is None:
            return v
        pattern = r"^[a-zA-Z0-9.-]+(:[0-9]+)?$"  # hostname[:numa_id]
        for target in v:
            if not re.match(pattern, target):
                raise ValueError(
                    f"Invalid target format: '{target}'. Use 'hostname' or 'hostname:numa_id'."
                )
        return v


class TaskInfoForRunner(BaseModel):
    task_id: int
    command: str
    arguments: list[str]
    env_vars: dict[str, str]
    required_cores: int
    stdout_path: str
    stderr_path: str
    required_memory_bytes: int | None = None
    target_numa_node_id: int | None = None


class TaskStatusUpdate(BaseModel):
    task_id: int
    status: str
    exit_code: int | None = None
    message: str | None = None
    started_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None = None


class HeartbeatKilledTaskInfo(BaseModel):
    task_id: int
    reason: str  # e.g., "oom", "killed_by_host"


class HeartbeatData(BaseModel):
    running_tasks: list[int] = Field(default_factory=list)
    killed_tasks: list[HeartbeatKilledTaskInfo] = Field(default_factory=list)
    cpu_percent: float | None = None
    memory_percent: float | None = None
    memory_used_bytes: int | None = None
    memory_total_bytes: int | None = None


# --- FastAPI App ---
app = FastAPI(title="HakuRiver Cluster Manager")


# --- Helper Functions (Logic remains the same, just use logger) ---
def get_node_available_cores(node: Node) -> int:
    running_tasks_cores = (
        Task.select(peewee.fn.SUM(Task.required_cores))
        .where((Task.assigned_node == node) & (Task.status == "running"))
        .scalar()
        or 0
    )
    return node.total_cores - running_tasks_cores


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
            # task.status = 'running' # Optimistic - Reverted
            # task.save()
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
        base_dir = os.path.join(HostConfig.SHARED_DIR, "task_outputs")
        db_path = task.stdout_path
    elif log_type == "stderr":
        base_dir = os.path.join(HostConfig.SHARED_DIR, "task_errors")
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
                    seconds=HostConfig.HEARTBEAT_INTERVAL_SECONDS * 3
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
    task = Task.get_or_none(Task.task_id == task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

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
    task = Task.get_or_none(Task.task_id == task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

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


@app.post("/submit", status_code=202)
async def submit_task(req: TaskRequest):
    """Accepts a task request and dispatches it to one or more target nodes/NUMA nodes."""
    created_task_ids = []
    failed_targets = []
    current_batch_id = None
    first_task_id_for_batch = None

    output_dir = os.path.join(HostConfig.SHARED_DIR, "task_outputs")
    errors_dir = os.path.join(HostConfig.SHARED_DIR, "task_errors")
    try:
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(errors_dir, exist_ok=True)
    except OSError as e:
        logger.error(
            f"Cannot create output/error directories in {HostConfig.SHARED_DIR}: {e}"
        )
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: Cannot create log directories.",
        )

    # --- Loop through each target specified in the request ---
    targets = req.targets
    if not targets:
        targets = find_suitable_node(req.required_cores).hostname
        targets = [targets]
    for target_str in targets:
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

        # --- Resource Check (Simple total cores on node for now) ---
        available_cores = get_node_available_cores(node)
        if available_cores < req.required_cores:
            logger.warning(
                f"Insufficient cores on node '{target_hostname}' ({available_cores} avail < {req.required_cores} req). Skipping target '{target_str}'."
            )
            failed_targets.append(
                {"target": target_str, "reason": "Insufficient available cores"}
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
                    arguments="",  # Will be set below
                    env_vars="",  # Will be set below
                    command=req.command,
                    required_cores=req.required_cores,
                    required_memory_bytes=req.required_memory_bytes,  # Store memory limit
                    assigned_node=node,
                    status="assigning",
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    submitted_at=datetime.datetime.now(),
                    systemd_unit_name=unit_name,
                    target_numa_node_id=target_numa_id,
                )
            task.set_arguments(req.arguments)
            task.set_env_vars(req.env_vars)
            task.save()
            logger.info(
                f"Task {task_id} created, "
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
            command=req.command,
            arguments=req.arguments,
            env_vars=req.env_vars,
            required_cores=req.required_cores,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            required_memory_bytes=req.required_memory_bytes,
            target_numa_node_id=target_numa_id,  # Pass the specific target NUMA ID
        )

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
        raise HTTPException(status_code=404, detail="Task not found")
    task: Task = query  # The query itself is the Task object here

    response = {
        "task_id": str(task.task_id),  # Return as string
        "batch_id": str(task.batch_id) if task.batch_id else None,  # Add batch ID
        "command": task.command,
        "arguments": task.get_arguments(),
        "env_vars": task.get_env_vars(),
        "required_cores": task.required_cores,
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
            f"Requesting kill confirmation from runner "
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
        raise HTTPException(status_code=404, detail="Task not found")
    match (command, task.status):
        case ("pause", "running"):
            unit_name = task.systemd_unit_name
            response = await send_pause_to_runner(task.assigned_node.url, task_id, unit_name)
            return {"message": f"Pause for task {task_id} sent to runner: {response}"}
        case ("resume", "paused"):
            unit_name = task.systemd_unit_name
            response = await send_resume_to_runner(task.assigned_node.url, task_id, unit_name)
            return {"message": f"Resume for task {task_id} sent to runner: {response}"}
        case _:
            raise HTTPException(
                status_code=400, detail=f"Invalid command or task state: {command} for {task.status}"
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
        query: Iterable[Node] = Node.select()
        if hostname:
            query = query.where(Node.hostname == hostname)

        nodes_health = []
        for node in query:
            nodes_health.append(
                {
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
                    "url": node.url,
                    "numa_topology": node.get_numa_topology(),  # Parse JSON from DB
                }
            )
        if hostname and not nodes_health:
            raise HTTPException(
                status_code=404, detail=f"No health data found for hostname: {hostname}"
            )
        return nodes_health

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
async def check_dead_runners():
    while True:
        await asyncio.sleep(HostConfig.CLEANUP_CHECK_INTERVAL_SECONDS)
        # Calculate timeout threshold based on current time
        timeout_threshold = datetime.datetime.now() - datetime.timedelta(
            seconds=HostConfig.HEARTBEAT_INTERVAL_SECONDS
            * HostConfig.HEARTBEAT_TIMEOUT_FACTOR
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
    initialize_database(HostConfig.DB_FILE)
    logger.info("Host server starting up.")
    # Start background task AFTER app starts running
    asyncio.create_task(check_dead_runners())


app.add_event_handler("startup", startup_event)


async def shutdown_event():
    if not db.is_closed():
        db.close()
    logger.info("Host server shutting down.")


app.add_event_handler("shutdown", shutdown_event)
