# host_app.py
from ast import arguments
import json
import uuid
import asyncio
import datetime
import os
from collections import defaultdict

import peewee
import uvicorn
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

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


# --- Pydantic Models (remain the same) ---
class RunnerInfo(BaseModel):
    hostname: str
    total_cores: int
    runner_url: str


class TaskRequest(BaseModel):
    command: str
    arguments: list[str] = Field(default_factory=list)
    env_vars: dict[str, str] = Field(default_factory=dict)
    required_cores: int


class TaskInfoForRunner(BaseModel):
    task_id: str
    command: str
    arguments: list[str]
    env_vars: dict[str, str]
    required_cores: int
    stdout_path: str
    stderr_path: str


class TaskStatusUpdate(BaseModel):
    task_id: str
    status: str
    exit_code: int | None = None
    message: str | None = None
    started_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None = None


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


# --- API Endpoints (Logic remains the same, use logger) ---


@app.post("/register")
async def register_runner(info: RunnerInfo):

    node: Node
    node, created = Node.get_or_create(
        hostname=info.hostname,
        defaults={
            "url": info.runner_url,
            "total_cores": info.total_cores,
            "last_heartbeat": datetime.datetime.now(),
            "status": "online",
        },
    )
    if not created:
        # Update info if node re-registers
        node.url = info.runner_url
        node.total_cores = info.total_cores
        node.last_heartbeat = datetime.datetime.now()
        node.status = "online"  # Mark as online on registration/re-registration
        node.save()
        logger.info(f"Runner {info.hostname} re-registered/updated.")
    else:
        logger.info(f"Runner {info.hostname} registered successfully.")
    return {"message": f"Runner {info.hostname} acknowledged."}


@app.put("/heartbeat/{hostname}")
async def receive_heartbeat(hostname: str):
    node: Node = Node.get_or_none(Node.hostname == hostname)
    if node:
        node.last_heartbeat = datetime.datetime.now()
        if node.status != "online":
            logger.info(f"Runner {hostname} came back online.")
            node.status = "online"
        node.save()
        # logger.debug(f"Heartbeat received from {hostname}") # Use debug level
        return {"message": "Heartbeat received"}
    else:
        logger.warning(f"Heartbeat received from unknown hostname: {hostname}")
        raise HTTPException(status_code=404, detail="Node not registered")


@app.post("/submit", status_code=202)
async def submit_task(req: TaskRequest):
    node = find_suitable_node(req.required_cores)
    if not node:
        raise HTTPException(
            status_code=503,
            detail="Insufficient resources or no suitable node available.",
        )

    task_id = uuid.uuid4()
    # Ensure the base output directory exists (best done via deployment/Ansible)
    output_dir = os.path.join(HostConfig.SHARED_DIR, "task_outputs")
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        logger.warning(f"Could not ensure output directory {output_dir} exists: {e}")
        # Continue anyway, runner might create it or fail task later

    stdout_path = os.path.join(output_dir, f"{task_id}.out")
    stderr_path = os.path.join(output_dir, f"{task_id}.err")

    try:
        task: Task = Task.create(
            task_id=task_id,
            arguments="",
            env_vars="",
            command=req.command,
            required_cores=req.required_cores,
            assigned_node=node,
            status="assigning",  # Task is assigning until runner confirms start
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            submitted_at=datetime.datetime.now(),
        )
        task.set_arguments(req.arguments)
        task.set_env_vars(req.env_vars)
        task.save()
        logger.info(
            f"Task {task_id} created, requires {req.required_cores} cores. Assigning to {node.hostname}."
        )
    except Exception as e:
        logger.exception(f"Failed to create task record in database: {e}")
        raise HTTPException(status_code=500, detail="Failed to save task state.")

    task_info_for_runner = TaskInfoForRunner(
        task_id=str(task_id),
        command=req.command,
        arguments=req.arguments,
        env_vars=req.env_vars,
        required_cores=req.required_cores,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )

    asyncio.create_task(send_task_to_runner(node.url, task_info_for_runner))

    return {"message": "Task accepted for processing.", "task_id": str(task_id)}


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
            f"Ignoring status update '{update.status}' for task {update.task_id} which is already in final state '{task.status}'."
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

    task.save()
    logger.info(f"Task {update.task_id} status updated to {update.status} in DB.")

    return {"message": "Task status updated successfully."}


