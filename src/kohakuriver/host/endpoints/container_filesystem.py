"""
Filesystem endpoints for Host Docker containers (env setup containers).

These endpoints execute commands inside Docker containers running on the Host
machine to provide filesystem operations. Unlike the task filesystem endpoints
which proxy to runners, these operate directly on the Host.
"""

import asyncio
import json
import logging
import os
import base64

import docker
from docker.errors import NotFound as DockerNotFound, APIError as DockerAPIError
from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel

from kohakuriver.docker.naming import ENV_PREFIX

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Request Models
# =============================================================================


class WriteFileRequest(BaseModel):
    """Request for file write."""

    path: str
    content: str
    encoding: str = "utf-8"
    create_parents: bool = True


class MkdirRequest(BaseModel):
    """Request for creating directory."""

    path: str
    parents: bool = True


class RenameRequest(BaseModel):
    """Request for rename/move operation."""

    source: str
    destination: str
    overwrite: bool = False


# =============================================================================
# Helper Functions
# =============================================================================


def _resolve_container_name(client: docker.DockerClient, env_name: str) -> str | None:
    """Resolve environment name to actual container name.

    Checks for prefixed name first, then falls back to unprefixed.
    """
    # Try prefixed name first
    prefixed_name = f"{ENV_PREFIX}-{env_name}"
    try:
        client.containers.get(prefixed_name)
        return prefixed_name
    except DockerNotFound:
        pass

    # Fallback: try the name as-is
    try:
        client.containers.get(env_name)
        return env_name
    except DockerNotFound:
        pass

    return None


def _get_container(client: docker.DockerClient, container_name: str):
    """Get a running container by name."""
    actual_name = _resolve_container_name(client, container_name)
    if not actual_name:
        raise HTTPException(
            status_code=404,
            detail=f"Container '{container_name}' not found.",
        )

    container = client.containers.get(actual_name)
    if container.status != "running":
        raise HTTPException(
            status_code=400,
            detail=f"Container '{container_name}' is not running (status: {container.status}).",
        )

    return container


def _exec_in_container(
    container, cmd: str | list, check: bool = True
) -> tuple[int, str]:
    """Execute a command in a container and return (exit_code, output)."""
    if isinstance(cmd, str):
        # Use shell for string commands
        result = container.exec_run(
            cmd=["sh", "-c", cmd],
            demux=False,
        )
    else:
        result = container.exec_run(cmd=cmd, demux=False)

    exit_code = result.exit_code
    output = result.output.decode("utf-8", errors="replace") if result.output else ""

    if check and exit_code != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Command failed with exit code {exit_code}: {output.strip()}",
        )

    return exit_code, output


# =============================================================================
# Filesystem Operations (blocking, run in executor)
# =============================================================================


def _do_list_directory(container_name: str, path: str, show_hidden: bool) -> list[dict]:
    """List directory contents in container."""
    client = docker.from_env()
    container = _get_container(client, container_name)

    # Use a Python one-liner to get structured output
    # This handles filenames with special characters properly
    py_script = f"""
import os, json, stat
path = {repr(path)}
try:
    entries = os.listdir(path)
except PermissionError:
    entries = []
result = []
for name in entries:
    if not {show_hidden} and name.startswith('.'):
        continue
    full_path = os.path.join(path, name)
    try:
        st = os.stat(full_path)
        entry = {{
            "name": name,
            "path": full_path,
            "type": "directory" if stat.S_ISDIR(st.st_mode) else "file",
            "size": st.st_size if not stat.S_ISDIR(st.st_mode) else -1,
            "mtime": st.st_mtime,
        }}
        result.append(entry)
    except (OSError, PermissionError):
        pass
print(json.dumps(result))
"""

    exit_code, output = _exec_in_container(
        container, ["python3", "-c", py_script], check=False
    )

    if exit_code != 0:
        # Fallback: try with python if python3 is not available
        exit_code, output = _exec_in_container(
            container, ["python", "-c", py_script], check=False
        )

    if exit_code != 0:
        # Last resort fallback: use ls
        ls_cmd = f"ls -la {repr(path)}" if show_hidden else f"ls -l {repr(path)}"
        exit_code, output = _exec_in_container(container, ls_cmd, check=False)

        if exit_code != 0:
            return []

        # Parse ls output (simplified)
        entries = []
        for line in output.strip().split("\n")[1:]:  # Skip "total" line
            parts = line.split()
            if len(parts) >= 9:
                name = " ".join(parts[8:])
                is_dir = line.startswith("d")
                size = int(parts[4]) if not is_dir else -1
                entries.append(
                    {
                        "name": name,
                        "path": os.path.join(path, name),
                        "type": "directory" if is_dir else "file",
                        "size": size,
                        "mtime": 0,
                    }
                )
        return entries

    try:
        return json.loads(output.strip())
    except json.JSONDecodeError:
        return []


