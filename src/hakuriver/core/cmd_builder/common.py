import shlex

from hakuriver.utils.logger import logger
from hakuriver.core.task_info import TaskInfo
from hakuriver.core.config import RUNNER_CONFIG


def build_numactl_prefix(
    task_info: TaskInfo,
    numa_topology: dict[int, dict] | None,
):
    """
    Generates a numactl prefix for NUMA node binding based on task
    configuration.

    Returns an empty string if no NUMA binding can be applied, otherwise
    returns a numactl command prefix for binding CPU and memory to the
    specified NUMA node.
    """
    task_id = task_info.task_id
    numactl_prefix = ""
    if task_info.target_numa_node_id is not None and numa_topology is not None:
        if (
            RUNNER_CONFIG.NUMACTL_PATH
            and numa_topology
            and task_info.target_numa_node_id in numa_topology
        ):
            # Basic binding to both CPU and memory on the target node
            numa_id = task_info.target_numa_node_id
            # Use --interleave=all as a fallback if specific binds cause issues,
            # or fine-tune with --physcpubind= based on numa_topology[numa_id]['cores']
            numactl_prefix = f"{shlex.quote(RUNNER_CONFIG.NUMACTL_PATH)} --cpunodebind={numa_id} --membind={numa_id} "
            logger.info(f"Task {task_id}: Applying NUMA binding to node {numa_id}.")
        elif not RUNNER_CONFIG.NUMACTL_PATH:
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
    return numactl_prefix
