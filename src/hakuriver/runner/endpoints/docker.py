"""
Docker management endpoints.

Handles container image synchronization.
"""

import logging
import os

from fastapi import APIRouter, HTTPException

from hakuriver.docker import utils as docker_utils
from hakuriver.docker.client import DockerManager
from hakuriver.runner.config import config

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/docker/images")
async def list_images():
    """List locally available Docker images."""
    docker_manager = DockerManager()

    try:
        images = docker_manager.list_images()
        return {
            "images": [
                {
                    "id": img.id,
                    "tags": img.tags,
                    "created": img.attrs.get("Created"),
                    "size": img.attrs.get("Size"),
                }
                for img in images
            ]
        }
    except Exception as e:
        logger.error(f"Failed to list images: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list images: {e}",
        )


@router.post("/docker/sync/{container_name}")
async def sync_container(container_name: str):
    """
    Synchronize a container image from shared storage.

    This will check if the local image needs updating and sync from
    the shared tarball if necessary.
    """
    container_tar_dir = config.get_container_tar_dir()

    try:
        needs_sync, sync_path = docker_utils.needs_sync(
            container_name, container_tar_dir
        )

        if not needs_sync:
            return {
                "message": f"Container '{container_name}' is up-to-date.",
                "synced": False,
            }

        if not sync_path:
            raise HTTPException(
                status_code=404,
                detail=f"No tarball found for container '{container_name}'.",
            )

        sync_timeout = config.DOCKER_IMAGE_SYNC_TIMEOUT
        logger.info(
            f"Syncing container '{container_name}' from {sync_path} "
            f"(timeout: {sync_timeout}s)"
        )

        success = docker_utils.sync_from_shared(
            container_name, sync_path, timeout=sync_timeout
        )

        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to sync container '{container_name}'.",
            )

        return {
            "message": f"Container '{container_name}' synced successfully.",
            "synced": True,
            "source": sync_path,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing container: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error syncing container: {e}",
        )
