"""
HakuRiver Host FastAPI Application.

Main entry point for the host server.
"""
import asyncio
import logging
import os

from fastapi import FastAPI

from hakuriver.db.base import db, initialize_database
from hakuriver.docker.client import DockerManager
from hakuriver.host.config import config
from hakuriver.host.background.health import collate_health_data, health_datas
from hakuriver.host.background.runner_monitor import check_dead_runners
from hakuriver.host.endpoints import docker, health, nodes, tasks, vps
from hakuriver.ssh_proxy.server import start_server
from hakuriver.utils.logger import configure_logging, format_traceback

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


async def _ensure_default_container(container_tar_dir: str):
    """Ensure default container tarball exists."""
    from hakuriver.docker import utils as docker_utils

    default_container_name = config.DEFAULT_CONTAINER_NAME
    initial_base_image = config.INITIAL_BASE_IMAGE

    # Check if any tarball for the default container name exists
    shared_tars = docker_utils.list_shared_container_tars(
        container_tar_dir, default_container_name
    )

    if shared_tars:
        logger.info(
            f"Found existing shared tarball for default container "
            f"'{default_container_name}'."
        )
        return

    logger.info(
        f"No shared tarball found for default container '{default_container_name}'. "
        f"Creating from initial image '{initial_base_image}'."
    )

    docker_manager = DockerManager()

    # Create container from initial image
    docker_manager.create_container(
        image=initial_base_image,
        name=default_container_name,
    )

    # Export to tarball
    tarball_path = docker_utils.create_container_tar(
        source_container_name=default_container_name,
        hakuriver_container_name=default_container_name,
        container_tar_dir=container_tar_dir,
    )

    if tarball_path:
        logger.info(
            f"Default container tarball created at {tarball_path}. "
            "Runners can now sync this base image."
        )
    else:
        logger.error(
            f"Failed to create default container tarball from '{initial_base_image}'."
        )


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

    from hakuriver.models.enums import LogLevel

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
