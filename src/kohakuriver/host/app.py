"""
HakuRiver Host FastAPI Application.

Main entry point for the host server.
"""

import asyncio
import logging
import os

from fastapi import FastAPI, WebSocket, Path

from kohakuriver.db.base import db, initialize_database
from kohakuriver.docker.client import DockerManager
from kohakuriver.host.config import config
from kohakuriver.host.background.health import collate_health_data, health_datas
from kohakuriver.host.background.runner_monitor import check_dead_runners
from kohakuriver.host.endpoints import docker, health, nodes, tasks, vps
from kohakuriver.host.endpoints.docker_terminal import terminal_websocket_endpoint
from kohakuriver.host.endpoints.task_terminal import task_terminal_proxy_endpoint
from kohakuriver.ssh_proxy.server import start_server
from kohakuriver.utils.logger import configure_logging, format_traceback

logger = logging.getLogger(__name__)

# Background tasks set
background_tasks: set[asyncio.Task] = set()

# FastAPI app
app = FastAPI(
    title="HakuRiver Host",
    description="Cluster management host server",
    version="0.2.0",
)

# Include routers
app.include_router(tasks.router, tags=["Tasks"])
app.include_router(nodes.router, tags=["Nodes"])
app.include_router(vps.router, tags=["VPS"])
app.include_router(docker.router, prefix="/docker", tags=["Docker"])
app.include_router(health.router, tags=["Health"])


# WebSocket endpoint for Docker container terminal (host-side env containers)
@app.websocket("/docker/host/containers/{container_name}/terminal")
async def websocket_terminal_endpoint(
    websocket: WebSocket, container_name: str = Path(...)
):
    """WebSocket endpoint for interactive terminal access to host containers."""
    await terminal_websocket_endpoint(websocket, container_name=container_name)


# WebSocket endpoint for task/VPS terminal (proxied to runner)
@app.websocket("/task/{task_id}/terminal")
async def websocket_task_terminal_proxy(websocket: WebSocket, task_id: int = Path(...)):
    """WebSocket proxy for task/VPS terminal access on remote runners."""
    await task_terminal_proxy_endpoint(websocket, task_id=task_id)


async def startup_event():
    """Initialize database and start background tasks."""
    logger.debug(f"startup_event called, config.DB_FILE={config.DB_FILE}")
    initialize_database(config.DB_FILE)
    logger.info("Host server starting up.")
    logger.debug(f"Database file: {config.DB_FILE}")

    # Ensure container tar directory exists
    container_tar_dir = config.get_container_dir()
    if not os.path.isdir(container_tar_dir):
        logger.warning(
            f"Shared directory '{container_tar_dir}' does not exist. Creating..."
        )
        try:
            os.makedirs(container_tar_dir, exist_ok=True)
            logger.info(f"Shared directory created: {container_tar_dir}")
        except OSError as e:
            logger.critical(
                f"FATAL: Cannot create shared directory '{container_tar_dir}': {e}."
            )
            return

    # Clean up broken containers (missing images from failed migrations)
    try:
        await _cleanup_broken_containers()
    except Exception as e:
        logger.error(f"Failed to cleanup broken containers: {e}")
        logger.debug(format_traceback(e))

    # Initialize default container if needed
    try:
        await _ensure_default_container(container_tar_dir)
    except Exception as e:
        logger.error(f"Failed to initialize default container: {e}")
        logger.debug(format_traceback(e))

    # Start background tasks
    task_monitor = asyncio.create_task(check_dead_runners())
    task_health = asyncio.create_task(collate_health_data())
    task_ssh = asyncio.create_task(
        start_server(config.HOST_BIND_IP, config.HOST_SSH_PROXY_PORT)
    )

    for task in [task_monitor, task_health, task_ssh]:
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)


def _do_cleanup_broken_containers():
    """Remove HakuRiver environment containers with missing images (blocking)."""
    from kohakuriver.docker.naming import ENV_PREFIX

    docker_manager = DockerManager()
    containers = docker_manager.list_containers(all=True)

    for container in containers:
        # Only check HakuRiver environment containers
        if not container.name.startswith(f"{ENV_PREFIX}-"):
            continue

        # Check if image exists
        try:
            image = container.image
            # Try to access image properties - will fail if image is missing
            _ = image.id
        except Exception:
            # Image is missing - remove the broken container
            logger.warning(
                f"Found broken container '{container.name}' with missing image. Removing..."
            )
            try:
                container.remove(force=True)
                logger.info(f"Removed broken container '{container.name}'")
            except Exception as e:
                logger.error(
                    f"Failed to remove broken container '{container.name}': {e}"
                )


