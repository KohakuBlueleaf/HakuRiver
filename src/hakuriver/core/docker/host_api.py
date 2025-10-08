import asyncio
import json
import os
import re
import subprocess

from fastapi import APIRouter, HTTPException, Path, Body
from .models import CreateContainerRequest, ContainerDetails, ListTarsDetail
from ...core.config import HOST_CONFIG
from ...utils import docker as docker_utils  # Use existing utils for consistency
from ...utils.logger import logger


router = APIRouter()

# --- Host Container Management (HTTP API using subprocess via docker_utils) ---


@router.get("/host/containers", response_model=list[ContainerDetails])
async def list_host_containers():
    """Lists Docker containers running (or stopped) on the Host machine."""
    logger.debug("Received request to list Host Docker containers.")
    try:
        # Use docker ps with JSON format for easy parsing
        # -a includes stopped containers which might be relevant for persistent ones
        cmd = ["docker", "ps", "-a", "--format", "{{json .}}", "--size=false"]
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            docker_utils._run_command,  # Use the utility function
            cmd,
            True,
            True,
            False,
        )

        containers = []
        # Output is newline-separated JSON objects
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                # Extract relevant fields (adjust based on actual `docker ps` output)
                containers.append(
                    ContainerDetails(
                        id=data.get("ID", "N/A"),
                        name=data.get("Names", "N/A"),
                        image=data.get("Image", "N/A"),
                        status=data.get("Status", "N/A"),
                    )
                )
            except json.JSONDecodeError:
                logger.warning(f"Could not parse JSON line from docker ps: {line}")
            except Exception as parse_exc:
                logger.warning(
                    f"Error processing container data line: {line}, Error: {parse_exc}"
                )

        logger.info(f"Found {len(containers)} containers on Host.")
        return containers

    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=500, detail=f"Docker command failed: {e.stderr}"
        )
    except FileNotFoundError:
        raise HTTPException(status_code=503)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail="Unexpected error listing containers."
        )


@router.post("/host/create", status_code=201)
async def create_host_container(req: CreateContainerRequest = Body(...)):
    """
    Creates a persistent Docker container on the Host machine.
    """
    logger.info(
        f"Received request to create Host container '{req.container_name}' from image '{req.image_name}'."
    )
    try:
        success = await asyncio.get_event_loop().run_in_executor(
            None, docker_utils.create_container, req.image_name, req.container_name
        )
        if success:
            logger.info(
                f"Host container '{req.container_name}' created or already exists."
            )
            return {
                "message": f"Container '{req.container_name}' created or already exists."
            }
        else:
            # create_container logs the specific error
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create container '{req.container_name}'. Check Host logs.",
            )
    except Exception as e:
        logger.exception(
            f"Unexpected error creating host container '{req.container_name}'."
        )
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@router.post("/host/delete/{container_name}", status_code=200)
async def delete_host_container(container_name: str = Path(...)):
    """Deletes a container (forcefully) from the Host machine."""
    logger.info(f"Received request to delete Host container '{container_name}'.")
    try:
        # Need to implement delete_container in docker_utils
        success = await asyncio.get_event_loop().run_in_executor(
            None,
            docker_utils.delete_container,  # Assumes this exists now
            container_name,
        )
        if success:
            logger.info(f"Host container '{container_name}' deleted.")
            return {"message": f"Container '{container_name}' deleted."}
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete container '{container_name}'. Check Host logs.",
            )
    except FileNotFoundError:
        raise HTTPException(status_code=503)
    except Exception as e:
        logger.exception(
            f"Unexpected error deleting host container '{container_name}'."
        )
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@router.post("/host/stop/{container_name}", status_code=200)
async def stop_host_container(container_name: str = Path(...)):
    """Stops a running container on the Host machine."""
    logger.info(f"Received request to stop Host container '{container_name}'.")
    try:
        # Need to implement stop_container in docker_utils
        success = await asyncio.get_event_loop().run_in_executor(
            None, docker_utils.stop_container, container_name  # Assumes this exists now
        )
        if success:
            logger.info(f"Host container '{container_name}' stopped.")
            return {"message": f"Container '{container_name}' stopped."}
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to stop container '{container_name}'. Check Host logs.",
            )
    except FileNotFoundError:
        raise HTTPException(status_code=503)
    except Exception as e:
        logger.exception(
            f"Unexpected error stopping host container '{container_name}'."
        )
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@router.post("/host/start/{container_name}", status_code=200)
async def start_host_container(container_name: str = Path(...)):
    """Starts a stopped container on the Host machine."""
    logger.info(f"Received request to start Host container '{container_name}'.")
    try:
        # Need to implement start_container in docker_utils
        success = await asyncio.get_event_loop().run_in_executor(
            None,
            docker_utils.start_container,  # Assumes this exists now
            container_name,
        )
        if success:
            logger.info(f"Host container '{container_name}' started.")
            return {"message": f"Container '{container_name}' started."}
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to start container '{container_name}'. Check Host logs.",
            )
    except FileNotFoundError:
        raise HTTPException(status_code=503)
    except Exception as e:
        logger.exception(
            f"Unexpected error starting host container '{container_name}'."
        )
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


