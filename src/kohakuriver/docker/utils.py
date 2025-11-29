"""
Docker utility functions for image management.

This module provides standalone utility functions for container tarball
management and image synchronization. These functions are used for
distributing container images across cluster nodes via shared storage.

Functions:
    - list_shared_container_tars: List available tarballs in shared storage
    - get_local_image_timestamp: Get creation time of local image
    - needs_sync: Check if local image needs update from shared storage
    - sync_from_shared: Load image from tarball
    - create_container_tar: Create tarball from existing container
"""

import datetime
import os
import re
import time

import docker

from kohakuriver.docker.naming import image_tag
from kohakuriver.utils.logger import get_logger

log = get_logger(__name__)


# =============================================================================
# Tarball Listing
# =============================================================================


def list_shared_container_tars(
    container_tar_dir: str,
    container_name: str,
) -> list[tuple[int, str]]:
    """
    List available container tarballs in a directory.

    Scans for files matching the pattern: {container_name}-{timestamp}.tar

    Args:
        container_tar_dir: Path to directory containing tarballs.
        container_name: HakuRiver container name.

    Returns:
        List of (timestamp, filepath) tuples, sorted newest first.
    """
    if not os.path.isdir(container_tar_dir):
        log.debug(f"Container tar directory not found: {container_tar_dir}")
        return []

    pattern = re.compile(rf"^{re.escape(container_name.lower())}-(\d+)\.tar$")
    tar_files: list[tuple[int, str]] = []

    try:
        for filename in os.listdir(container_tar_dir):
            match = pattern.match(filename)
            if match:
                try:
                    timestamp = int(match.group(1))
                    tar_path = os.path.join(container_tar_dir, filename)
                    tar_files.append((timestamp, tar_path))
                except ValueError:
                    log.warning(f"Skipping malformed tarball filename: {filename}")
    except OSError as e:
        log.error(f"Error listing container tars in {container_tar_dir}: {e}")
        return []

    tar_files.sort(key=lambda item: item[0], reverse=True)
    return tar_files


# =============================================================================
# Image Timestamp
# =============================================================================


