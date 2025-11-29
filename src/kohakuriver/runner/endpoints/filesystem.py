"""
Filesystem REST API endpoints for task/VPS containers on the Runner.

Provides file browsing and editing capabilities inside Docker containers
via Docker exec commands.
"""

import asyncio
import base64
import json
import logging
import os
import shlex
from datetime import datetime
from typing import Literal

import docker
from docker.errors import NotFound as DockerNotFound, APIError as DockerAPIError
from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field

from kohakuriver.storage.vault import TaskStateStore

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level dependencies (set by app on startup)
_task_store: TaskStateStore | None = None


def set_dependencies(task_store: TaskStateStore):
    """Set module dependencies from app startup."""
    global _task_store
    _task_store = task_store


# =============================================================================
# Constants and Configuration
# =============================================================================

# Security: Forbidden paths that cannot be accessed
FORBIDDEN_PATHS = {"/proc", "/sys", "/dev"}

# Limits
MAX_FILE_READ_SIZE = 10 * 1024 * 1024  # 10MB
MAX_DIRECTORY_ENTRIES = 1000
MAX_FILE_WRITE_SIZE = 50 * 1024 * 1024  # 50MB


# =============================================================================
# Request/Response Models
# =============================================================================


class FileEntry(BaseModel):
    """A file or directory entry."""

    name: str
    path: str
    type: Literal["file", "directory", "symlink", "other"]
    size: int = -1  # -1 for directories
    mtime: str  # ISO format timestamp
    permissions: str  # e.g., "rwxr-xr-x"


class ListDirectoryResponse(BaseModel):
    """Response for directory listing."""

    path: str
    entries: list[FileEntry]
    parent: str | None = None


class ReadFileResponse(BaseModel):
    """Response for file read."""

    path: str
    content: str
    encoding: Literal["utf-8", "base64"]
    size: int
    truncated: bool


class WriteFileRequest(BaseModel):
    """Request for file write."""

    path: str
    content: str
    encoding: Literal["utf-8", "base64"] = "utf-8"
    create_parents: bool = True


class WriteFileResponse(BaseModel):
    """Response for file write."""

    path: str
    size: int
    success: bool = True


class MkdirRequest(BaseModel):
    """Request for creating directory."""

    path: str
    parents: bool = True


class RenameRequest(BaseModel):
    """Request for rename/move operation."""

    source: str
    destination: str
    overwrite: bool = False


class FileStatResponse(BaseModel):
    """Response for file stat."""

    path: str
    type: Literal["file", "directory", "symlink", "other"]
    size: int
    mtime: str
    permissions: str
    owner: str | None = None
    is_readable: bool = True
    is_writable: bool = True
    is_binary: bool = False


# =============================================================================
# Helper Functions
# =============================================================================


def _resolve_container_name(task_id: int) -> str | None:
    """Resolve task_id to container name using task_store."""
    if not _task_store:
        return None

    task_data = _task_store.get_task(task_id)
    if not task_data:
        return None

    return task_data.get("container_name")


def _validate_path(path: str) -> tuple[bool, str | None]:
    """
    Validate path for security issues.

    Returns (is_valid, error_message).
    """
    if not path:
        return False, "Path cannot be empty"

    if not path.startswith("/"):
        return False, "Path must be absolute (start with /)"

    # Normalize to resolve .. and .
    normalized = os.path.normpath(path)

    # Check for forbidden paths
    for forbidden in FORBIDDEN_PATHS:
        if normalized == forbidden or normalized.startswith(forbidden + "/"):
            return False, f"Access to {forbidden} is forbidden"

    return True, None


def _get_validated_path(path: str) -> str:
    """Validate and normalize path, raising HTTPException on error."""
    is_valid, error = _validate_path(path)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)
    return os.path.normpath(path)


async def _get_container(task_id: int) -> tuple[docker.DockerClient, any]:
    """
    Get Docker client and container for a task.

    Returns (client, container) tuple.
    Raises HTTPException on error.
    """
    # Resolve container name
    container_name = _resolve_container_name(task_id)
    if not container_name:
        raise HTTPException(
            status_code=404, detail=f"Task {task_id} not found on this runner."
        )

    # Initialize Docker client
    try:
        client = docker.from_env(timeout=30)
        client.ping()
    except Exception as e:
        logger.error(f"Failed to initialize Docker client: {e}")
        raise HTTPException(status_code=500, detail=f"Docker connection error: {e}")

    # Get container
    try:
        container = client.containers.get(container_name)
        if container.status != "running":
            raise HTTPException(
                status_code=400,
                detail=f"Container is not running (status: {container.status}).",
            )
        return client, container
    except DockerNotFound:
        raise HTTPException(status_code=404, detail="Container not found.")
    except DockerAPIError as e:
        raise HTTPException(status_code=500, detail=f"Docker API error: {e}")


