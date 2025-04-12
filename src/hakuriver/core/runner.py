import os
import httpx
import socket
import asyncio
import datetime
import shlex

from fastapi import FastAPI, HTTPException, Body, BackgroundTasks
from pydantic import BaseModel, Field

# Load configuration FIRST
from hakuriver.utils.logger import logger
from hakuriver.utils.config_loader import settings


class RunnerConfig:
    # This needs to happen before setting up logging if log filename includes hostname
    RUNNER_HOSTNAME = socket.gethostname()
    # Network
    HOST_ADDRESS = settings["network"]["host_reachable_address"]
    HOST_PORT = settings["network"]["host_port"]
    RUNNER_PORT = settings["network"]["runner_port"]
    HOST_URL = f"http://{HOST_ADDRESS}:{HOST_PORT}"
    # Paths
    SHARED_DIR = settings["paths"]["shared_dir"]
    LOCAL_TEMP_DIR = settings["paths"]["local_temp_dir"]
    NUMACTL_PATH = settings["paths"]["numactl_path"] or None
    # Timing
    HEARTBEAT_INTERVAL_SECONDS = settings["timing"]["heartbeat_interval"]


RunnerConfig = RunnerConfig()


class TaskInfo(BaseModel):
    task_id: int
    command: str
    arguments: list[str] = Field(default_factory=list)
    env_vars: dict[str, str] = Field(default_factory=dict)
    required_cores: int
    stdout_path: str
    stderr_path: str


class TaskStatusUpdate(BaseModel):
    task_id: int
    status: str
    exit_code: int | None = None
    message: str | None = None
    started_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None = None


class HeartbeatData(BaseModel):
    running_tasks: list[int]
    completed_tasks: list[int]


# --- Global State ---
just_completed_tasks = set()
running_processes = {}  # task_id -> asyncio.subprocess.Process
try:
    runner_ip = socket.gethostbyname(RunnerConfig.RUNNER_HOSTNAME)
except socket.gaierror:
    logger.warning(
        f"Could not resolve hostname '{RunnerConfig.RUNNER_HOSTNAME}' to IP. Using 127.0.0.1 for runner URL registration. This might fail if host cannot reach 127.0.0.1 of the runner."
    )
    runner_ip = "127.0.0.1"  # Fallback, likely problematic

runner_url = f"http://{runner_ip}:{RunnerConfig.RUNNER_PORT}"
total_cores = os.cpu_count()
if not total_cores:
    logger.warning("Could not determine CPU count, defaulting to 4.")
    total_cores = 4


# --- Helper Functions (Logic same, use logger) ---
async def report_status_to_host(update_data: TaskStatusUpdate):
    logger.debug(
        f"Reporting status for task {update_data.task_id}: {update_data.status}"
    )
    try:
        # Use a slightly longer timeout for potentially busy host
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{RunnerConfig.HOST_URL}/update",
                json=update_data.model_dump(mode="json"),
                timeout=15.0,
            )
            response.raise_for_status()
        logger.debug(f"Host acknowledged status update for {update_data.task_id}")
    except httpx.RequestError as e:
        logger.error(
            f"Failed to report status for task {update_data.task_id} to host {RunnerConfig.HOST_URL}: {e}. Update lost."
        )
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Host {RunnerConfig.HOST_URL} rejected status update for task {update_data.task_id}: {e.response.status_code} - {e.response.text}"
        )
    except Exception as e:
        logger.exception(
            f"Unexpected error reporting status for task {update_data.task_id}: {e}"
        )


