"""
Docker utility functions for image management.

Provides functions for container tarball management and image syncing.
"""

import datetime
import json
import logging
import os
import re
import time

import docker

from kohakuriver.docker.naming import image_tag

logger = logging.getLogger(__name__)


def list_shared_container_tars(
    container_tar_dir: str,
    container_name: str,
) -> list[tuple[int, str]]:
    """
    List available container tarballs in the specified directory.

    Args:
        container_tar_dir: Path to directory containing tarballs.
        container_name: HakuRiver container name.

    Returns:
        List of (timestamp, filepath) tuples, sorted newest first.
    """
    tar_files = []
    pattern = re.compile(rf"^{re.escape(container_name.lower())}-(\d+)\.tar$")

    try:
        if not os.path.isdir(container_tar_dir):
            logger.warning(f"Container tar directory not found: {container_tar_dir}")
            return []

        for filename in os.listdir(container_tar_dir):
            match = pattern.match(filename)
            if match:
                try:
                    timestamp = int(match.group(1))
                    tar_path = os.path.join(container_tar_dir, filename)
                    tar_files.append((timestamp, tar_path))
                except ValueError:
                    logger.warning(f"Skipping malformed tarball filename: {filename}")

    except Exception as e:
        logger.exception(f"Error listing container tars in {container_tar_dir}: {e}")
        return []

    tar_files.sort(key=lambda item: item[0], reverse=True)
    return tar_files


def get_local_image_timestamp(container_name: str) -> int | None:
    """
    Get the creation timestamp of the local HakuRiver base image.

    Args:
        container_name: HakuRiver container name.

    Returns:
        Creation timestamp as Unix time, or None if not found.
    """
    tag = image_tag(container_name)

    try:
        client = docker.from_env(timeout=None)
        image = client.images.get(tag)
        created_str = image.attrs.get("Created")

        if created_str:
            dt_obj = datetime.datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            return int(dt_obj.timestamp())
        return None

    except docker.errors.ImageNotFound:
        logger.debug(f"Local image {tag} not found.")
        return None
    except Exception as e:
        logger.error(f"Error inspecting local image {tag}: {e}")
        return None


def needs_sync(
    container_name: str,
    container_tar_dir: str,
) -> tuple[bool, str | None]:
    """
    Check if the local image needs to be synced from shared storage.

    Args:
        container_name: HakuRiver container name.
        container_tar_dir: Path to directory containing tarballs.

    Returns:
        Tuple of (needs_sync, path_to_latest_tar).
    """
    local_timestamp = get_local_image_timestamp(container_name)
    shared_tars = list_shared_container_tars(container_tar_dir, container_name)

    if not shared_tars:
        logger.debug(f"No shared tarballs found for container '{container_name}'.")
        return False, None

    latest_timestamp, latest_path = shared_tars[0]

    if local_timestamp is None:
        logger.info(
            f"Local image '{container_name}' not found. Sync needed from {latest_path}."
        )
        return True, latest_path

    if latest_timestamp > local_timestamp:
        logger.info(
            f"Newer shared tarball found for '{container_name}' "
            f"(shared: {latest_timestamp}, local: {local_timestamp}). "
            f"Sync needed from {latest_path}."
        )
        return True, latest_path

    logger.debug(
        f"Local image '{container_name}' is up-to-date "
        f"(local: {local_timestamp}, latest shared: {latest_timestamp})."
    )
    return False, None