async def _exec_in_container(
    container, cmd: list[str], timeout: int = 30
) -> tuple[int, str, str]:
    """
    Execute a command in container.

    Returns (exit_code, stdout, stderr).
    """

    def _run():
        exec_instance = container.client.api.exec_create(
            container.id,
            cmd=cmd,
            stdout=True,
            stderr=True,
            stdin=False,
            tty=False,
        )
        output = container.client.api.exec_start(
            exec_instance["Id"],
            stream=False,
            demux=True,
        )
        stdout = output[0].decode("utf-8", errors="replace") if output[0] else ""
        stderr = output[1].decode("utf-8", errors="replace") if output[1] else ""
        inspect = container.client.api.exec_inspect(exec_instance["Id"])
        return inspect.get("ExitCode", -1), stdout, stderr

    return await asyncio.to_thread(_run)


def _parse_ls_output(output: str, base_path: str) -> list[FileEntry]:
    """
    Parse output from ls -la command.

    Supports two formats:
    1. GNU ls with --time-style=+%s:
       drwxr-xr-x 2 root root 4096 1234567890 .
    2. BusyBox ls (no --time-style):
       drwxr-xr-x 2 root root 4096 Nov 29 01:30 .
    """
    entries = []
    lines = output.strip().split("\n")

    for line in lines:
        # Skip total line and empty lines
        if not line or line.startswith("total "):
            continue

        parts = line.split()
        if len(parts) < 6:
            continue

        permissions = parts[0]
        # parts[1] is link count
        # parts[2] is owner
        # parts[3] is group
        size_str = parts[4]

        # Detect format: GNU (epoch) vs BusyBox (month day time)
        # BusyBox: "Nov 29 01:30 filename" or "Nov 29 2024 filename"
        # GNU: "1234567890 filename"
        timestamp_str = parts[5]

        # Check if timestamp is numeric (GNU) or month name (BusyBox)
        if timestamp_str.isdigit() and len(timestamp_str) > 6:
            # GNU format: epoch timestamp
            name = " ".join(parts[6:])
            try:
                timestamp = int(timestamp_str)
                mtime = datetime.fromtimestamp(timestamp).isoformat()
            except (ValueError, OSError):
                mtime = datetime.now().isoformat()
        else:
            # BusyBox format: "Mon DD HH:MM" or "Mon DD YYYY"
            # parts[5] = month, parts[6] = day, parts[7] = time/year
            if len(parts) < 8:
                continue
            name = " ".join(parts[8:])
            # Use current time as fallback since parsing BusyBox dates is complex
            mtime = datetime.now().isoformat()

        # Skip . and ..
        if name in (".", "..") or not name:
            continue

        # Determine type from permissions
        type_char = permissions[0] if permissions else "-"
        if type_char == "d":
            entry_type = "directory"
        elif type_char == "l":
            entry_type = "symlink"
            # Remove symlink target from name (e.g., "link -> target")
            if " -> " in name:
                name = name.split(" -> ")[0]
        elif type_char == "-":
            entry_type = "file"
        else:
            entry_type = "other"

        # Parse size
        try:
            size = int(size_str) if entry_type == "file" else -1
        except ValueError:
            size = -1

        # Build full path
        if base_path == "/":
            full_path = f"/{name}"
        else:
            full_path = f"{base_path}/{name}"

        entries.append(
            FileEntry(
                name=name,
                path=full_path,
                type=entry_type,
                size=size,
                mtime=mtime,
                permissions=permissions[1:] if len(permissions) > 1 else "",
            )
        )

    return entries


# =============================================================================
# REST Endpoints
# =============================================================================


