"""
VPS management endpoints.

Handles VPS creation and control requests.
"""
import logging
import os

from fastapi import APIRouter, HTTPException

from hakuriver.models.requests import VPSCreateRequest
from hakuriver.runner.config import config
from hakuriver.runner.services.vps_manager import (
    create_vps,
    pause_vps,
    resume_vps,
    stop_vps,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# These will be set by the app on startup
task_store = None


def set_dependencies(store):
    """Set module dependencies from app startup."""
    global task_store
    task_store = store


@router.post("/vps/create")
async def create_vps_endpoint(request: VPSCreateRequest):
    """Create a VPS container."""
    task_id = request.task_id

    # Check if already running
    if task_store and task_store.get_task(task_id):
        logger.warning(f"VPS {task_id} is already running.")
        raise HTTPException(
            status_code=409,
            detail=f"VPS {task_id} is already running on this node.",
        )

    # Check local temp directory
    if not os.path.isdir(config.LOCAL_TEMP_DIR):
        logger.error(
            f"Local temp directory '{config.LOCAL_TEMP_DIR}' not found."
        )
        raise HTTPException(
            status_code=500,
            detail=f"Configuration error: LOCAL_TEMP_DIR missing on node.",
        )

    logger.info(
        f"Creating VPS {task_id} with {request.required_cores} cores, "
        f"SSH port {request.ssh_port}"
    )

    result = await create_vps(
        task_id=task_id,
        required_cores=request.required_cores,
        required_gpus=request.required_gpus or [],
        required_memory_bytes=request.required_memory_bytes,
        target_numa_node_id=request.target_numa_node_id,
        container_name=request.container_name,
        ssh_public_key=request.ssh_public_key,
        ssh_port=request.ssh_port,
        task_store=task_store,
    )

    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "VPS creation failed."),
        )

    return result


@router.post("/vps/stop/{task_id}")
async def stop_vps_endpoint(task_id: int):
    """Stop a running VPS."""
    logger.info(f"Received stop request for VPS {task_id}")

    if not task_store or not task_store.get_task(task_id):
        logger.warning(f"Stop request for unknown VPS {task_id}")
        raise HTTPException(
            status_code=404,
            detail=f"VPS {task_id} not found.",
        )

    success = stop_vps(task_id, task_store)
    if not success:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop VPS {task_id}.",
        )

    return {"message": f"VPS {task_id} stopped."}


@router.post("/vps/pause/{task_id}")
async def pause_vps_endpoint(task_id: int):
    """Pause a running VPS."""
    logger.info(f"Received pause request for VPS {task_id}")

    if not task_store or not task_store.get_task(task_id):
        logger.warning(f"Pause request for unknown VPS {task_id}")
        raise HTTPException(
            status_code=404,
            detail=f"VPS {task_id} not found.",
        )

    success = pause_vps(task_id, task_store)
    if not success:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to pause VPS {task_id}.",
        )

    return {"message": f"VPS {task_id} paused."}


@router.post("/vps/resume/{task_id}")
async def resume_vps_endpoint(task_id: int):
    """Resume a paused VPS."""
    logger.info(f"Received resume request for VPS {task_id}")

    if not task_store or not task_store.get_task(task_id):
        logger.warning(f"Resume request for unknown VPS {task_id}")
        raise HTTPException(
            status_code=404,
            detail=f"VPS {task_id} not found.",
        )

    success = resume_vps(task_id, task_store)
    if not success:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to resume VPS {task_id}.",
        )

    return {"message": f"VPS {task_id} resumed."}
