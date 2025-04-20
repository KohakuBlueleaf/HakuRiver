import getpass
import os
import signal
import httpx
import socket
import asyncio
import datetime
import shlex
import subprocess
import psutil
import json
import re

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
    RUNNER_ADDRESS = settings["network"]["runner_address"]
    RUNNER_PORT = settings["network"]["runner_port"]
    HOST_URL = f"http://{HOST_ADDRESS}:{HOST_PORT}"
    # Paths
    SHARED_DIR = settings["paths"]["shared_dir"]
    LOCAL_TEMP_DIR = settings["paths"]["local_temp_dir"]
    NUMACTL_PATH = (
        settings["paths"]["numactl_path"] or "numactl"
    )  # Default to system PATH
    # Timing
    HEARTBEAT_INTERVAL_SECONDS = settings["timing"]["heartbeat_interval"]
    TASK_CHECK_INTERVAL_SECONDS = settings["timing"].get("resource_check_interval", 1)
    RUNNER_USER = settings.get("environment", {}).get("runner_user", getpass.getuser())


RunnerConfig = RunnerConfig()


class TaskInfo(BaseModel):
    task_id: int
    command: str
    arguments: list[str] = Field(default_factory=list)
    env_vars: dict[str, str] = Field(default_factory=dict)
    required_cores: int
    stdout_path: str
    stderr_path: str
    required_memory_bytes: int | None = None
    target_numa_node_id: int | None = Field(
        default=None, description="Target NUMA node ID for execution"
    )  # MODIFIED: Added field


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
    running_tasks: list[int]
    killed_tasks: list[HeartbeatKilledTaskInfo] = Field(default_factory=list)
    cpu_percent: float | None = None
    memory_percent: float | None = None
    memory_used_bytes: int | None = None
    memory_total_bytes: int | None = None


# --- Global State ---
killed_tasks_pending_report: list[HeartbeatKilledTaskInfo] = []
running_processes = (
    {}
)  # task_id -> {'unit': str, 'process': asyncio.Process | None, 'memory_limit': int | None, 'pid': int | None}
paused_processes = {}
runner_ip = RunnerConfig.RUNNER_ADDRESS
runner_url = f"http://{runner_ip}:{RunnerConfig.RUNNER_PORT}"
total_cores = os.cpu_count()
if not total_cores:
    logger.warning("Could not determine CPU count, defaulting to 4.")
    total_cores = 4

numa_topology: dict[int, dict] = {}