def sync_from_shared(
    container_name: str,
    tarball_path: str,
    timeout: int = 600,
) -> bool:
    """
    Load a container image from a tarball into local Docker registry.

    Args:
        container_name: HakuRiver container name (for logging).
        tarball_path: Path to the .tar file.
        timeout: Timeout in seconds for the Docker image load operation.
                 Default 600 (10 minutes) for large images (10-30GB).

    Returns:
        True if sync was successful.
    """
    logger.info(
        f"Syncing image for container '{container_name}' from tarball: {tarball_path} "
        f"(timeout: {timeout}s)"
    )

    if not os.path.exists(tarball_path):
        logger.error(f"Tarball not found: {tarball_path}")
        return False

    try:
        # Create client with no timeout for large image loads (timeout param is legacy, ignored)
        client = docker.from_env(timeout=None)

        with open(tarball_path, "rb") as f:
            images = client.images.load(f)

        if not images:
            logger.error(f"No images loaded from {tarball_path}.")
            return False

        loaded_image = images[0]
        expected_tag = image_tag(container_name)

        logger.info(f"Loaded image: {loaded_image.id}, tags: {loaded_image.tags}")

        # Check if image has the expected tag
        if expected_tag not in (loaded_image.tags or []):
            # Image loaded without proper tag (legacy tarball with RepoTags: null)
            # Tag it manually
            logger.warning(
                f"Loaded image missing expected tag '{expected_tag}'. "
                f"Tagging manually..."
            )
            try:
                loaded_image.tag(expected_tag)
                logger.info(f"Successfully tagged image as '{expected_tag}'")
            except Exception as e:
                logger.error(f"Failed to tag image: {e}")
                return False

        logger.info(f"Successfully synced image '{expected_tag}' from {tarball_path}.")
        return True

    except Exception as e:
        logger.error(f"Failed to load image from {tarball_path}: {e}")
        return False


def create_container_tar(
    source_container_name: str,
    kohakuriver_container_name: str,
    container_tar_dir: str,
) -> str | None:
    """
    Create a KohakuRiver container tarball from an existing Docker container.

    Args:
        source_container_name: Name of the container to commit from.
        kohakuriver_container_name: KohakuRiver container name.
        container_tar_dir: Path to store the tarball.

    Returns:
        Path to the created tarball, or None if failed.
    """
    tag = image_tag(kohakuriver_container_name)
    timestamp = int(time.time())
    tarball_filename = f"{kohakuriver_container_name.lower()}-{timestamp}.tar"
    tarball_path = os.path.join(container_tar_dir, tarball_filename)

    logger.info(
        f"Creating tarball for '{kohakuriver_container_name}' "
        f"from container '{source_container_name}'"
    )

    try:
        client = docker.from_env(timeout=None)

        # Get the source container
        try:
            container = client.containers.get(source_container_name)
        except docker.errors.NotFound:
            logger.error(f"Source container '{source_container_name}' not found.")
            return None

        # Stop container for consistent commit
        logger.info(f"Stopping container '{source_container_name}'...")
        try:
            container.stop(timeout=10)
        except Exception:
            pass  # May already be stopped

        # Commit the container to a new image
        logger.info(f"Committing container to image {tag}")
        container.commit(repository=tag.split(":")[0], tag="base")
        logger.info(f"Committed to image: {tag}")

        # Get the image by tag (commit returns image without proper tag reference for save)
        image = client.images.get(tag)
        logger.info(f"Got image for saving: {image.tags}")

        # Ensure directory exists
        os.makedirs(container_tar_dir, exist_ok=True)

        # Save the image to tarball
        logger.info(f"Saving image to {tarball_path}")
        with open(tarball_path, "wb") as f:
            for chunk in image.save(named=True):
                f.write(chunk)

        logger.info(f"Tarball created at {tarball_path}")

        # Clean up old tarballs
        for old_timestamp, old_path in list_shared_container_tars(
            container_tar_dir, kohakuriver_container_name
        ):
            if old_timestamp < timestamp:
                logger.info(f"Removing older tarball: {old_path}")
                try:
                    os.remove(old_path)
                except OSError as e:
                    logger.warning(f"Failed to remove old tarball {old_path}: {e}")

        # Prune dangling images
        logger.info("Cleaning up dangling images...")
        try:
            client.images.prune(filters={"dangling": True})
        except Exception:
            pass

        return tarball_path

    except Exception as e:
        logger.error(f"Failed to create container tarball: {e}")
        return None
