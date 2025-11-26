"""
Docker management endpoints.

Handles:
- Host Docker container management (list, create, start, stop, delete)
- HakuRiver container tarball management (list, create, download, delete)
"""
import logging
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from hakuriver.docker import utils as docker_utils
from hakuriver.docker.client import DockerManager
from hakuriver.host.config import config

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateContainerRequest(BaseModel):
    """Request body for creating a container."""
    image_name: str
    container_name: str


# =============================================================================
# Host Docker Container Management (/docker/host/*)
# =============================================================================


@router.get("/host/containers")
async def list_host_containers():
    """List all Docker containers on the Host (like old behavior).

    Returns all containers, not just HakuRiver-managed ones.
    This allows users to see and manage any container for environment setup.
    """
    try:
        docker_manager = DockerManager()
        # List ALL containers (like old code did with `docker ps -a`)
        containers = docker_manager.list_containers(all=True)

        result = []
        for container in containers:
            # Get image tag safely
            image_tags = container.image.tags if container.image.tags else []
            image_name = image_tags[0] if image_tags else container.image.short_id

            result.append({
                "id": container.short_id,
                "name": container.name,
                "image": image_name,
                "status": container.status,
                "created": container.attrs.get("Created"),
            })

        # Frontend expects array directly
        return result

    except Exception as e:
        logger.error(f"Error listing containers: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing containers: {e}")


@router.post("/host/create")
async def create_host_container(request: CreateContainerRequest):
    """Create a persistent Docker container on the Host."""
    logger.info(f"Creating container '{request.container_name}' from image '{request.image_name}'")

    try:
        docker_manager = DockerManager()

        # Check if container already exists
        if docker_manager.container_exists(request.container_name):
            raise HTTPException(
                status_code=409,
                detail=f"Container '{request.container_name}' already exists.",
            )

        # Create container (runs with sleep infinity)
        container = docker_manager.create_container(
            image=request.image_name,
            name=request.container_name,
            command="sleep infinity",
        )

        return {
            "message": f"Container '{request.container_name}' created successfully.",
            "container_id": container.short_id,
            "status": container.status,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating container: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating container: {e}")


@router.post("/host/delete/{container_name}")
async def delete_host_container(container_name: str):
    """Delete a Docker container on the Host."""
    logger.info(f"Deleting container '{container_name}'")

    try:
        docker_manager = DockerManager()

        if not docker_manager.container_exists(container_name):
            raise HTTPException(
                status_code=404,
                detail=f"Container '{container_name}' not found.",
            )

        success = docker_manager.remove_container(container_name, force=True)
        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete container '{container_name}'.",
            )

        return {"message": f"Container '{container_name}' deleted successfully."}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting container: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting container: {e}")


@router.post("/host/stop/{container_name}")
async def stop_host_container(container_name: str):
    """Stop a running Docker container on the Host."""
    logger.info(f"Stopping container '{container_name}'")

    try:
        docker_manager = DockerManager()

        if not docker_manager.container_exists(container_name):
            raise HTTPException(
                status_code=404,
                detail=f"Container '{container_name}' not found.",
            )

        success = docker_manager.stop_container(container_name)
        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to stop container '{container_name}'.",
            )

        return {"message": f"Container '{container_name}' stopped successfully."}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping container: {e}")
        raise HTTPException(status_code=500, detail=f"Error stopping container: {e}")


@router.post("/host/start/{container_name}")
async def start_host_container(container_name: str):
    """Start a stopped Docker container on the Host."""
    logger.info(f"Starting container '{container_name}'")

    try:
        docker_manager = DockerManager()

        if not docker_manager.container_exists(container_name):
            raise HTTPException(
                status_code=404,
                detail=f"Container '{container_name}' not found.",
            )

        success = docker_manager.start_container(container_name)
        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to start container '{container_name}'.",
            )

        return {"message": f"Container '{container_name}' started successfully."}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting container: {e}")
        raise HTTPException(status_code=500, detail=f"Error starting container: {e}")


# =============================================================================
# HakuRiver Container Tarball Management (/docker/*)
# =============================================================================