async def run_task_background(task_info: TaskInfo):
    task_id = task_info.task_id
    start_time = datetime.datetime.now()

    # Report 'running' status *before* starting the process
    await report_status_to_host(
        TaskStatusUpdate(task_id=task_id, status="running", started_at=start_time)
    )

    # Prepare command
    core_list = ",".join(map(str, range(task_info.required_cores)))
    if RunnerConfig.NUMACTL_PATH is not None:
        numa_cmd_prefix = [
            RunnerConfig.NUMACTL_PATH,
            f"--physcpubind={core_list}",
            "-l",
        ]
    else:
        numa_cmd_prefix = []
    command_list = numa_cmd_prefix + [task_info.command] + task_info.arguments

    # Prepare environment
    process_env = os.environ.copy()
    process_env.update(task_info.env_vars)
    process_env["RunnerConfig.CLUSTER_TASK_ID"] = str(task_id)
    process_env["RunnerConfig.LOCAL_TEMP_DIR"] = RunnerConfig.LOCAL_TEMP_DIR
    process_env["RunnerConfig.SHARED_DIR"] = (
        RunnerConfig.SHARED_DIR
    )  # Make shared dir path available too

    logger.info(
        f"Executing task {task_id}: {' '.join(shlex.quote(str(s)) for s in command_list)}"
    )  # Use shlex.quote for safer logging
    logger.info(f"Task {task_id} stdout -> {task_info.stdout_path}")
    logger.info(f"Task {task_id} stderr -> {task_info.stderr_path}")
    logger.debug(f"Task {task_id} environment overrides: {task_info.env_vars}")

    exit_code = None
    error_message = None
    process = None
    completion_time = None

    try:
        # Ensure output directory exists
        try:
            os.makedirs(os.path.dirname(task_info.stdout_path), exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create output directory for task {task_id}: {e}")
            raise  # Re-raise exception to trigger failure reporting

        with (
            open(task_info.stdout_path, "wb") as f_out,
            open(task_info.stderr_path, "wb") as f_err,
        ):
            process = await asyncio.create_subprocess_exec(
                *command_list,
                stdout=f_out,
                stderr=f_err,
                env=process_env,
                # Consider setting CWD:
                # cwd=RunnerConfig.LOCAL_TEMP_DIR # Run task within its local temp space?
                # cwd=RunnerConfig.SHARED_DIR     # Run task from shared dir? (Default: runner's cwd)
            )
            running_processes[task_id] = process
            logger.info(f"Task {task_id} started with PID {process.pid}")

            exit_code = await process.wait()
            completion_time = datetime.datetime.now()

            if task_id in running_processes:
                del running_processes[task_id]
                just_completed_tasks.add(task_id)  # Add to set for next heartbeat

        if exit_code == 0:
            status = "completed"
            logger.info(f"Task {task_id} completed successfully (exit code 0).")
        else:
            status = "failed"
            error_message = f"Process exited with non-zero code: {exit_code}"
            logger.warning(f"Task {task_id} failed with exit code {exit_code}.")

    except FileNotFoundError:
        status = "failed"
        # Distinguish between numactl and actual command not found
        cmd_not_found = (
            task_info.command
            if os.path.exists(RunnerConfig.NUMACTL_PATH)
            else RunnerConfig.NUMACTL_PATH
        )
        error_message = f"Executable not found: '{cmd_not_found}'"
        logger.error(f"Execution failed for task {task_id}: {error_message}")
        completion_time = datetime.datetime.now()
        if task_id in running_processes:
            del running_processes[task_id]
    except OSError as e:  # Catch permission errors, etc.
        status = "failed"
        error_message = f"OS error executing process: {e}"
        logger.error(f"OS error during execution of task {task_id}: {e}")
        completion_time = datetime.datetime.now()
        if task_id in running_processes:
            del running_processes[task_id]  # Clean up just in case
    except Exception as e:
        status = "failed"
        exit_code = -1
        error_message = f"Unexpected error during process execution: {e}"
        logger.exception(f"Exception during execution of task {task_id}: {e}")
        completion_time = datetime.datetime.now()
        # Clean up process if it exists and seems alive
        if task_id in running_processes:
            proc_to_kill = running_processes.pop(task_id)  # Remove first
            if proc_to_kill and proc_to_kill.returncode is None:
                try:
                    proc_to_kill.kill()
                    logger.info(f"Killed process for task {task_id} after exception.")
                except ProcessLookupError:
                    pass  # Already gone
                except Exception as kill_e:
                    logger.error(
                        f"Failed to kill process for {task_id} after exception: {kill_e}"
                    )

    # Report final status
    await report_status_to_host(
        TaskStatusUpdate(
            task_id=task_id,
            status=status,
            exit_code=exit_code,
            message=error_message,
            started_at=start_time,
            completed_at=completion_time
            or datetime.datetime.now(),  # Ensure completion time is set
        )
    )


async def send_heartbeat():
    while True:
        await asyncio.sleep(RunnerConfig.HEARTBEAT_INTERVAL_SECONDS)
        current_running_ids = list(running_processes.keys())
        completed_ids_to_send = []
        # Copy the set and clear the original atomically
        if just_completed_tasks:
            completed_ids_to_send = list(just_completed_tasks)
            just_completed_tasks.clear()

        heartbeat_payload = HeartbeatData(
            running_tasks=current_running_ids, completed_tasks=completed_ids_to_send
        )
        # logger.debug(f"Sending heartbeat to {RunnerConfig.HOST_URL}") # Too verbose for INFO level
        try:
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{RunnerConfig.HOST_URL}/heartbeat/{RunnerConfig.RUNNER_HOSTNAME}",
                    json=heartbeat_payload.model_dump(mode="json"),
                    timeout=10.0,
                )
                response.raise_for_status()
            # logger.debug("Heartbeat sent successfully.")
        except httpx.RequestError as e:
            logger.warning(
                f"Failed to send heartbeat to host {RunnerConfig.HOST_URL}: {e}"
            )
            # --- If heartbeat fails, put completed tasks back ---
            if completed_ids_to_send:
                just_completed_tasks.update(completed_ids_to_send)
                logger.warning(
                    f"Re-added {len(completed_ids_to_send)} completed task IDs to report on next successful heartbeat."
                )
            # ---------------------------------------------------
        except httpx.HTTPStatusError as e:
            logger.warning(
                f"Host {RunnerConfig.HOST_URL} rejected heartbeat: {e.response.status_code} - {e.response.text}"
            )
            if e.response.status_code == 404:
                logger.warning("Node seems unregistered, attempting to re-register...")
                await register_with_host()
            # Re-add completed tasks on host error too
            if completed_ids_to_send:
                just_completed_tasks.update(completed_ids_to_send)
                logger.warning(
                    f"Re-added {len(completed_ids_to_send)} completed task IDs to report on next successful heartbeat."
                )
        except Exception as e:
            logger.exception(f"Unexpected error sending heartbeat: {e}")
            # Re-add completed tasks on unexpected error too
            if completed_ids_to_send:
                just_completed_tasks.update(completed_ids_to_send)
                logger.warning(
                    f"Re-added {len(completed_ids_to_send)} completed task IDs to report on next successful heartbeat."
                )