# --- Helper Functions (Logic same, use logger) ---
def detect_numa_topology() -> dict | None:
    """Detects NUMA topology by parsing `numactl --hardware` output."""
    if not RunnerConfig.NUMACTL_PATH:
        logger.info("numactl path not configured, skipping NUMA detection.")
        return None
    try:
        cmd = [RunnerConfig.NUMACTL_PATH, "-H"]
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, encoding="utf-8"
        )
        output = result.stdout

        topology = {}
        # Regex to find node lines like: node 0 cpus: 0 1 2 3 4 5 6 7 16 17 18 19 20 21 22 23
        node_cpu_match = re.findall(r"node (\d+) cpus:((?:\s+\d+)+)", output)
        # Regex to find memory lines like: node 0 size: 64215 MB
        # Allows for different units (kB, MB, GB)
        node_mem_match = re.findall(
            r"node (\d+) size: (\d+)\s*((?:MB|GB|kB))", output, re.IGNORECASE
        )
        # Regex to find distance lines: node distances: node   0   1 \n  0:  10  21 \n  1:  21  10
        # We mainly care about the number of nodes reported here to validate parsing
        distance_header = re.search(r"node distances:\nnode\s+((?:\s*\d+)+)", output)
        num_nodes_from_distance = (
            len(distance_header.group(1).split()) if distance_header else 0
        )

        if not node_cpu_match:
            logger.warning(
                f"`{RunnerConfig.NUMACTL_PATH} --hardware` output did not contain expected CPU info."
            )
            return None  # No NUMA nodes detected based on CPU info

        parsed_nodes = set()
        for node_id_str, cpu_list_str in node_cpu_match:
            node_id = int(node_id_str)
            parsed_nodes.add(node_id)
            cores = [int(cpu) for cpu in cpu_list_str.split()]
            topology[node_id] = {
                "cores": cores,
                "memory_bytes": None,
            }  # Initialize memory

        for node_id_str, mem_size_str, mem_unit in node_mem_match:
            node_id = int(node_id_str)
            if node_id in topology:
                size = int(mem_size_str)
                unit = mem_unit.upper()
                if unit == "GB":
                    topology[node_id]["memory_bytes"] = size * 1024 * 1024 * 1024
                elif unit == "MB":
                    topology[node_id]["memory_bytes"] = size * 1024 * 1024
                elif unit == "KB":
                    topology[node_id]["memory_bytes"] = size * 1024
                else:  # Assume bytes if no unit found by regex (though unlikely with the regex)
                    topology[node_id]["memory_bytes"] = size

        # Validation: Check if number of nodes from CPU list matches distance header (if available)
        if num_nodes_from_distance > 0 and len(parsed_nodes) != num_nodes_from_distance:
            logger.warning(
                f"Mismatch between detected NUMA nodes from CPU list ({len(parsed_nodes)}) and distance matrix header ({num_nodes_from_distance}). Topology parsing might be incomplete."
            )

        if not topology:
            logger.info("No NUMA nodes detected or parsed.")
            return None

        logger.info(f"Detected NUMA topology: {json.dumps(topology)}")
        return topology

    except FileNotFoundError:
        logger.error(
            f"`{RunnerConfig.NUMACTL_PATH}` command not found. Cannot detect NUMA topology."
        )
        return None
    except subprocess.CalledProcessError as e:
        logger.error(
            f"Error running `{RunnerConfig.NUMACTL_PATH} --hardware`: {e.stderr}"
        )
        return None
    except Exception as e:
        logger.exception(f"Unexpected error during NUMA detection: {e}")
        return None


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
    unit_name = f"hakuriver-task-{task_id}"
    start_time = datetime.datetime.now()

    # --- Construct systemd-run command ---
    systemd_run_cmd = [
        "sudo",
        "systemd-run",
        "--scope",  # Run as a transient scope unit
        "--collect",  # Garbage collect unit when process exits
        f"--property=User={RunnerConfig.RUNNER_USER}",  # Run as the current user (or specify another user)
        f"--unit={unit_name}",
        # Basic description
        f"--description=HakuRiver Task {task_id}: {shlex.quote(task_info.command)}",
    ]

    # Resource Allocation Properties
    if task_info.required_cores > 0 and total_cores > 0:
        # Generate CPU list like "0,1,2" if required_cores=3
        # cpu_list = ",".join(map(str, range(min(task_info.required_cores, total_cores))))
        # systemd_run_cmd.append(f"--property=CPUAffinity={cpu_list}")
        # Optionally add CPUQuota for stricter enforcement (percentage)
        cpu_quota = int(task_info.required_cores * 100)
        systemd_run_cmd.append(f"--property=CPUQuota={cpu_quota}%")

    if (
        task_info.required_memory_bytes is not None
        and task_info.required_memory_bytes > 0
    ):
        systemd_run_cmd.append(
            f"--property=MemoryMax={task_info.required_memory_bytes}"
        )
    systemd_run_cmd.append("--property=MemorySwapMax=0")

    # Environment Variables
    process_env = os.environ.copy()  # Start with runner's environment
    process_env.update(task_info.env_vars)
    process_env["HAKURIVER_TASK_ID"] = str(task_id)  # Use HAKURIVER_ prefix
    process_env["HAKURIVER_LOCAL_TEMP_DIR"] = RunnerConfig.LOCAL_TEMP_DIR
    process_env["HAKURIVER_SHARED_DIR"] = RunnerConfig.SHARED_DIR
    if task_info.target_numa_node_id is not None:
        process_env["HAKURIVER_TARGET_NUMA_NODE"] = str(task_info.target_numa_node_id)
    for key, value in process_env.items():
        systemd_run_cmd.append(f"--setenv={key}={value}")  # Pass all env vars

    # Working Directory (Optional - run in shared or temp?)
    systemd_run_cmd.append(f'--working-directory={RunnerConfig.SHARED_DIR}') # Example

    # Command and Arguments with Redirection
    # This is complex due to shell quoting needed inside systemd-run
    # Ensure stdout/stderr paths are absolute and quoted if they contain spaces
    quoted_stdout = shlex.quote(task_info.stdout_path)
    quoted_stderr = shlex.quote(task_info.stderr_path)
    # Use shlex.join for the inner command and args if possible, otherwise manual quoting
    inner_cmd_parts = [shlex.quote(task_info.command)] + [
        shlex.quote(arg) for arg in task_info.arguments
    ]
    inner_cmd_str = " ".join(inner_cmd_parts)

    numactl_prefix = ""
    if task_info.target_numa_node_id is not None and numa_topology is not None:
        if (
            RunnerConfig.NUMACTL_PATH
            and numa_topology
            and task_info.target_numa_node_id in numa_topology
        ):
            # Basic binding to both CPU and memory on the target node
            numa_id = task_info.target_numa_node_id
            # Use --interleave=all as a fallback if specific binds cause issues,
            # or fine-tune with --physcpubind= based on numa_topology[numa_id]['cores']
            numactl_prefix = f"{shlex.quote(RunnerConfig.NUMACTL_PATH)} --cpunodebind={numa_id} --membind={numa_id} "
            logger.info(f"Task {task_id}: Applying NUMA binding to node {numa_id}.")
        elif not RunnerConfig.NUMACTL_PATH:
            logger.warning(
                f"Task {task_id}: Target NUMA node {task_info.target_numa_node_id} specified, but numactl path is not configured. Ignoring NUMA binding."
            )
        elif not numa_topology:
            logger.warning(
                f"Task {task_id}: Target NUMA node {task_info.target_numa_node_id} specified, but NUMA topology couldn't be detected on this runner. Ignoring NUMA binding."
            )
        else:  # NUMA ID not found in detected topology
            logger.warning(
                f"Task {task_id}: Target NUMA node {task_info.target_numa_node_id} not found in detected topology {list(numa_topology.keys())}. Ignoring NUMA binding."
            )

    shell_command = (
        f"exec {numactl_prefix}{inner_cmd_str} > {quoted_stdout} 2> {quoted_stderr}"
    )
    systemd_run_cmd.extend(["/bin/sh", "-c", shell_command])

    logger.info(f"Executing task {task_id} via systemd-run unit {unit_name}")
    logger.debug(
        f"systemd-run command: {' '.join(systemd_run_cmd)}"
    )  # Log the full command for debugging

    exit_code = None
    error_message = None
    systemd_process = None
    status = "failed"  # Default to failed unless successful

    try:
        # Ensure output directories exist before starting
        os.makedirs(os.path.dirname(task_info.stdout_path), exist_ok=True)
        os.makedirs(os.path.dirname(task_info.stderr_path), exist_ok=True)

        # Run systemd-run itself
        systemd_process = await asyncio.create_subprocess_exec(
            *systemd_run_cmd,
            stdout=asyncio.subprocess.PIPE,  # Capture systemd-run's output/errors
            stderr=asyncio.subprocess.PIPE,
        )
        await report_status_to_host(
            TaskStatusUpdate(
                task_id=task_id,
                status="running",
                started_at=start_time,
            )
        )

        # Store info immediately, even before systemd-run finishes
        running_processes[task_id] = {
            "unit": unit_name,
            "process": systemd_process,  # Store the systemd-run process object initially
            "memory_limit": task_info.required_memory_bytes,
            "pid": systemd_process.pid,  # PID will be filled by the check loop
        }

        # Wait for systemd-run command to finish
        stdout, stderr = await systemd_process.communicate()
        exit_code = systemd_process.returncode

        if exit_code == 0:
            logger.info(
                f"systemd-run unit {unit_name} for task {task_id} "
                "successfully executed, task is done."
            )
            if task_id in running_processes:
                del running_processes[task_id]  # Remove from tracking
            # Report running status (Host already knows it's assigning)
            # With scope mode, systemd-run will not fork so once it's done, the task is done
            await report_status_to_host(
                TaskStatusUpdate(
                    task_id=task_id,
                    status="completed",
                    exit_code=exit_code,
                    completed_at=datetime.datetime.now(),
                )
            )
        elif task_id in running_processes:  # not killed by host
            error_message = f"systemd-run failed with exit code {exit_code}."
            stderr_decoded = stderr.decode(errors="replace").strip()
            if stderr_decoded:
                error_message += f" Stderr: {stderr_decoded}"
            logger.error(
                f"Failed to launch task {task_id} via systemd-run: {error_message}"
            )
            # Remove from running processes as it failed to launch
            if task_id in running_processes:
                del running_processes[task_id]
            # Report failure to host
            await report_status_to_host(
                TaskStatusUpdate(
                    task_id=task_id,
                    status="failed",
                    exit_code=exit_code,  # systemd-run's exit code
                    message=error_message,
                    started_at=start_time,  # It attempted to start
                    completed_at=datetime.datetime.now(),
                )
            )

    except FileNotFoundError:
        # This likely means systemd-run itself wasn't found
        error_message = (
            "systemd-run command not found. Is systemd installed and in PATH?"
        )
        logger.critical(error_message)
        status = "failed"
        if task_id in running_processes:
            del running_processes[task_id]
        await report_status_to_host(
            TaskStatusUpdate(
                task_id=task_id,
                status=status,
                message=error_message,
                completed_at=datetime.datetime.now(),
            )
        )
    except OSError as e:
        error_message = f"OS error executing systemd-run for task {task_id}: {e}"
        logger.error(error_message)
        status = "failed"
        if task_id in running_processes:
            del running_processes[task_id]
        await report_status_to_host(
            TaskStatusUpdate(
                task_id=task_id,
                status=status,
                message=error_message,
                completed_at=datetime.datetime.now(),
            )
        )
    except Exception as e:
        error_message = f"Unexpected error launching task {task_id}: {e}"
        logger.exception(error_message)
        status = "failed"
        if task_id in running_processes:
            del running_processes[task_id]
        await report_status_to_host(
            TaskStatusUpdate(
                task_id=task_id,
                status=status,
                message=error_message,
                completed_at=datetime.datetime.now(),
            )
        )

    # Note: The run_task_background function now primarily handles LAUNCHING the task.
    # The actual completion/failure/OOM kill is detected by the check_running_tasks loop
    # and reported via heartbeat or direct status updates from that loop.


