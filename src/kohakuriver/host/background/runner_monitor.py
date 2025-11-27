"""
Runner monitoring background task.

Detects dead runners and marks their tasks as lost.
"""

import asyncio
import datetime
import logging

from kohakuriver.db.node import Node
from kohakuriver.db.task import Task
from kohakuriver.host.config import config

logger = logging.getLogger(__name__)


async def check_dead_runners():
    """
    Check for runners that have missed heartbeats.

    Marks offline runners and their running tasks as lost.
    """
    while True:
        await asyncio.sleep(config.CLEANUP_CHECK_INTERVAL_SECONDS)

        # Calculate timeout threshold
        timeout_threshold = datetime.datetime.now() - datetime.timedelta(
            seconds=config.HEARTBEAT_INTERVAL_SECONDS * config.HEARTBEAT_TIMEOUT_FACTOR
        )

        try:
            # Find nodes marked 'online' with stale heartbeats
            dead_nodes: list[Node] = list(
                Node.select().where(
                    (Node.status == "online")
                    & (Node.last_heartbeat < timeout_threshold)
                )
            )

            if not dead_nodes:
                continue

            for node in dead_nodes:
                logger.warning(
                    f"Runner {node.hostname} missed heartbeat threshold "
                    f"(last seen: {node.last_heartbeat}). Marking as offline."
                )
                node.status = "offline"
                node.save()

                # Mark running/assigning tasks as lost
                tasks_to_fail: list[Task] = list(
                    Task.select().where(
                        (Task.assigned_node == node.hostname)
                        & (Task.status.in_(["running", "assigning"]))
                    )
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
                    task.exit_code = -1
                    task.save()

        except Exception as e:
            logger.error(f"Error checking dead runners: {e}")