def _do_read_file(container_name: str, path: str, encoding: str, limit: int) -> dict:
    """Read file contents from container."""
    client = docker.from_env()
    container = _get_container(client, container_name)

    # Check file size first
    exit_code, output = _exec_in_container(
        container, f"stat -c %s {repr(path)}", check=False
    )

    if exit_code != 0:
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    try:
        file_size = int(output.strip())
    except ValueError:
        file_size = 0

    # Read file with limit
    if encoding == "base64":
        # Binary file - read and base64 encode
        exit_code, output = _exec_in_container(
            container,
            f"head -c {limit} {repr(path)} | base64",
            check=True,
        )
        return {
            "path": path,
            "content": output.strip(),
            "encoding": "base64",
            "size": file_size,
            "truncated": file_size > limit,
        }
    else:
        # Text file
        exit_code, output = _exec_in_container(
            container,
            f"head -c {limit} {repr(path)}",
            check=True,
        )
        return {
            "path": path,
            "content": output,
            "encoding": encoding,
            "size": file_size,
            "truncated": file_size > limit,
        }


def _do_write_file(
    container_name: str, path: str, content: str, encoding: str, create_parents: bool
) -> dict:
    """Write file contents to container."""
    client = docker.from_env()
    container = _get_container(client, container_name)

    if create_parents:
        parent_dir = os.path.dirname(path)
        if parent_dir:
            _exec_in_container(container, f"mkdir -p {repr(parent_dir)}", check=False)

    if encoding == "base64":
        # Decode base64 and write binary
        content_bytes = base64.b64decode(content)
        # Use a temp file approach
        encoded = base64.b64encode(content_bytes).decode("ascii")
        _exec_in_container(
            container,
            f"echo {repr(encoded)} | base64 -d > {repr(path)}",
            check=True,
        )
    else:
        # Text file - use printf for reliable writing
        # Escape content for shell
        escaped = content.replace("\\", "\\\\").replace("'", "'\"'\"'")
        _exec_in_container(
            container,
            f"printf '%s' '{escaped}' > {repr(path)}",
            check=True,
        )

    return {"path": path, "success": True}


def _do_mkdir(container_name: str, path: str, parents: bool) -> dict:
    """Create directory in container."""
    client = docker.from_env()
    container = _get_container(client, container_name)

    cmd = f"mkdir -p {repr(path)}" if parents else f"mkdir {repr(path)}"
    _exec_in_container(container, cmd, check=True)

    return {"path": path, "success": True}


def _do_rename(
    container_name: str, source: str, destination: str, overwrite: bool
) -> dict:
    """Rename/move file or directory in container."""
    client = docker.from_env()
    container = _get_container(client, container_name)

    # Check if source exists
    exit_code, _ = _exec_in_container(container, f"test -e {repr(source)}", check=False)
    if exit_code != 0:
        raise HTTPException(status_code=404, detail=f"Source not found: {source}")

    # Check if destination exists
    if not overwrite:
        exit_code, _ = _exec_in_container(
            container, f"test -e {repr(destination)}", check=False
        )
        if exit_code == 0:
            raise HTTPException(
                status_code=409, detail=f"Destination already exists: {destination}"
            )

    _exec_in_container(container, f"mv {repr(source)} {repr(destination)}", check=True)

    return {"source": source, "destination": destination, "success": True}


def _do_delete(container_name: str, path: str, recursive: bool) -> dict:
    """Delete file or directory in container."""
    client = docker.from_env()
    container = _get_container(client, container_name)

    # Check if path exists
    exit_code, _ = _exec_in_container(container, f"test -e {repr(path)}", check=False)
    if exit_code != 0:
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")

    cmd = f"rm -rf {repr(path)}" if recursive else f"rm {repr(path)}"
    _exec_in_container(container, cmd, check=True)

    return {"path": path, "success": True}