async def send_heartbeat():
    while True:
        await asyncio.sleep(RunnerConfig.HEARTBEAT_INTERVAL_SECONDS)

        # --- Gather Data ---
        current_running_ids = list(running_processes.keys())
        killed_payload: list[HeartbeatKilledTaskInfo] = []

        # Atomically get and clear pending killed tasks
        if killed_tasks_pending_report:
            killed_payload = killed_tasks_pending_report[:]  # Copy the list
            killed_tasks_pending_report.clear()  # Clear the original

        # Get node resource stats
        node_cpu_percent = psutil.cpu_percent(
            interval=None
        )  # Get overall CPU % since last call (or boot)
        node_mem_info = psutil.virtual_memory()

        heartbeat_payload = HeartbeatData(
            running_tasks=current_running_ids,
            killed_tasks=killed_payload,  # Send the copied list
            cpu_percent=node_cpu_percent,
            memory_percent=node_mem_info.percent,
            memory_used_bytes=node_mem_info.used,
            memory_total_bytes=node_mem_info.total,
        )

        # logger.debug(f"Sending heartbeat to {RunnerConfig.HOST_URL}")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{RunnerConfig.HOST_URL}/heartbeat/{RunnerConfig.RUNNER_HOSTNAME}",
                    json=heartbeat_payload.model_dump(mode="json"),
                    timeout=10.0,
                )
                response.raise_for_status()
            # logger.debug("Heartbeat sent successfully.")
            # Success: killed_payload was sent, keep killed_tasks_pending_report empty

        except httpx.RequestError as e:
            logger.warning(
                f"Failed to send heartbeat to host {RunnerConfig.HOST_URL}: {e}"
            )
            # Failure: Put the killed tasks back to be reported next time
            if killed_payload:
                killed_tasks_pending_report.extend(killed_payload)
                logger.warning(
                    f"Re-added {len(killed_payload)} killed task reports for next heartbeat."
                )
        except httpx.HTTPStatusError as e:
            logger.warning(
                f"Host {RunnerConfig.HOST_URL} rejected heartbeat: {e.response.status_code} - {e.response.text}"
            )
            if e.response.status_code == 404:
                logger.warning("Node seems unregistered, attempting to re-register...")
                await register_with_host()
            # Failure: Put the killed tasks back
            if killed_payload:
                killed_tasks_pending_report.extend(killed_payload)
                logger.warning(
                    f"Re-added {len(killed_payload)} killed task reports for next heartbeat."
                )
        except Exception as e:
            logger.exception(f"Unexpected error sending heartbeat: {e}")
            # Failure: Put the killed tasks back
            if killed_payload:
                killed_tasks_pending_report.extend(killed_payload)
                logger.warning(
                    f"Re-added {len(killed_payload)} killed task reports for next heartbeat."
                )


