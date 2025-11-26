"""
Health monitoring endpoints.

Provides cluster health metrics and history.
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from hakuriver.host.background.health import health_datas

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def get_cluster_health(
    hostname: str | None = Query(
        None, description="Optional: Filter by specific hostname"
    )
):
    """
    Get cluster health status.

    Returns the last known health status (heartbeat data) and NUMA info for nodes.
    Provides 60 seconds of historical data at 1-second intervals.
    """
    logger.debug(f"Health request. Filter hostname: {hostname}")

    try:
        if hostname and health_datas:
            # Return specific node's latest data
            if hostname in health_datas[-1]:
                return [health_datas[-1][hostname]]
            raise HTTPException(
                status_code=404,
                detail=f"Node {hostname} not found in health data.",
            )

        return {
            "nodes": [
                [v for k, v in data.items() if k != "aggregate"]
                for data in health_datas
            ],
            "aggregate": [data.get("aggregate", {}) for data in health_datas],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching health data: {e}")
        raise HTTPException(
            status_code=500,
            detail="Error fetching health data.",
        )
