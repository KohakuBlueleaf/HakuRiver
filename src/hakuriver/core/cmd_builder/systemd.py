import os
import shlex

from hakuriver.utils.binding import get_executable_and_library_mounts
from hakuriver.utils import docker as docker_utils
from hakuriver.core.config import RUNNER_CONFIG, RunnerConfig

from hakuriver.core.task_info import TaskInfo


def append_resource_alloc_options(
    task_info: TaskInfo,
    run_cmd: list[str],
    total_cores: int,
):
    """
    Appends systemd-run specific resource allocation options to the given
    command. This function modifies `run_cmd` in-place.

    Possible options to be appended:
    - `CPUQuota`
    - `MemoryMax`
    - `MemorySwapMax`
    """
    if task_info.required_cores > 0 and total_cores > 0:
        # Generate CPU list like "0,1,2" if required_cores=3
        # cpu_list = ",".join(map(str, range(min(task_info.required_cores, total_cores))))
        # run_cmd.append(f"--property=CPUAffinity={cpu_list}")
        # Optionally add CPUQuota for stricter enforcement (percentage)
        cpu_quota = int(task_info.required_cores * 100)
        run_cmd.append(f"--property=CPUQuota={cpu_quota}%")

    if (
        task_info.required_memory_bytes is not None
        and task_info.required_memory_bytes > 0
    ):
        run_cmd.append(f"--property=MemoryMax={task_info.required_memory_bytes}")
    run_cmd.append("--property=MemorySwapMax=0")

def append_env_options(
    task_info: TaskInfo,
    run_cmd: list[str],
):
    """
    Appends systemd-run specific environment variables options to the given
    command. This function modifies `run_cmd` in-place.
    """
    process_env = os.environ.copy()  # Start with runner's environment
    process_env.update(task_info.env_vars)
    process_env["HAKURIVER_TASK_ID"] = str(task_info.task_id)  # Use HAKURIVER_ prefix
    process_env["HAKURIVER_LOCAL_TEMP_DIR"] = RUNNER_CONFIG.LOCAL_TEMP_DIR
    process_env["HAKURIVER_SHARED_DIR"] = RUNNER_CONFIG.SHARED_DIR
    if task_info.target_numa_node_id is not None:
        process_env["HAKURIVER_TARGET_NUMA_NODE"] = str(
            task_info.target_numa_node_id
        )
    for key, value in process_env.items():
        run_cmd.append(f"--setenv={key}={value}")  # Pass all env vars

def build_inner_cmd(
    task_info: TaskInfo,
):
    """
    Builds the inner command for systemd-run.
    """
    task_id = task_info.task_id
    # Use shlex.join for the inner command and args if possible, otherwise manual quoting
    if not task_info.docker_image_name:
        inner_cmd_parts = [task_info.command] + [
            shlex.quote(arg) for arg in task_info.arguments
        ]
    else:
        task_command_list = [task_info.command] + [
            shlex.quote(arg) for arg in task_info.arguments
        ]
        docker_wrapper_cmd = docker_utils.modify_command_for_docker(
            original_command_list=task_command_list,
            container_image_name=task_info.docker_image_name,
            task_id=task_id,
            privileged=task_info.docker_privileged,
            mount_dirs=task_info.docker_additional_mounts
            + [
                f"{RUNNER_CONFIG.SHARED_DIR}/shared_data:/shared",
                f"{RUNNER_CONFIG.LOCAL_TEMP_DIR}:/local_temp",
            ]
            + get_executable_and_library_mounts(RunnerConfig.NUMACTL_PATH)[1],
            working_dir="/shared",
        )
        inner_cmd_parts = docker_wrapper_cmd
    inner_cmd_str = " ".join(inner_cmd_parts)
    return inner_cmd_str

def build(
    task_info: TaskInfo,
    *,
    working_dir: str,
    unit_name: str,
    total_cores: int,
    numactl_prefix: str,
):
    """
    Builds the command to run the task using systemd.
    """
    task_id = task_info.task_id
    run_cmd = [
        "sudo",
        "systemd-run",
        "--scope",  # Run as a transient scope unit
        "--collect",  # Garbage collect unit when process exits
        f"--property=User={RUNNER_CONFIG.RUNNER_USER}",  # Run as the current user (or specify another user)
        f"--unit={unit_name}",
        # Basic description
        f"--description=HakuRiver Task {task_id}: {shlex.quote(task_info.command)}",
    ]

    # Append resource allocation properties
    append_resource_alloc_options(task_info, run_cmd, total_cores)

    # Append nvironment variables options
    append_env_options(task_info, run_cmd)

    # Working Directory (Optional - run in shared or temp?)
    run_cmd.append(f"--working-directory={working_dir}")  # Example

    # Command and Arguments with Redirection
    # This is complex due to shell quoting needed inside systemd-run
    inner_cmd_str = build_inner_cmd(task_info)

    # Ensure stdout/stderr paths are absolute and quoted if they contain spaces
    quoted_stdout = shlex.quote(task_info.stdout_path)
    quoted_stderr = shlex.quote(task_info.stderr_path)

    shell_command = (
        f"exec {numactl_prefix}{inner_cmd_str} > {quoted_stdout} 2> {quoted_stderr}"
    )
    run_cmd.extend(["/bin/sh", "-c", shell_command])
    return run_cmd