@router.get("/list")
async def list_tarballs():
    """List available HakuRiver container tarballs in the shared directory.

    Returns:
        Object with container names as keys, each containing:
        - latest_timestamp: Unix timestamp of latest version
        - latest_tarball: Filename of latest tarball
        - all_versions: List of all versions sorted by timestamp (newest first)
    """
    import re
    from collections import defaultdict

    container_dir = config.get_container_dir()

    if not os.path.isdir(container_dir):
        return {}

    # Group tarballs by container name
    # Tarball naming pattern: {container_name}-{timestamp}.tar (dash separator, not underscore)
    # Example: python-1732570234.tar -> container_name="python", timestamp=1732570234
    containers: dict[str, list[dict]] = defaultdict(list)

    for filename in os.listdir(container_dir):
        if not filename.endswith(".tar"):
            continue

        filepath = os.path.join(container_dir, filename)
        stat = os.stat(filepath)

        # Parse timestamp from filename: {name}-{timestamp}.tar
        # The timestamp is always a 10-digit unix timestamp at the end before .tar
        match = re.match(r"^(.+)-(\d{10,})\.tar$", filename)
        if match:
            container_name = match.group(1)
            timestamp = int(match.group(2))
        else:
            # No valid timestamp pattern, skip this file
            continue

        containers[container_name].append({
            "timestamp": timestamp,
            "tarball": filename,
            "size_bytes": stat.st_size,
        })

    # Build result object with latest_timestamp, latest_tarball, all_versions
    result = {}
    for name, versions in containers.items():
        # Sort by timestamp descending (newest first)
        versions.sort(key=lambda x: x["timestamp"], reverse=True)
        result[name] = {
            "latest_timestamp": versions[0]["timestamp"],
            "latest_tarball": versions[0]["tarball"],
            "all_versions": versions,
        }

    return result


@router.post("/create_tar/{container_name}")
async def create_tarball(container_name: str):
    """Create a HakuRiver container tarball from a Host container."""
    logger.info(f"Creating tarball from container '{container_name}'")

    try:
        docker_manager = DockerManager()

        if not docker_manager.container_exists(container_name):
            raise HTTPException(
                status_code=404,
                detail=f"Container '{container_name}' not found.",
            )

        # Create tarball
        tarball_path = docker_manager.create_container_tarball(
            source_container=container_name,
            hakuriver_name=container_name,
            container_tar_dir=config.get_container_dir(),
        )

        if not tarball_path:
            raise HTTPException(
                status_code=500,
                detail="Failed to create container tarball.",
            )

        logger.info(f"Container tarball created at {tarball_path}")

        return {
            "message": f"Tarball created from container '{container_name}'.",
            "tarball_path": tarball_path,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating tarball: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating tarball: {e}")


@router.get("/container/{name}")
async def download_container(name: str):
    """Download a container tarball."""
    container_dir = config.get_container_dir()

    # Try exact match first
    tarball_path = os.path.join(container_dir, f"{name}.tar")

    # If not found, try to find tarball with timestamp pattern
    if not os.path.exists(tarball_path):
        docker_manager = DockerManager()
        tarballs = docker_manager.list_shared_tarballs(container_dir, name)
        if tarballs:
            tarball_path = tarballs[0][1]  # Latest tarball

    if not os.path.exists(tarball_path):
        raise HTTPException(
            status_code=404,
            detail=f"Container '{name}' not found.",
        )

    return FileResponse(
        path=tarball_path,
        filename=os.path.basename(tarball_path),
        media_type="application/x-tar",
    )


@router.delete("/container/{name}")
async def delete_tarball(name: str):
    """Delete a container tarball."""
    container_dir = config.get_container_dir()

    # Find all tarballs matching this name
    docker_manager = DockerManager()
    tarballs = docker_manager.list_shared_tarballs(container_dir, name)

    # Also check for exact match
    exact_path = os.path.join(container_dir, f"{name}.tar")
    if os.path.exists(exact_path):
        tarballs.append((0, exact_path))

    if not tarballs:
        raise HTTPException(
            status_code=404,
            detail=f"Container '{name}' not found.",
        )

    try:
        for _, tarball_path in tarballs:
            os.remove(tarball_path)
            logger.info(f"Deleted container tarball: {tarball_path}")

        return {"message": f"Container '{name}' deleted."}

    except Exception as e:
        logger.error(f"Error deleting container: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting container: {e}",
        )