async def register_with_host():
    register_data = {
        "hostname": RunnerConfig.RUNNER_HOSTNAME,
        "total_cores": total_cores,
        "runner_url": runner_url,
    }
    logger.info(
        f"Attempting to register with host {RunnerConfig.HOST_URL} "
        f"as {RunnerConfig.RUNNER_HOSTNAME} "
        f"({register_data['total_cores']} cores) at {runner_url}"
    )
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{RunnerConfig.HOST_URL}/register", json=register_data, timeout=15.0
            )
            response.raise_for_status()
        logger.info("Successfully registered/updated with host.")
        return True
    except httpx.RequestError as e:
        logger.error(f"Failed to register with host {RunnerConfig.HOST_URL}: {e}")
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Host {RunnerConfig.HOST_URL} rejected registration: "
            f"{e.response.status_code} - {e.response.text}"
        )
    except Exception as e:
        logger.exception(f"Unexpected error during registration: {e}")
    return False


# --- FastAPI App ---
app = FastAPI(title=f"Runner - {RunnerConfig.RUNNER_HOSTNAME}")


@app.post("/run")
async def accept_task(task_info: TaskInfo, background_tasks: BackgroundTasks):
    task_id = task_info.task_id
    if task_id in running_processes:
        logger.warning(
            f"Received request to run task {task_id}, but it is already running."
        )
        # Maybe it's a retry from host? Check process status? For now, reject.
        raise HTTPException(
            status_code=409, detail=f"Task {task_id} is already running on this node."
        )

    # Basic check for local temp dir existence
    if not os.path.isdir(RunnerConfig.LOCAL_TEMP_DIR):
        logger.error(
            f"Local temp directory '{RunnerConfig.LOCAL_TEMP_DIR}' "
            f"not found or not a directory. Rejecting task {task_id}."
        )
        # Report failure back? Or just reject? Reject is simpler.
        raise HTTPException(
            status_code=500,
            detail=f"Configuration error: LOCAL_TEMP_DIR '{RunnerConfig.LOCAL_TEMP_DIR}' missing on node.",
        )

    logger.info(
        f"Accepted task {task_id}: {task_info.command} with {task_info.required_cores} cores."
    )
    background_tasks.add_task(run_task_background, task_info)
    return {"message": "Task accepted", "task_id": task_id}