def get_local_image_timestamp(container_name: str) -> int | None:
    """
    Get the creation timestamp of the local HakuRiver image.

    Args:
        container_name: HakuRiver container name.

    Returns:
        Creation timestamp as Unix time, or None if image not found.
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
        log.debug(f"Local image {tag} not found")
        return None
    except Exception as e:
        log.error(f"Error inspecting local image {tag}: {e}")
        return None


# =============================================================================
# Sync Operations
# =============================================================================


def needs_sync(
    container_name: str,
    container_tar_dir: str,
) -> tuple[bool, str | None]:
    """
    Check if the local image needs to be synced from shared storage.

    Compares local image timestamp against available tarballs.

    Args:
        container_name: HakuRiver container name.
        container_tar_dir: Path to directory containing tarballs.

    Returns:
        Tuple of (needs_sync, path_to_latest_tar).
        If no sync needed or no tarballs available, path is None.
    """
    local_timestamp = get_local_image_timestamp(container_name)
    shared_tars = list_shared_container_tars(container_tar_dir, container_name)

    if not shared_tars:
        log.debug(f"No shared tarballs found for container '{container_name}'")
        return False, None

    latest_timestamp, latest_path = shared_tars[0]

    if local_timestamp is None:
        log.info(f"Local image '{container_name}' not found, sync needed")
        return True, latest_path

    if latest_timestamp > local_timestamp:
        log.info(
            f"Newer tarball found for '{container_name}' "
            f"(shared: {latest_timestamp}, local: {local_timestamp})"
        )
        return True, latest_path

    log.debug(f"Local image '{container_name}' is up-to-date")
    return False, None


def sync_from_shared(
    container_name: str,
    tarball_path: str,
    timeout: int = 600,
) -> bool:
    """
    Load a container image from a tarball into local Docker.

    Args:
        container_name: HakuRiver container name (for logging and tagging).
        tarball_path: Path to the .tar file.
        timeout: Timeout hint (currently not enforced by docker-py).

    Returns:
        True if sync was successful, False otherwise.
    """
    log.info(f"Syncing image for '{container_name}' from: {tarball_path}")

    if not os.path.exists(tarball_path):
        log.error(f"Tarball not found: {tarball_path}")
        return False

    try:
        client = docker.from_env(timeout=None)

        with open(tarball_path, "rb") as f:
            images = client.images.load(f)

        if not images:
            log.error(f"No images loaded from {tarball_path}")
            return False

        loaded_image = images[0]
        expected_tag = image_tag(container_name)

        log.debug(f"Loaded image: {loaded_image.id}, tags: {loaded_image.tags}")

        # Tag image if it doesn't have the expected tag
        if expected_tag not in (loaded_image.tags or []):
            log.warning(
                f"Loaded image missing expected tag '{expected_tag}', tagging..."
            )
            try:
                loaded_image.tag(expected_tag)
                log.info(f"Tagged image as '{expected_tag}'")
            except Exception as e:
                log.error(f"Failed to tag image: {e}")
                return False

        log.info(f"Successfully synced image '{expected_tag}'")
        return True

    except Exception as e:
        log.error(f"Failed to load image from {tarball_path}: {e}")
        return False


# =============================================================================
# Tarball Creation
# =============================================================================


def create_container_tar(
    source_container_name: str,
    kohakuriver_container_name: str,
    container_tar_dir: str,
) -> str | None:
    """
    Create a HakuRiver container tarball from an existing Docker container.

    This commits the container to an image and saves it as a tarball
    for distribution to other nodes via shared storage.

    Args:
        source_container_name: Name of the container to commit.
        kohakuriver_container_name: HakuRiver container name for the image.
        container_tar_dir: Directory to store the tarball.

    Returns:
        Path to the created tarball, or None if failed.
    """
    tag = image_tag(kohakuriver_container_name)
    timestamp = int(time.time())
    tarball_filename = f"{kohakuriver_container_name.lower()}-{timestamp}.tar"
    tarball_path = os.path.join(container_tar_dir, tarball_filename)

    log.info(
        f"Creating tarball for '{kohakuriver_container_name}' "
        f"from container '{source_container_name}'"
    )

    try:
        client = docker.from_env(timeout=None)

        # Get and stop the source container
        container = _get_and_stop_container(client, source_container_name)
        if container is None:
            return None

        # Commit container to image
        _commit_container(container, tag)

        # Save image to tarball
        image = client.images.get(tag)
        _save_image_to_tarball(image, tarball_path, container_tar_dir)

        # Clean up old tarballs
        _cleanup_old_tarballs(container_tar_dir, kohakuriver_container_name, timestamp)

        # Prune dangling images
        _prune_dangling_images(client)

        log.info(f"Created tarball at {tarball_path}")
        return tarball_path

    except Exception as e:
        log.error(f"Failed to create container tarball: {e}")
        return None


def _get_and_stop_container(client, container_name: str):
    """Get a container and stop it for consistent commit."""
    try:
        container = client.containers.get(container_name)
    except docker.errors.NotFound:
        log.error(f"Source container '{container_name}' not found")
        return None

    log.info(f"Stopping container '{container_name}'...")
    try:
        container.stop(timeout=10)
    except Exception:
        pass  # May already be stopped

    return container


def _commit_container(container, tag: str) -> None:
    """Commit a container to an image."""
    repository, image_tag_part = tag.rsplit(":", 1)
    log.info(f"Committing container to image {tag}")
    container.commit(repository=repository, tag=image_tag_part)
    log.info(f"Committed to image: {tag}")


def _save_image_to_tarball(image, tarball_path: str, container_tar_dir: str) -> None:
    """Save an image to a tarball file."""
    os.makedirs(container_tar_dir, exist_ok=True)

    log.info(f"Saving image to {tarball_path}")
    with open(tarball_path, "wb") as f:
        for chunk in image.save(named=True):
            f.write(chunk)


def _cleanup_old_tarballs(
    container_tar_dir: str,
    container_name: str,
    current_timestamp: int,
) -> None:
    """Remove older tarballs for a container."""
    for old_timestamp, old_path in list_shared_container_tars(
        container_tar_dir, container_name
    ):
        if old_timestamp < current_timestamp:
            log.info(f"Removing older tarball: {old_path}")
            try:
                os.remove(old_path)
            except OSError as e:
                log.warning(f"Failed to remove old tarball {old_path}: {e}")


def _prune_dangling_images(client) -> None:
    """Prune dangling Docker images."""
    log.debug("Cleaning up dangling images...")
    try:
        client.images.prune(filters={"dangling": True})
    except Exception:
        pass