async def register_with_host():
    global numa_topology  # Ensure we are using the global variable
    if numa_topology is None:  # Detect only if not already done
        numa_topology = detect_numa_topology()

    register_data = {
        "hostname": RunnerConfig.RUNNER_HOSTNAME,
        "total_cores": total_cores,
        "total_ram_bytes": psutil.virtual_memory().total,
        "runner_url": runner_url,
        "numa_topology": numa_topology,  # Add the detected topology
    }
    logger.info(
        f"Attempting to register with host {RunnerConfig.HOST_URL} "
        f"as {RunnerConfig.RUNNER_HOSTNAME} "
        f"({register_data['total_cores']} cores, NUMA: {'Detected' if numa_topology else 'N/A'}) at {runner_url}"
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
        unit_name = running_processes[task_id].get("unit", "unknown unit")
        logger.warning(
            f"Received request to run task {task_id}, but it is already tracked (unit: {unit_name})."
        )
        raise HTTPException(
            status_code=409,
            detail=f"Task {task_id} is already running/tracked on this node.",
        )

    if not os.path.isdir(RunnerConfig.LOCAL_TEMP_DIR):
        logger.error(
            f"Local temp directory '{RunnerConfig.LOCAL_TEMP_DIR}' "
            f"not found or not a directory. Rejecting task {task_id}."
        )
        raise HTTPException(
            status_code=500,
            detail=f"Configuration error: LOCAL_TEMP_DIR '{RunnerConfig.LOCAL_TEMP_DIR}' missing on node.",
        )

    logger.info(
        f"Accepted task {task_id}: {task_info.command} "
        f"Cores: {task_info.required_cores}, "
        f"Mem: {task_info.required_memory_bytes // (1024*1024) if task_info.required_memory_bytes else 'N/A'}MB, "
    )
    background_tasks.add_task(run_task_background, task_info)
    return {"message": "Task accepted for launch", "task_id": task_id}


@app.post("/pause")
async def pause_task(body: dict = Body(...)):
    task_id = body.get("task_id")
    if not task_id:
        raise HTTPException(
            status_code=400, detail="Missing 'task_id' in request body."
        )

    logger.info(f"Received pause request for task {task_id}")
    task_data = running_processes.get(task_id, None)
    unit_name = task_data["unit"]

    if not task_data:
        logger.warning(
            f"Pause request for task {task_id}, but it's not actively tracked."
        )
        raise HTTPException(
            status_code=404, detail=f"Task {task_id} not found or not tracked."
        )

    try:
        if "task_pid" in task_data:
            pid = task_data["task_pid"]
        else:
            logger.info(f"Finding process for task {unit_name} to pause.")
            find_cmd = ["sudo", "systemctl", "status", f"{unit_name}.scope"]
            process = subprocess.run(
                find_cmd, capture_output=True, text=True
            )
            result = re.search(rf"{unit_name}\.scope\n\s+[^\d]+(\d+)", process.stdout)
            if not result:
                logger.error(
                    f"Failed to find process for task {task_id}."
                    f"\nOutput: {process.stdout}"
                )
                raise Exception(f"Failed to find process for task {task_id}.\nOutput: {process.stdout}")
            pid = result.group(1)
            logger.info(f"Found process {pid} for task {task_id}.")
        logger.info(f"Attempting to pause task {task_id} using kill.")
        stop_cmd = ["sudo", "kill", "-s", "SIGSTOP", str(pid)]
        result = subprocess.run(stop_cmd, check=False, timeout=1)
        if result.returncode != 0:
            raise Exception(f"Failed to pause task {task_id} using kill.")

        logger.info(f"Task {task_id} paused successfully.")
        paused_processes[task_id] = running_processes.pop(task_id)
        paused_processes[task_id]["task_pid"] = pid  # Store the paused PID
        await report_status_to_host(
            TaskStatusUpdate(
                task_id=task_id,
                status="paused",
                exit_code=None,
                message="Task paused using kill.",
            )
        )
    except Exception as e:
        logger.exception(f"Error during kill pause for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {"message": f"Pause request processed for task {task_id}"}


@app.post("/resume")
async def resume_task(body: dict = Body(...)):
    task_id = body.get("task_id")
    if not task_id:
        raise HTTPException(
            status_code=400, detail="Missing 'task_id' in request body."
        )

    logger.info(f"Received resume request for task {task_id}")
    task_data = paused_processes.get(task_id, None)

    if not task_data:
        logger.warning(
            f"Resume request for task {task_id}, but it's not actively tracked."
        )
        raise HTTPException(
            status_code=404, detail=f"Task {task_id} not found or not tracked."
        )

    try:
        logger.info(f"Attempting to resume task {task_id} using kill.")
        task_pid = task_data["task_pid"]
        resume_cmd = ["sudo", "kill", "-s", "SIGCONT", str(task_pid)]
        result = subprocess.run(resume_cmd, check=False, timeout=1)
        if result.returncode != 0:
            raise Exception(f"Failed to resume task {task_id} using kill.")

        logger.info(f"Task {task_id} resumed successfully.")
        running_processes[task_id] = paused_processes.pop(task_id)
        await report_status_to_host(
            TaskStatusUpdate(
                task_id=task_id,
                status="running",
                exit_code=None,
                message="Task resumed using kill.",
            )
        )
    except Exception as e:
        logger.exception(f"Error during kill resume for task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {"message": f"Resume request processed for task {task_id}"}


@app.post("/kill")
async def kill_task_endpoint(body: dict = Body(...)):
    task_id = body.get("task_id")
    if not task_id:
        raise HTTPException(
            status_code=400, detail="Missing 'task_id' in request body."
        )

    logger.info(f"Received kill request for task {task_id}")
    task_data = running_processes.get(task_id)

    if not task_data:
        logger.warning(
            f"Kill request for task {task_id}, but it's not actively tracked."
        )
        # Report killed status to host as requested, even if we lost track
        await report_status_to_host(
            TaskStatusUpdate(
                task_id=task_id,
                status="killed",
                exit_code=-9,
                message="Kill requested by host, task not tracked by runner.",
                completed_at=datetime.datetime.now(),
            )
        )
        raise HTTPException(
            status_code=404, detail=f"Task {task_id} not found or not tracked."
        )

    process = task_data["process"]
    unit_name = task_data["unit"]
    kill_message = f"Task killed by host request (Unit: {unit_name})."
    status = "killed"
    completion_time = datetime.datetime.now()
    exit_code = -9  # Assume SIGKILL equivalent

    try:
        if "task_pid" in task_data:
            pid = task_data["task_pid"]
        else:
            logger.info(f"Finding process for task {unit_name} to pause.")
            find_cmd = ["sudo", "systemctl", "status", f"{unit_name}.scope"]
            process = subprocess.run(
                find_cmd, capture_output=True, text=True
            )
            result = re.search(rf"{unit_name}\.scope\n\s+[^\d]+(\d+)", process.stdout)
            if not result:
                logger.error(
                    f"Failed to find process for task {task_id}."
                    f"\nOutput: {process.stdout}"
                )
                raise Exception(f"Failed to find process for task {task_id}.\nOutput: {process.stdout}")
            pid = result.group(1)
            logger.info(f"Found process {pid} for task {task_id}.")
        logger.info(
            f"Attempting to stop/kill systemd unit {unit_name} for task {task_id}"
        )
        # Use kill directly to ensure we stop the unit
        kill_cmd_task = ["sudo", "kill", "-s", "SIGKILL", str(pid)]
        kill_result_task = subprocess.run(
            kill_cmd_task, capture_output=True, text=True, check=False
        )
        kill_cmd = ["sudo", "kill", "-s", "SIGKILL", str(process.pid)]
        kill_result = subprocess.run(
            kill_cmd, capture_output=True, text=True, check=False
        )

        if kill_result.returncode == 0 and kill_result_task.returncode == 0:
            logger.info(f"Successfully sent kill signal to unit {unit_name}.")
        else:
            # Maybe it already stopped? Or permission error?
            logger.warning(
                f"kill {unit_name} failed (rc={kill_result.returncode}): {kill_result.stderr.strip()}. Unit might be stopped already."
            )
            # Check if it's inactive
            status_cmd = ["sudo", "systemctl", "is-active", unit_name]
            status_result = subprocess.run(
                status_cmd, capture_output=True, text=True, check=False
            )
            if status_result.stdout.strip() != "active":
                logger.info(
                    f"Unit {unit_name} is not active, assuming kill effective or already stopped."
                )
            else:
                logger.error(
                    f"Failed to kill unit {unit_name} and it still seems active."
                )
                kill_message += " | Failed to confirm kill via systemctl."

        # Remove from tracking immediately
        if task_id in running_processes:
            del running_processes[task_id]

        # Add to report list
        killed_info = HeartbeatKilledTaskInfo(task_id=task_id, reason="killed_by_host")
        killed_tasks_pending_report.append(killed_info)

    except Exception as e:
        logger.exception(
            f"Error during systemctl kill process for task {task_id} ({unit_name}): {e}"
        )
        kill_message = f"Error during kill via systemctl: {e}"
        status = "killed"
        if task_id in running_processes:
            del running_processes[task_id]  # Ensure removal on error too

    # Report final status back to host (optional here, could rely on heartbeat)
    # await report_status_to_host(
    #     TaskStatusUpdate(
    #         task_id=task_id, status=status, exit_code=exit_code,
    #         message=kill_message, completed_at=completion_time
    #     )
    # )

    return {
        "message": f"Kill processed for task {task_id}. Final status will be reported via heartbeat."
    }


async def startup_event():
    global numa_topology
    logger.info(
        f"Runner starting up on {RunnerConfig.RUNNER_HOSTNAME} "
        f"({runner_ip}:{RunnerConfig.RUNNER_PORT})"
    )
    # Detect topology *before* first registration attempt
    logger.info("Detecting NUMA topology...")
    numa_topology = detect_numa_topology()

    registered = False
    for attempt in range(5):
        registered = await register_with_host()  # Now sends topology if detected
        if registered:
            break
        wait_time = 5 * (attempt + 1)
        logger.info(
            f"Registration attempt {attempt+1}/5 failed. Retrying in {wait_time} seconds..."
        )
        await asyncio.sleep(wait_time)

    if not registered:
        logger.error(
            "Failed to register with host after multiple attempts. Runner may not function correctly."
        )
    else:
        logger.info("Starting background tasks (Heartbeat).")
        # Removed check_running_tasks call - rely on systemd-run --scope --collect
        asyncio.create_task(send_heartbeat())


app.add_event_handler("startup", startup_event)


async def shutdown_event():
    logger.info("Runner shutting down.")
    tasks_to_kill = list(running_processes.keys())
    if tasks_to_kill:
        logger.warning(
            f"Attempting to stop {len(tasks_to_kill)} tracked systemd units on shutdown..."
        )
        for task_id, task_data in running_processes.items():
            unit_name = task_data["unit"]
            logger.info(
                f"Sending stop signal to unit {unit_name} for task {task_id} on shutdown."
            )
            try:
                # Use stop for potentially cleaner shutdown than kill
                stop_cmd = ["sudo", "systemctl", "stop", unit_name]
                subprocess.run(
                    stop_cmd, check=False, timeout=1
                )  # Short timeout, best effort
            except Exception as e:
                logger.error(f"Error stopping unit {unit_name} on shutdown: {e}")
    await asyncio.sleep(0.5)  # Brief pause


app.add_event_handler("shutdown", shutdown_event)