@app.post("/kill")
async def kill_task_endpoint(
    body: dict = Body(...),
):  # Renamed to avoid conflict with function name
    task_id = body.get("task_id")
    if not task_id:
        raise HTTPException(
            status_code=400, detail="Missing 'task_id' in request body."
        )

    logger.info(f"Received kill request for task {task_id}")
    process = running_processes.get(task_id)

    if not process:
        logger.warning(
            f"Kill request for task {task_id}, but process not found (maybe already finished?)."
        )
        just_completed_tasks.add(task_id)
        # Report 'killed' status to host anyway, as requested
        await report_status_to_host(
            TaskStatusUpdate(
                task_id=task_id,
                status="killed",
                message="Kill requested, but process not found/already finished.",
            )
        )
        # Return 404 to indicate it wasn't actively running here when kill arrived
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found or not currently running.",
        )

    kill_message = f"Task killed by host request."
    exit_code = -9  # Default for killed
    status = "killed"
    completion_time = datetime.datetime.now()

    try:
        if process.returncode is None:
            logger.info(f"Terminating process PID {process.pid} for task {task_id}")
            process.terminate()
            try:
                # Wait briefly for graceful shutdown
                await asyncio.wait_for(process.wait(), timeout=3.0)
                exit_code = process.returncode
                kill_message = f"Task terminated gracefully by host request (exit code {exit_code})."
                logger.info(
                    f"Process for task {task_id} terminated gracefully (exit code {exit_code})."
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Process for task {task_id} did not terminate gracefully, sending SIGKILL."
                )
                try:
                    process.kill()  # Force kill
                    exit_code = -9  # SIGKILL usually results in -9 or similar
                    kill_message = f"Task forcefully killed (SIGKILL) by host request."
                except ProcessLookupError:
                    logger.warning(
                        f"Process for task {task_id} disappeared during SIGKILL attempt."
                    )
                    kill_message = f"Task disappeared during kill attempt."
            except Exception as e:
                logger.error(
                    f"Error during process termination wait for {task_id}: {e}"
                )
                exit_code = process.returncode if process.returncode is not None else -9

        else:
            logger.warning(
                f"Kill request for task {task_id}, "
                f"but process already exited with code {process.returncode}."
            )
            kill_message = f"Kill requested, but process already exited (code {process.returncode})."
            exit_code = process.returncode  # Report actual exit code
            # Status remains 'killed' as requested, even if it already finished

        # Remove from running list only after handling kill/termination
        if task_id in running_processes:
            del running_processes[task_id]
        just_completed_tasks.add(task_id)

    except ProcessLookupError:
        logger.warning(
            f"Process for task {task_id} already gone when kill was attempted."
        )
        kill_message = "Kill requested, but process was already gone."
        status = "killed"
        if task_id in running_processes:
            del running_processes[task_id]
    except Exception as e:
        logger.exception(f"Error during kill process for task {task_id}: {e}")
        kill_message = f"Error during kill process: {e}"
        status = "killed"
        if task_id in running_processes:
            del running_processes[task_id]

    # Report final status back to host
    await report_status_to_host(
        TaskStatusUpdate(
            task_id=task_id,
            status=status,
            exit_code=exit_code,
            message=kill_message,
            # started_at=? # Not readily available here, Host has it
            completed_at=completion_time,
        )
    )

    return {"message": f"Kill processed for task {task_id}. Status reported to host."}


async def startup_event():
    logger.info(
        f"Runner starting up on {RunnerConfig.RUNNER_HOSTNAME} "
        f"({runner_ip}:{RunnerConfig.RUNNER_PORT})"
    )
    registered = False
    for attempt in range(5):  # Retry registration a few times with longer delay
        registered = await register_with_host()
        if registered:
            break
        wait_time = 5 * (attempt + 1)  # Increase wait time
        logger.info(
            f"Registration attempt {attempt+1}/5 failed. Retrying in {wait_time} seconds..."
        )
        await asyncio.sleep(wait_time)

    if not registered:
        logger.error(
            "Failed to register with host after multiple attempts. "
            "Runner will not receive tasks and may not function correctly."
        )
        # Consider exiting? For now, continue but log error.
        # sys.exit(1)
    else:
        # Start heartbeat only if registration is successful
        logger.info("Starting heartbeat background task.")
        asyncio.create_task(send_heartbeat())


app.add_event_handler("startup", startup_event)


async def shutdown_event():
    logger.info("Runner shutting down.")
    # Optional: Attempt to gracefully kill running tasks?
    # This is complex as shutdown might be abrupt. Best effort:
    tasks_to_kill = list(running_processes.keys())
    if tasks_to_kill:
        logger.warning(
            f"Attempting to terminate {len(tasks_to_kill)} running tasks on shutdown..."
        )
        for task_id, process in running_processes.items():
            if process.returncode is None:
                logger.info(
                    f"Terminating task {task_id} (PID {process.pid}) on shutdown."
                )
                try:
                    process.terminate()
                    # Don't wait long, just send signal
                except Exception as e:
                    logger.error(f"Error terminating task {task_id} on shutdown: {e}")
        # Give a very brief moment for signals to be processed
        await asyncio.sleep(0.5)


app.add_event_handler("shutdown", shutdown_event)