def _do_stat(container_name: str, path: str) -> dict:
    """Get file/directory metadata in container."""
    client = docker.from_env()
    container = _get_container(client, container_name)

    # Use Python for reliable stat
    py_script = f"""
import os, json, stat
path = {repr(path)}
try:
    st = os.stat(path)
    print(json.dumps({{
        "path": path,
        "name": os.path.basename(path),
        "type": "directory" if stat.S_ISDIR(st.st_mode) else "file",
        "size": st.st_size,
        "mtime": st.st_mtime,
        "mode": oct(st.st_mode),
        "uid": st.st_uid,
        "gid": st.st_gid,
    }}))
except FileNotFoundError:
    print(json.dumps({{"error": "not_found"}}))
except PermissionError:
    print(json.dumps({{"error": "permission_denied"}}))
"""

    exit_code, output = _exec_in_container(
        container, ["python3", "-c", py_script], check=False
    )

    if exit_code != 0:
        exit_code, output = _exec_in_container(
            container, ["python", "-c", py_script], check=False
        )

    if exit_code != 0:
        raise HTTPException(status_code=500, detail="Failed to stat file")

    try:
        result = json.loads(output.strip())
        if "error" in result:
            if result["error"] == "not_found":
                raise HTTPException(status_code=404, detail=f"Path not found: {path}")
            else:
                raise HTTPException(
                    status_code=403, detail=f"Permission denied: {path}"
                )
        return result
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Failed to parse stat output")


# =============================================================================
# REST Endpoints
# =============================================================================


@router.get("/fs/container/{container_name}/list")
async def list_directory(
    container_name: str = Path(..., description="Container name"),
    path: str = Query("/", description="Directory path to list"),
    show_hidden: bool = Query(False, description="Include hidden files"),
):
    """List contents of a directory inside the container."""
    try:
        result = await asyncio.to_thread(
            _do_list_directory, container_name, path, show_hidden
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing directory in container: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fs/container/{container_name}/read")
async def read_file(
    container_name: str = Path(..., description="Container name"),
    path: str = Query(..., description="File path to read"),
    encoding: str = Query("utf-8", description="Output encoding"),
    limit: int = Query(10485760, description="Max bytes to read"),
):
    """Read contents of a file inside the container."""
    try:
        result = await asyncio.to_thread(
            _do_read_file, container_name, path, encoding, limit
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading file in container: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fs/container/{container_name}/write")
async def write_file(
    container_name: str = Path(..., description="Container name"),
    request: WriteFileRequest = ...,
):
    """Write contents to a file inside the container."""
    try:
        result = await asyncio.to_thread(
            _do_write_file,
            container_name,
            request.path,
            request.content,
            request.encoding,
            request.create_parents,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error writing file in container: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fs/container/{container_name}/mkdir")
async def create_directory(
    container_name: str = Path(..., description="Container name"),
    request: MkdirRequest = ...,
):
    """Create a directory inside the container."""
    try:
        result = await asyncio.to_thread(
            _do_mkdir, container_name, request.path, request.parents
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating directory in container: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fs/container/{container_name}/rename")
async def rename_item(
    container_name: str = Path(..., description="Container name"),
    request: RenameRequest = ...,
):
    """Rename or move a file/directory inside the container."""
    try:
        result = await asyncio.to_thread(
            _do_rename,
            container_name,
            request.source,
            request.destination,
            request.overwrite,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error renaming in container: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/fs/container/{container_name}/delete")
async def delete_item(
    container_name: str = Path(..., description="Container name"),
    path: str = Query(..., description="Path to delete"),
    recursive: bool = Query(False, description="Delete directories recursively"),
):
    """Delete a file or directory inside the container."""
    try:
        result = await asyncio.to_thread(_do_delete, container_name, path, recursive)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting in container: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fs/container/{container_name}/stat")
async def stat_file(
    container_name: str = Path(..., description="Container name"),
    path: str = Query(..., description="Path to stat"),
):
    """Get file/directory metadata inside the container."""
    try:
        result = await asyncio.to_thread(_do_stat, container_name, path)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting stat in container: {e}")
        raise HTTPException(status_code=500, detail=str(e))