# --- Tarball Management (Moved from host.py, using subprocess via docker_utils) ---


@router.post("/create_tar/{container_name}")
async def create_container_tar_endpoint(
    container_name: str = Path(
        ...,
        description="The name of the *existing* container on the Host to commit and create a tarball from.",
    )
):
    """
    Creates a new container tarball in the shared container directory by committing
    from an *existing* Docker container on the Host with the same name.
    """
    logger.info(
        f"Received request to create/refresh container tar for '{container_name}'."
    )
    container_tar_dir = HOST_CONFIG.CONTAINER_DIR

    if not os.path.isdir(container_tar_dir):
        logger.info(
            f"Container tar directory '{container_tar_dir}' not found on host. Creating..."
        )
        try:
            os.makedirs(container_tar_dir, exist_ok=True)
        except OSError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create container tar directory '{container_tar_dir}': {e}",
            )

    source_container_name = container_name  # Assume the source is the same name

    try:
        # Use run_in_executor as create_container_tar uses subprocess and can block
        tarball_path = await asyncio.get_event_loop().run_in_executor(
            None,
            docker_utils.create_container_tar,
            source_container_name,
            container_name,  # Use same name for HakuRiver convention
            container_tar_dir,
        )

        if tarball_path:
            logger.info(
                f"Successfully created/refreshed container tar for '{container_name}' at {tarball_path}"
            )
            return {
                "message": "Container tarball created/refreshed successfully.",
                "tarball_path": tarball_path,
            }
        else:
            detail = f"Failed to create/refresh container tar for '{container_name}'. Check Host logs."
            logger.error(detail)
            raise HTTPException(status_code=500, detail=detail)
    except FileNotFoundError:
        raise HTTPException(status_code=503)
    except Exception as e:
        logger.exception(
            f"Unexpected error during tar creation for '{container_name}'."
        )
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@router.get("/list", response_model=dict[str, ListTarsDetail])
async def list_docker_tars():
    """
    Lists all available HakuRiver container tarballs in the shared directory.
    """
    logger.debug("Received request to list Docker container tarballs.")
    container_tar_dir = HOST_CONFIG.CONTAINER_DIR

    if not os.path.isdir(container_tar_dir):
        raise HTTPException(
            status_code=500,
            detail=f"Shared container directory '{container_tar_dir}' not found on host.",
        )

    # List all unique container names based on tarball filenames
    container_names = set()
    pattern = re.compile(
        r"^([a-zA-Z0-9._-]+)-(\d+)\.tar$"
    )  # Allow dots and underscores in name
    try:
        for filename in os.listdir(container_tar_dir):
            match = pattern.match(filename)
            if match:
                container_names.add(match.group(1))
    except Exception as e:
        logger.exception(f"Error scanning shared directory {container_tar_dir}: {e}")
        raise HTTPException(status_code=500, detail="Error scanning shared directory.")

    results = {}
    for name in sorted(list(container_names)):
        # This utility function uses os.listdir, so it's not blocking significantly
        tars = docker_utils.list_shared_container_tars(container_tar_dir, name)
        if tars:
            latest_timestamp, latest_path = tars[0]
            results[name] = ListTarsDetail(
                latest_timestamp=latest_timestamp,
                latest_tarball=os.path.basename(latest_path),
                all_versions=[
                    {"timestamp": ts, "tarball": os.path.basename(p)} for ts, p in tars
                ],
            )

    logger.info(f"Found {len(results)} container types in shared directory.")
    return results