@app.get("/status/{task_id}")
async def get_task_status(task_id: str):
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Task ID format.")

    # Fetch associated node hostname efficiently if available
    query: Task = (
        Task.select(Task, Node.hostname.alias("node_hostname"))
        .left_outer_join(Node)
        .where(Task.task_id == task_uuid)
        .first()
    )
    assigned_node: Node = query.assigned_node
    if not query:
        raise HTTPException(status_code=404, detail="Task not found")
    task = query  # query is the Task object here due to Peewee's select behavior

    response = {
        "task_id": str(task.task_id),
        "command": task.command,
        "arguments": task.get_arguments(),
        "env_vars": task.get_env_vars(),
        "required_cores": task.required_cores,
        "status": task.status,
        # Access the aliased hostname from the query result
        "assigned_node": (
            assigned_node.hostname if assigned_node is not None else None
        ),
        "stdout_path": task.stdout_path,
        "stderr_path": task.stderr_path,
        "exit_code": task.exit_code,
        "error_message": task.error_message,
        "submitted_at": (task.submitted_at.isoformat() if task.submitted_at else None),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": (task.completed_at.isoformat() if task.completed_at else None),
    }
    return response


# Kill endpoint and helper (logic same, use logger)
async def send_kill_to_runner(runner_url: str, task_id: str):
    logger.info(f"Sending kill request for task {task_id} to runner {runner_url}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{runner_url}/kill", json={"task_id": task_id}, timeout=10.0
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

        task = Task.get_or_none(Task.task_id == task_id)
        if task and task.status == "killed":
            task.error_message += f" | Runner unreachable for kill confirmation: {e}"
            task.save()
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Runner {runner_url} failed kill for task {task_id}: {e.response.status_code} - {e.response.text}"
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


@app.post("/kill/{task_id}", status_code=202)
async def request_kill_task(task_id: str):
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Task ID format.")

    task: Task = (
        Task.select(Task, Node).join(Node).where(Task.task_id == task_uuid).first()
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
            f"Requesting kill confirmation from runner {task.assigned_node.hostname} for task {task_id}"
        )
        asyncio.create_task(send_kill_to_runner(runner_url, str(task_id)))
    else:
        logger.info(
            f"No kill signal sent to runner for task {task_id} (was not running or node offline/unknown)."
        )

    return {"message": f"Kill requested for task {task_id}. Task marked as killed."}


@app.get("/nodes")
async def get_nodes_status():
    nodes_status = []

    nodes: list[Node] = list(Node.select())
    # Need to calculate available cores for each online node
    online_nodes = {n.hostname: n for n in nodes if n.status == "online"}
    cores_in_use = defaultdict(int)
    if online_nodes:
        running_tasks: list[Task] = list(
            Task.select(
                Task.assigned_node, peewee.fn.SUM(Task.required_cores).alias("used")
            )
            .where(
                (Task.status == "running")
                & (Task.assigned_node << list(online_nodes.values()))
            )
            .group_by(Task.assigned_node)
        )

        for task_usage in running_tasks:
            # task_usage.assigned_node actually holds the foreign key ID here
            # We need to map it back to hostname. Let's re-query node hostname.
            node_fk: Node = task_usage.assigned_node
            cores_in_use[node_fk.hostname] = task_usage.required_cores

    for node in nodes:
        available = 0
        if node.status == "online":
            available = node.total_cores - cores_in_use.get(node.hostname, 0)

        nodes_status.append(
            {
                "hostname": node.hostname,
                "url": node.url,
                "total_cores": node.total_cores,
                "cores_in_use": (
                    cores_in_use.get(node.hostname, 0)
                    if node.status == "online"
                    else "N/A"
                ),
                "available_cores": available if node.status == "online" else 0,
                "status": node.status,
                "last_heartbeat": (
                    node.last_heartbeat.isoformat() if node.last_heartbeat else None
                ),
            }
        )
    return nodes_status


# --- Background Tasks (Logic same, use logger) ---
async def check_dead_runners():
    while True:
        await asyncio.sleep(HostConfig.CLEANUP_CHECK_INTERVAL_SECONDS)
        logger.info("Running check for dead runners...")
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
            logger.info("No dead runners found.")
            continue

        for node in dead_nodes:
            logger.warning(
                f"Runner {node.hostname} missed heartbeat threshold (last seen: {node.last_heartbeat}). Marking as offline."
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
                    f"Marking task {task.task_id} as 'lost' because node {node.hostname} went offline."
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
