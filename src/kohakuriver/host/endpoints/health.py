"""
Health Monitoring Endpoints.

Provides cluster health metrics and historical data.
Returns aggregated health information from all nodes.
"""

from fastapi import APIRouter, HTTPException, Query

from kohakuriver.host.background.health import health_datas
from kohakuriver.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Health Endpoints
# =============================================================================


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

    Args:
        hostname: Optional hostname to filter results to a single node.

    Returns:
        If hostname specified: List containing single node's latest data.
        Otherwise: Dict with 'nodes' and 'aggregate' historical data.
    """
    logger.debug(f"Health request (filter hostname: {hostname})")

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
