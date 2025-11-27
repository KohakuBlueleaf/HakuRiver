"""
Health data collection background task.

Collects and aggregates cluster health metrics.
"""

import asyncio
import datetime
import logging

from kohakuriver.db.node import Node

logger = logging.getLogger(__name__)

# Health data history (last 60 seconds)
health_datas: list[dict] = []


async def collate_health_data():
    """
    Collect and aggregate health data for all nodes.

    Runs every second and keeps 60 seconds of history.
    """
    global health_datas

    while True:
        await asyncio.sleep(1)

        new_node_health: dict = {}
        aggregate_health = {
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

        try:
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

                if (
                    node.last_heartbeat
                    and node.last_heartbeat.isoformat()
                    > aggregate_health["lastUpdated"]
                ):
                    aggregate_health["lastUpdated"] = node.last_heartbeat.isoformat()

                aggregate_health["maxAvgCpuTemp"] = max(
                    aggregate_health["maxAvgCpuTemp"], node.current_avg_temp or 0
                )
                aggregate_health["maxMaxCpuTemp"] = max(
                    aggregate_health["maxMaxCpuTemp"], node.current_max_temp or 0
                )

            # Calculate averages
            if aggregate_health["totalCores"] > 0:
                aggregate_health["avgCpuPercent"] /= aggregate_health["totalCores"]
            if aggregate_health["totalMemBytes"] > 0:
                aggregate_health["avgMemPercent"] = (
                    aggregate_health["usedMemBytes"]
                    / aggregate_health["totalMemBytes"]
                    * 100
                )

            new_node_health["aggregate"] = aggregate_health
            health_datas.append(new_node_health)
            health_datas = health_datas[-60:]  # Keep only last 60 seconds

        except Exception as e:
            logger.error(f"Error collecting health data: {e}")