async def _cleanup_broken_containers():
    """Remove HakuRiver environment containers with missing images.

    This cleans up containers left in a broken state from failed migrations
    or other operations where the image was deleted but container remains.
    """
    import asyncio

    await asyncio.to_thread(_do_cleanup_broken_containers)


def _do_ensure_default_container(container_tar_dir: str):
    """Ensure default container and tarball exist (blocking)."""
    from kohakuriver.docker import utils as docker_utils
    from kohakuriver.docker.naming import ENV_PREFIX

    default_env_name = config.DEFAULT_CONTAINER_NAME
    initial_base_image = config.INITIAL_BASE_IMAGE

    # Full container name with prefix
    container_name = f"{ENV_PREFIX}-{default_env_name}"

    # Check if any tarball for the default container name exists
    shared_tars = docker_utils.list_shared_container_tars(
        container_tar_dir, default_env_name
    )

    if shared_tars:
        logger.info(
            f"Found existing shared tarball for default environment "
            f"'{default_env_name}'."
        )
        # Ensure the container also exists (for shell access)
        docker_manager = DockerManager()
        if not docker_manager.container_exists(container_name):
            # Also check legacy name (without prefix)
            if docker_manager.container_exists(default_env_name):
                logger.info(
                    f"Found legacy container '{default_env_name}' (without prefix)."
                )
            else:
                logger.info(
                    f"Environment container '{container_name}' not found. "
                    "Creating from tarball..."
                )
                # Load from tarball and create container
                latest_tar = shared_tars[0][1]
                docker_manager.load_image(latest_tar)
                docker_manager.create_container(
                    image=f"kohakuriver/{default_env_name}:base",
                    name=container_name,
                )
                logger.info(f"Environment container '{container_name}' created.")
        return

    logger.info(
        f"No shared tarball found for default environment '{default_env_name}'. "
        f"Creating from initial image '{initial_base_image}'."
    )

    docker_manager = DockerManager()

    # Create container from initial image with prefix
    docker_manager.create_container(
        image=initial_base_image,
        name=container_name,
    )

    # Export to tarball (tarball uses env_name without prefix)
    tarball_path = docker_manager.create_container_tarball(
        source_container=container_name,
        kohakuriver_name=default_env_name,
        container_tar_dir=container_tar_dir,
    )

    if tarball_path:
        logger.info(
            f"Default environment tarball created at {tarball_path}. "
            "Runners can now sync this base image."
        )
    else:
        logger.error(
            f"Failed to create default environment tarball from '{initial_base_image}'."
        )


async def _ensure_default_container(container_tar_dir: str):
    """Ensure default container and tarball exist.

    Creates the default environment container (kohakuriver-env-{name}) and its
    tarball if they don't exist.
    """
    import asyncio

    await asyncio.to_thread(_do_ensure_default_container, container_tar_dir)


async def shutdown_event():
    """Clean shutdown."""
    # Cancel background tasks
    for task in background_tasks:
        task.cancel()

    # Close database
    if not db.is_closed():
        db.close()

    logger.info("Host server shut down.")


app.add_event_handler("startup", startup_event)
app.add_event_handler("shutdown", shutdown_event)


def run():
    """Run the host server using uvicorn."""
    import uvicorn

    from kohakuriver.models.enums import LogLevel

    log_level = config.LOG_LEVEL

    # Configure HakuRiver logging
    configure_logging(log_level)

    match log_level:
        case LogLevel.FULL:
            uvicorn_level = "debug"
        case LogLevel.DEBUG:
            uvicorn_level = "debug"
        case LogLevel.INFO:
            uvicorn_level = "info"
        case LogLevel.WARNING:
            uvicorn_level = "warning"

    uvicorn.run(
        app,
        host=config.HOST_BIND_IP,
        port=config.HOST_PORT,
        log_level=uvicorn_level,
    )


def main():
    """Entry point for KohakuEngine."""
    run()


if __name__ == "__main__":
    main()
