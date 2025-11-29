"""
Health Data Collection Background Task.

Collects and aggregates cluster health metrics from all nodes.
Maintains a rolling 60-second history of health data.
"""

import asyncio
import datetime

from kohakuriver.db.node import Node
from kohakuriver.utils.logger import get_logger

logger = get_logger(__name__)

# Health data history (last 60 seconds)
health_datas: list[dict] = []


# =============================================================================
# Background Task
# =============================================================================


async def collate_health_data() -> None:
    """
    Collect and aggregate health data for all nodes.

    Runs every second and keeps 60 seconds of history.
    This data is used by the /health endpoint for monitoring.
    """
    global health_datas

    while True:
        await asyncio.sleep(1)

        try:
            node_health, aggregate = _collect_node_metrics()
            node_health["aggregate"] = aggregate

            health_datas.append(node_health)
            health_datas = health_datas[-60:]  # Keep only last 60 seconds

        except Exception as e:
            logger.error(f"Error collecting health data: {e}")


# =============================================================================
# Helper Functions
# =============================================================================


def _collect_node_metrics() -> tuple[dict, dict]:
    """
    Collect metrics from all nodes.

    Returns:
        Tuple of (node_health_dict, aggregate_dict).
    """
    node_health: dict = {}
    aggregate = _create_empty_aggregate()

    for node in Node.select():
        node_health[node.hostname] = _build_node_health(node)
        _update_aggregate(aggregate, node)

    _finalize_aggregate(aggregate)
    return node_health, aggregate


def _create_empty_aggregate() -> dict:
    """Create an empty aggregate health structure."""
    return {
        "totalNodes": 0,
        "onlineNodes": 0,
        "totalCores": 0,
        "totalMemBytes": 0,
        "usedMemBytes": 0,
        "avgCpuPercent": 0.0,
        "avgMemPercent": 0.0,
        "maxAvgCpuTemp": 0.0,
        "maxMaxCpuTemp": 0.0,
        "lastUpdated": datetime.datetime.now().isoformat(),
    }


def _build_node_health(node: Node) -> dict:
    """Build health dictionary for a single node."""
    return {
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


def _update_aggregate(aggregate: dict, node: Node) -> None:
    """Update aggregate metrics with data from a node."""
    aggregate["totalNodes"] += 1

    if node.status == "online":
        aggregate["onlineNodes"] += 1

    aggregate["totalCores"] += node.total_cores or 0
    aggregate["totalMemBytes"] += node.memory_total_bytes or 0
    aggregate["usedMemBytes"] += node.memory_used_bytes or 0

    # Weight CPU percent by core count
    aggregate["avgCpuPercent"] += (node.cpu_percent or 0) * (node.total_cores or 0)

    # Track latest heartbeat
    if node.last_heartbeat:
        node_timestamp = node.last_heartbeat.isoformat()
        if node_timestamp > aggregate["lastUpdated"]:
            aggregate["lastUpdated"] = node_timestamp

    # Track max temperatures
    aggregate["maxAvgCpuTemp"] = max(
        aggregate["maxAvgCpuTemp"], node.current_avg_temp or 0
    )
    aggregate["maxMaxCpuTemp"] = max(
        aggregate["maxMaxCpuTemp"], node.current_max_temp or 0
    )


def _finalize_aggregate(aggregate: dict) -> None:
    """Calculate final aggregate averages."""
    if aggregate["totalCores"] > 0:
        aggregate["avgCpuPercent"] /= aggregate["totalCores"]

    if aggregate["totalMemBytes"] > 0:
        aggregate["avgMemPercent"] = (
            aggregate["usedMemBytes"] / aggregate["totalMemBytes"] * 100
        )