@router.get("/fs/{task_id}/list", response_model=ListDirectoryResponse)
async def list_directory(
    task_id: int = Path(..., description="Task ID"),
    path: str = Query("/", description="Directory path to list"),
    show_hidden: bool = Query(False, description="Include hidden files"),
):
    """List contents of a directory inside the container."""
    path = _get_validated_path(path)
    client, container = await _get_container(task_id)

    try:
        # Build ls command - try GNU ls first, fallback to BusyBox compatible
        flags = "-la" if show_hidden else "-lA"

        # Try GNU ls with --time-style first
        cmd = ["ls", flags, "--time-style=+%s", path]
        exit_code, stdout, stderr = await _exec_in_container(container, cmd)

        # If --time-style not supported (BusyBox), fallback to basic ls
        if exit_code != 0 and "unrecognized option" in stderr:
            cmd = ["ls", flags, path]
            exit_code, stdout, stderr = await _exec_in_container(container, cmd)

        if exit_code != 0:
            if "No such file or directory" in stderr:
                raise HTTPException(status_code=404, detail=f"Path not found: {path}")
            elif "Permission denied" in stderr:
                raise HTTPException(
                    status_code=403, detail=f"Permission denied: {path}"
                )
            elif "Not a directory" in stderr:
                raise HTTPException(status_code=400, detail=f"Not a directory: {path}")
            else:
                raise HTTPException(status_code=500, detail=f"ls failed: {stderr}")

        entries = _parse_ls_output(stdout, path)

        # Limit entries
        if len(entries) > MAX_DIRECTORY_ENTRIES:
            entries = entries[:MAX_DIRECTORY_ENTRIES]
            logger.warning(
                f"Directory listing truncated to {MAX_DIRECTORY_ENTRIES} entries"
            )

        # Calculate parent path
        parent = os.path.dirname(path) if path != "/" else None

        return ListDirectoryResponse(path=path, entries=entries, parent=parent)

    finally:
        client.close()


@router.get("/fs/{task_id}/read", response_model=ReadFileResponse)
async def read_file(
    task_id: int = Path(..., description="Task ID"),
    path: str = Query(..., description="File path to read"),
    encoding: Literal["utf-8", "base64"] = Query(
        "utf-8", description="Output encoding"
    ),
    limit: int = Query(MAX_FILE_READ_SIZE, description="Max bytes to read"),
):
    """Read contents of a file inside the container."""
    path = _get_validated_path(path)
    client, container = await _get_container(task_id)

    # Clamp limit
    limit = min(limit, MAX_FILE_READ_SIZE)

    try:
        # First check if it's a file and get size
        # Try GNU stat first, then BusyBox stat
        stat_cmd = ["stat", "--format=%F|%s", path]
        exit_code, stdout, stderr = await _exec_in_container(container, stat_cmd)

        # Fallback to BusyBox stat format
        if exit_code != 0 and "unrecognized option" in stderr:
            stat_cmd = ["stat", "-c", "%F|%s", path]
            exit_code, stdout, stderr = await _exec_in_container(container, stat_cmd)

        if exit_code != 0:
            if "No such file or directory" in stderr:
                raise HTTPException(status_code=404, detail=f"File not found: {path}")
            elif "Permission denied" in stderr:
                raise HTTPException(
                    status_code=403, detail=f"Permission denied: {path}"
                )
            else:
                raise HTTPException(status_code=500, detail=f"stat failed: {stderr}")

        parts = stdout.strip().split("|")
        file_type = parts[0] if parts else ""
        file_size = int(parts[1]) if len(parts) > 1 else 0

        if "directory" in file_type.lower():
            raise HTTPException(
                status_code=400, detail=f"Cannot read directory: {path}"
            )

        # Read file with size limit
        cmd = ["head", "-c", str(limit), path]
        exit_code, stdout, stderr = await _exec_in_container(container, cmd)

        if exit_code != 0:
            raise HTTPException(status_code=500, detail=f"read failed: {stderr}")

        truncated = file_size > limit
        content = stdout
        actual_encoding = encoding

        # If requested encoding is utf-8, try to decode, fallback to base64 if binary
        if encoding == "utf-8":
            try:
                # Check if content is valid UTF-8
                content.encode("utf-8")
            except (UnicodeDecodeError, UnicodeEncodeError):
                # Binary file - use base64
                content = base64.b64encode(stdout.encode("latin-1")).decode("ascii")
                actual_encoding = "base64"
        else:
            # base64 requested
            content = base64.b64encode(stdout.encode("latin-1")).decode("ascii")
            actual_encoding = "base64"

        return ReadFileResponse(
            path=path,
            content=content,
            encoding=actual_encoding,
            size=len(stdout),
            truncated=truncated,
        )

    finally:
        client.close()


