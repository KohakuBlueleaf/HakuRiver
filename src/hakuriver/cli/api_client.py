"""
API client for CLI commands.

Provides functions to interact with the HakuRiver host API.
"""
import json
import logging

import httpx

from hakuriver.cli import config as CLI_CONFIG

logger = logging.getLogger(__name__)


def _get_host_url() -> str:
    """Get the host URL from config."""
    return f"http://{CLI_CONFIG.HOST_ADDRESS}:{CLI_CONFIG.HOST_PORT}"


def list_nodes():
    """List all registered nodes."""
    url = f"{_get_host_url()}/nodes"
    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        nodes = response.json()

        if not nodes:
            print("No nodes registered.")
            return

        print(f"{'Hostname':<20} {'Status':<10} {'Cores':<8} {'Available':<10} {'URL'}")
        print("-" * 80)
        for node in nodes:
            hostname = node.get("hostname", "?")
            status = node.get("status", "?")
            total = node.get("total_cores", "?")
            available = node.get("available_cores", "?")
            url_val = node.get("url", "?")
            print(f"{hostname:<20} {status:<10} {total:<8} {available:<10} {url_val}")

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error: {e.response.status_code}")
        raise
    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        raise


def get_health(hostname: str | None = None):
    """Get health status for nodes."""
    url = f"{_get_host_url()}/health"
    if hostname:
        url += f"?hostname={hostname}"

    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        health_data = response.json()
        print(json.dumps(health_data, indent=2))

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error: {e.response.status_code}")
        raise
    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        raise


def check_status(task_id: str):
    """Check status of a task."""
    url = f"{_get_host_url()}/status/{task_id}"

    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        task_data = response.json()
        print(json.dumps(task_data, indent=2))

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            print(f"Task {task_id} not found.")
        else:
            logger.error(f"HTTP error: {e.response.status_code}")
        raise
    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        raise


def kill_task(task_id: str):
    """Kill a task."""
    url = f"{_get_host_url()}/kill/{task_id}"

    try:
        response = httpx.post(url, timeout=10.0)
        response.raise_for_status()
        result = response.json()
        print(result.get("message", "Kill request sent."))

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            print(f"Task {task_id} not found.")
        elif e.response.status_code == 409:
            print(f"Task {task_id} cannot be killed (already finished).")
        else:
            logger.error(f"HTTP error: {e.response.status_code}")
        raise
    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        raise


def send_task_command(task_id: str, action: str):
    """Send a control command (pause/resume) to a task."""
    url = f"{_get_host_url()}/command/{task_id}/{action}"

    try:
        response = httpx.post(url, timeout=10.0)
        response.raise_for_status()
        result = response.json()
        print(result.get("message", f"{action.capitalize()} command sent."))

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            print(f"Task {task_id} not found.")
        elif e.response.status_code == 400:
            print(f"Invalid command or task state.")
        else:
            logger.error(f"HTTP error: {e.response.status_code}")
        raise
    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        raise


def submit_task(
    command: str,
    args: list[str],
    env: dict[str, str],
    cores: int,
    memory_bytes: int | None,
    targets: list[str],
    container_name: str | None,
    privileged: bool | None,
    additional_mounts: list[str] | None,
    gpu_ids: list[list[int]],
) -> list[str]:
    """Submit a standard task and return task IDs."""
    url = f"{_get_host_url()}/submit"

    payload = {
        "command": command,
        "args": args,
        "env": env,
        "cores": cores,
        "memory_bytes": memory_bytes,
        "targets": targets,
        "container_name": container_name,
        "privileged": privileged,
        "additional_mounts": additional_mounts,
        "gpu_ids": gpu_ids,
    }

    try:
        response = httpx.post(url, json=payload, timeout=30.0)
        response.raise_for_status()
        result = response.json()
        return result.get("task_ids", [])

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error: {e.response.status_code}")
        try:
            error_detail = e.response.json()
            logger.error(f"Error detail: {error_detail}")
        except Exception:
            pass
        raise
    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        raise


def get_task_status(task_id: str) -> dict | None:
    """Get task status as dict (for wait loop)."""
    url = f"{_get_host_url()}/status/{task_id}"

    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        return response.json()

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        raise
    except httpx.RequestError:
        return None


def get_task_stdout(task_id: str):
    """Get stdout for a task."""
    url = f"{_get_host_url()}/task/{task_id}/stdout"

    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        result = response.json()
        stdout_content = result.get("stdout", "")
        print(stdout_content)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            print(f"Task {task_id} not found.")
        else:
            logger.error(f"HTTP error: {e.response.status_code}")
        raise
    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        raise


def get_task_stderr(task_id: str):
    """Get stderr for a task."""
    url = f"{_get_host_url()}/task/{task_id}/stderr"

    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        result = response.json()
        stderr_content = result.get("stderr", "")
        print(stderr_content)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            print(f"Task {task_id} not found.")
        else:
            logger.error(f"HTTP error: {e.response.status_code}")
        raise
    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        raise


def create_vps(
    public_key: str,
    cores: int,
    memory_bytes: int | None,
    target: str | None,
    container_name: str | None,
    privileged: bool | None,
    additional_mounts: list[str] | None,
    gpu_ids: list[int],
) -> list[str]:
    """Create a VPS task and return task IDs."""
    url = f"{_get_host_url()}/vps/create"

    payload = {
        "public_key": public_key,
        "cores": cores,
        "memory_bytes": memory_bytes,
        "target": target,
        "container_name": container_name,
        "privileged": privileged,
        "additional_mounts": additional_mounts,
        "gpu_ids": gpu_ids,
    }

    try:
        response = httpx.post(url, json=payload, timeout=30.0)
        response.raise_for_status()
        result = response.json()
        print(json.dumps(result, indent=2))
        return result.get("task_ids", [])

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error: {e.response.status_code}")
        try:
            error_detail = e.response.json()
            logger.error(f"Error detail: {error_detail}")
        except Exception:
            pass
        raise
    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        raise


def get_active_vps_status():
    """Get status of all active VPS tasks."""
    url = f"{_get_host_url()}/vps/status"

    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        result = response.json()
        print(json.dumps(result, indent=2))

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error: {e.response.status_code}")
        raise
    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        raise
