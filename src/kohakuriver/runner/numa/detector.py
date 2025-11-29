"""
NUMA topology detection.

Detects NUMA nodes and their CPU/memory assignments.
"""

import re
import subprocess

from kohakuriver.runner.config import config
from kohakuriver.utils.logger import get_logger

logger = get_logger(__name__)


def detect_numa_topology() -> dict | None:
    """
    Detect NUMA topology by parsing `numactl --hardware` output.

    Returns:
        Dictionary mapping node IDs to their cores and memory, or None if
        NUMA is not available or detection fails.

        Example:
        {
            0: {"cores": [0, 1, 2, 3], "memory_bytes": 68719476736},
            1: {"cores": [4, 5, 6, 7], "memory_bytes": 68719476736},
        }
    """
    numactl_path = config.NUMACTL_PATH
    if not numactl_path:
        logger.info("numactl path not configured, skipping NUMA detection.")
        return None

    try:
        cmd = [numactl_path, "-H"]
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, encoding="utf-8"
        )
        output = result.stdout

        topology: dict[int, dict] = {}

        # Parse node CPU lines: node 0 cpus: 0 1 2 3 4 5 6 7
        node_cpu_match = re.findall(r"node (\d+) cpus:((?:\s+\d+)+)", output)

        # Parse node memory lines: node 0 size: 64215 MB
        node_mem_match = re.findall(
            r"node (\d+) size: (\d+)\s*((?:MB|GB|kB))", output, re.IGNORECASE
        )

        if not node_cpu_match:
            logger.warning(
                f"`{numactl_path} --hardware` did not contain expected CPU info."
            )
            return None

        # Parse CPU assignments
        for node_id_str, cpu_list_str in node_cpu_match:
            node_id = int(node_id_str)
            cores = [int(cpu) for cpu in cpu_list_str.split()]
            topology[node_id] = {
                "cores": cores,
                "memory_bytes": None,
            }

        # Parse memory assignments
        for node_id_str, mem_size_str, mem_unit in node_mem_match:
            node_id = int(node_id_str)
            if node_id in topology:
                size = int(mem_size_str)
                unit = mem_unit.upper()
                match unit:
                    case "GB":
                        topology[node_id]["memory_bytes"] = size * 1024 * 1024 * 1024
                    case "MB":
                        topology[node_id]["memory_bytes"] = size * 1024 * 1024
                    case "KB":
                        topology[node_id]["memory_bytes"] = size * 1024
                    case _:
                        topology[node_id]["memory_bytes"] = size

        if not topology:
            logger.info("No NUMA nodes detected.")
            return None

        logger.info(f"Detected NUMA topology: {len(topology)} nodes")
        return topology

    except FileNotFoundError:
        logger.error(f"`{numactl_path}` not found. Cannot detect NUMA topology.")
        return None
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running `{numactl_path} --hardware`: {e.stderr}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error during NUMA detection: {e}")
        return None


def get_numa_prefix(numa_node_id: int | None, numa_topology: dict | None) -> str:
    """
    Get numactl command prefix for binding to a NUMA node.

    Args:
        numa_node_id: Target NUMA node ID, or None for no binding.
        numa_topology: Detected NUMA topology.

    Returns:
        numactl command prefix string, or empty string if not applicable.
    """
    if numa_node_id is None:
        return ""

    numactl_path = config.NUMACTL_PATH
    if not numactl_path:
        logger.warning(
            f"Target NUMA node {numa_node_id} specified, but numactl not configured."
        )
        return ""

    if numa_topology is None:
        logger.warning(
            f"Target NUMA node {numa_node_id} specified, but NUMA not detected."
        )
        return ""

    if numa_node_id not in numa_topology:
        logger.warning(
            f"Target NUMA node {numa_node_id} not in detected topology "
            f"{list(numa_topology.keys())}."
        )
        return ""

    # Bind to both CPU and memory on the target node
    return f"{numactl_path} --cpunodebind={numa_node_id} --membind={numa_node_id}"