@router.post("/fs/{task_id}/write", response_model=WriteFileResponse)
async def write_file(
    task_id: int = Path(..., description="Task ID"),
    request: WriteFileRequest = ...,
):
    """Write contents to a file inside the container."""
    path = _get_validated_path(request.path)
    client, container = await _get_container(task_id)

    try:
        # Decode content if base64
        if request.encoding == "base64":
            try:
                content_bytes = base64.b64decode(request.content)
            except Exception as e:
                raise HTTPException(
                    status_code=400, detail=f"Invalid base64 content: {e}"
                )
        else:
            content_bytes = request.content.encode("utf-8")

        # Check size limit
        if len(content_bytes) > MAX_FILE_WRITE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_FILE_WRITE_SIZE} bytes.",
            )

        # Create parent directories if requested
        if request.create_parents:
            parent_dir = os.path.dirname(path)
            if parent_dir and parent_dir != "/":
                mkdir_cmd = ["mkdir", "-p", parent_dir]
                exit_code, _, stderr = await _exec_in_container(container, mkdir_cmd)
                if exit_code != 0:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to create parent directories: {stderr}",
                    )

        # Write file using base64 for safe transfer
        b64_content = base64.b64encode(content_bytes).decode("ascii")
        escaped_path = shlex.quote(path)

        # Use sh -c with base64 decode and write
        write_cmd = [
            "sh",
            "-c",
            f'echo "{b64_content}" | base64 -d > {escaped_path}',
        ]
        exit_code, stdout, stderr = await _exec_in_container(container, write_cmd)

        if exit_code != 0:
            if "Permission denied" in stderr:
                raise HTTPException(
                    status_code=403, detail=f"Permission denied: {path}"
                )
            raise HTTPException(status_code=500, detail=f"Write failed: {stderr}")

        return WriteFileResponse(path=path, size=len(content_bytes), success=True)

    finally:
        client.close()


@router.post("/fs/{task_id}/mkdir")
async def create_directory(
    task_id: int = Path(..., description="Task ID"),
    request: MkdirRequest = ...,
):
    """Create a directory inside the container."""
    path = _get_validated_path(request.path)
    client, container = await _get_container(task_id)

    try:
        flags = "-p" if request.parents else ""
        cmd = ["mkdir", flags, path] if flags else ["mkdir", path]

        exit_code, stdout, stderr = await _exec_in_container(container, cmd)

        if exit_code != 0:
            if "Permission denied" in stderr:
                raise HTTPException(
                    status_code=403, detail=f"Permission denied: {path}"
                )
            elif "File exists" in stderr:
                raise HTTPException(
                    status_code=409, detail=f"Directory already exists: {path}"
                )
            raise HTTPException(status_code=500, detail=f"mkdir failed: {stderr}")

        return {"message": f"Directory created: {path}", "path": path}

    finally:
        client.close()


@router.post("/fs/{task_id}/rename")
async def rename_item(
    task_id: int = Path(..., description="Task ID"),
    request: RenameRequest = ...,
):
    """Rename or move a file/directory inside the container."""
    source = _get_validated_path(request.source)
    destination = _get_validated_path(request.destination)
    client, container = await _get_container(task_id)

    try:
        # Check if destination exists (unless overwrite is true)
        if not request.overwrite:
            check_cmd = ["test", "-e", destination]
            exit_code, _, _ = await _exec_in_container(container, check_cmd)
            if exit_code == 0:
                raise HTTPException(
                    status_code=409,
                    detail=f"Destination already exists: {destination}",
                )

        cmd = ["mv", source, destination]
        exit_code, stdout, stderr = await _exec_in_container(container, cmd)

        if exit_code != 0:
            if "No such file or directory" in stderr:
                raise HTTPException(
                    status_code=404, detail=f"Source not found: {source}"
                )
            elif "Permission denied" in stderr:
                raise HTTPException(status_code=403, detail="Permission denied")
            raise HTTPException(status_code=500, detail=f"rename failed: {stderr}")

        return {
            "message": f"Renamed {source} to {destination}",
            "source": source,
            "destination": destination,
        }

    finally:
        client.close()


