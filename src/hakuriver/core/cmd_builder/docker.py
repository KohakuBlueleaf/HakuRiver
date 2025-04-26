import shlex

from hakuriver.utils import docker as docker_utils
from hakuriver.core.task_info import TaskInfo
from hakuriver.core.config import RUNNER_CONFIG


def build(
    task_info: TaskInfo,
    working_dir: str,
):
    task_id = task_info.task_id

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
            f"{working_dir}:/shared",
            f"{RUNNER_CONFIG.LOCAL_TEMP_DIR}:/local_temp",
        ],
        working_dir="/shared",
        cpu_cores=task_info.required_cores,
        memory_limit=(
            f"{task_info.required_memory_bytes/1e6:.1f}M"
            if task_info.required_memory_bytes
            else None
        ),
        gpu_ids=task_info.required_gpus,
    )
    inner_cmd_str = " ".join(docker_wrapper_cmd)
    shell_cmd = f"exec {inner_cmd_str} > {shlex.quote(task_info.stdout_path)} 2> {shlex.quote(task_info.stderr_path)}"
    run_cmd = ["sudo", "/bin/bash", "-c", shell_cmd]
    return run_cmd