@router.delete("/fs/{task_id}/delete")
async def delete_item(
    task_id: int = Path(..., description="Task ID"),
    path: str = Query(..., description="Path to delete"),
    recursive: bool = Query(False, description="Delete directories recursively"),
):
    """Delete a file or directory inside the container."""
    path = _get_validated_path(path)
    client, container = await _get_container(task_id)

    try:
        # Use rm with appropriate flags
        if recursive:
            cmd = ["rm", "-rf", path]
        else:
            cmd = ["rm", "-f", path]

        exit_code, stdout, stderr = await _exec_in_container(container, cmd)

        if exit_code != 0:
            if "No such file or directory" in stderr:
                raise HTTPException(status_code=404, detail=f"Path not found: {path}")
            elif "Permission denied" in stderr:
                raise HTTPException(
                    status_code=403, detail=f"Permission denied: {path}"
                )
            elif "Is a directory" in stderr:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot delete directory without recursive flag: {path}",
                )
            raise HTTPException(status_code=500, detail=f"delete failed: {stderr}")

        return {"message": f"Deleted: {path}", "path": path}

    finally:
        client.close()


@router.get("/fs/{task_id}/stat", response_model=FileStatResponse)
async def stat_file(
    task_id: int = Path(..., description="Task ID"),
    path: str = Query(..., description="Path to stat"),
):
    """Get file/directory metadata inside the container."""
    path = _get_validated_path(path)
    client, container = await _get_container(task_id)

    try:
        # stat with custom format: type|size|mtime|owner|group|permissions
        # Try GNU stat first, then BusyBox stat
        cmd = ["stat", "--format=%F|%s|%Y|%U|%G|%a", path]
        exit_code, stdout, stderr = await _exec_in_container(container, cmd)

        # Fallback to BusyBox stat format
        if exit_code != 0 and "unrecognized option" in stderr:
            cmd = ["stat", "-c", "%F|%s|%Y|%U|%G|%a", path]
            exit_code, stdout, stderr = await _exec_in_container(container, cmd)

        if exit_code != 0:
            if "No such file or directory" in stderr:
                raise HTTPException(status_code=404, detail=f"Path not found: {path}")
            elif "Permission denied" in stderr:
                raise HTTPException(
                    status_code=403, detail=f"Permission denied: {path}"
                )
            raise HTTPException(status_code=500, detail=f"stat failed: {stderr}")

        parts = stdout.strip().split("|")
        if len(parts) < 6:
            raise HTTPException(status_code=500, detail="Invalid stat output")

        file_type_str = parts[0].lower()
        size = int(parts[1]) if parts[1] else 0
        mtime_unix = int(parts[2]) if parts[2] else 0
        owner = parts[3]
        # group = parts[4]
        permissions_octal = parts[5]

        # Map file type
        if "directory" in file_type_str:
            file_type = "directory"
        elif "symbolic link" in file_type_str:
            file_type = "symlink"
        elif "regular" in file_type_str or "empty" in file_type_str:
            file_type = "file"
        else:
            file_type = "other"

        # Convert mtime
        try:
            mtime = datetime.fromtimestamp(mtime_unix).isoformat()
        except (ValueError, OSError):
            mtime = datetime.now().isoformat()

        # Convert octal permissions to rwx format
        try:
            perms_int = int(permissions_octal, 8)
            permissions = ""
            for shift in [6, 3, 0]:
                p = (perms_int >> shift) & 7
                permissions += "r" if p & 4 else "-"
                permissions += "w" if p & 2 else "-"
                permissions += "x" if p & 1 else "-"
        except ValueError:
            permissions = permissions_octal

        # Check if binary by looking at file extension or trying to read first bytes
        is_binary = False
        if file_type == "file":
            binary_extensions = {
                ".bin",
                ".exe",
                ".dll",
                ".so",
                ".dylib",
                ".o",
                ".a",
                ".zip",
                ".tar",
                ".gz",
                ".bz2",
                ".xz",
                ".7z",
                ".rar",
                ".jpg",
                ".jpeg",
                ".png",
                ".gif",
                ".bmp",
                ".ico",
                ".webp",
                ".mp3",
                ".wav",
                ".ogg",
                ".flac",
                ".mp4",
                ".mkv",
                ".avi",
                ".pdf",
                ".doc",
                ".docx",
                ".xls",
                ".xlsx",
                ".ppt",
                ".pptx",
                ".pyc",
                ".pyo",
                ".class",
                ".jar",
                ".war",
            }
            ext = os.path.splitext(path)[1].lower()
            is_binary = ext in binary_extensions

        return FileStatResponse(
            path=path,
            type=file_type,
            size=size,
            mtime=mtime,
            permissions=permissions,
            owner=owner,
            is_readable=True,  # If we got here, it's readable
            is_writable=True,  # Assume writable (would need more checks)
            is_binary=is_binary,
        )

    finally:
        client.close()
