import os
import sys
import subprocess
import shlex
import re
import shutil
import logging
from hakuriver.utils.logger import logger


class BindingError(Exception):
    """Custom exception for binding-related errors."""

    pass


def _run_command(cmd, capture_output=True, text=True, check=True, **kwargs):
    """Helper to run subprocess commands."""
    logger.debug(f"Running command: {' '.join(shlex.quote(c) for c in cmd)}")
    try:
        result = subprocess.run(
            cmd, capture_output=capture_output, text=text, check=check, **kwargs
        )
        logger.debug(f"Command stdout:\n{result.stdout.strip()}")
        if result.stderr:
            logger.debug(f"Command stderr:\n{result.stderr.strip()}")
        return result
    except FileNotFoundError:
        logger.error(f"Command not found: {cmd[0]}")
        raise BindingError(f"Command not found: {cmd[0]}") from None
    except subprocess.CalledProcessError as e:
        logger.error(
            f"Command failed with exit code {e.returncode}: {' '.join(shlex.quote(c) for c in cmd)}"
        )
        if e.stdout:
            logger.error(f"Stdout:\n{e.stdout.strip()}")
        if e.stderr:
            logger.error(f"Stderr:\n{e.stderr.strip()}")
        raise BindingError(
            f"Command failed with exit code {e.returncode}. Stderr: {e.stderr.strip()}"
        ) from None
    except Exception as e:
        logger.exception(
            f"An unexpected error occurred while running command: {' '.join(shlex.quote(c) for c in cmd)}"
        )
        raise BindingError(f"Unexpected error running command: {e}") from e


def find_executable_path(command_name_or_path: str) -> str:
    """
    Finds the absolute path of an executable command.

    Args:
        command_name_or_path: The name of the command (e.g., "numactl") or
                              a potential absolute path (e.g., "/usr/bin/numactl").

    Returns:
        The absolute path to the executable.

    Raises:
        BindingError: If the executable cannot be found.
    """
    logger.debug(f"Finding executable path for: {command_name_or_path}")

    # 1. Check if the input is already an absolute path and exists/is executable
    if (
        os.path.isabs(command_name_or_path)
        and os.path.exists(command_name_or_path)
        and os.access(command_name_or_path, os.X_OK)
    ):
        logger.debug(f"Input is an existing absolute path: {command_name_or_path}")
        return command_name_or_path

    # 2. Use shutil.which to find the executable in the system's PATH
    # This is generally more robust than parsing 'whereis' output.
    path_in_path = shutil.which(command_name_or_path)
    if path_in_path and os.access(path_in_path, os.X_OK):
        logger.debug(f"Found executable in PATH: {path_in_path}")
        return path_in_path
    elif path_in_path:
        # Found in path but not executable? Unlikely for shutil.which result, but good check.
        logger.warning(
            f"Found executable '{command_name_or_path}' at '{path_in_path}' but it's not executable."
        )

    # 3. Fallback: Use 'whereis' (less preferred, primarily for finding source/manual pages)
    # We'll only look for the binary path.
    try:
        # Use check=False because whereis returns non-zero if not found
        whereis_result = _run_command(
            ["whereis", "-b", command_name_or_path],
            check=False,
            capture_output=True,
            text=True,
        )
        if whereis_result.returncode == 0 and whereis_result.stdout:
            # whereis output is typically "name: /path1 /path2 ..."
            parts = whereis_result.stdout.strip().split(":", 1)
            if len(parts) > 1:
                binary_paths = parts[1].strip().split()
                for path in binary_paths:
                    if os.path.exists(path) and os.access(path, os.X_OK):
                        logger.debug(f"Found executable using whereis: {path}")
                        return path
                # If found paths but none are executable
                logger.warning(
                    f"Found paths using whereis for '{command_name_or_path}' but none are executable: {binary_paths}"
                )

    except BindingError:
        # Ignore BindingError from _run_command if whereis itself isn't found, etc.
        logger.debug(
            f"whereis command failed or not found for '{command_name_or_path}'."
        )
        pass  # Continue to raise the final error

    logger.error(
        f"Executable command '{command_name_or_path}' not found or is not executable."
    )
    raise BindingError(
        f"Executable command '{command_name_or_path}' not found or is not executable."
    )


def find_linked_libraries(executable_path: str) -> set[str]:
    """
    Uses ldd to find dynamic libraries linked by an executable and returns
    a set of their unique directory paths.

    Args:
        executable_path: The absolute path to the executable.

    Returns:
        A set of unique absolute directory paths containing the linked libraries.

    Raises:
        BindingError: If ldd fails or the executable is statically linked.
    """
    logger.debug(f"Finding linked libraries for: {executable_path}")

    try:
        ldd_result = _run_command(
            ["ldd", executable_path], check=True, capture_output=True, text=True
        )
        output = ldd_result.stdout

    except BindingError as e:
        if (
            "not a dynamic executable" in str(e).lower()
            or "statically linked" in e.stderr.lower()
        ):
            logger.info(
                f"Executable '{executable_path}' is statically linked. No external dynamic libraries needed."
            )
            return set()
        elif "command not found" in str(e):
            raise BindingError(
                "ldd command not found. Cannot determine dynamic library dependencies."
            ) from e
        elif "no such file" in e.stderr.lower() or "not found" in e.stderr.lower():
            raise BindingError(
                f"ldd could not find executable '{executable_path}'."
            ) from e
        else:
            logger.error(f"ldd command failed for '{executable_path}'.")
            raise  # Re-raise other binding errors

    library_dirs = set()

    # Regex to capture paths for libraries using '=>'
    # Group 1: The absolute path to the linked library
    regex_linked = re.compile(r"^\s*.*?=>\s+(/[^ ]+)\s+\([^)]+\)$")

    # Regex to capture paths for libraries/linker that might not use '=>' format
    # (e.g., the dynamic linker itself, sometimes on its own line)
    # Group 1: The absolute path
    regex_direct = re.compile(r"^\s*(/[^ ]+)\s+\([^)]+\)$")

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue

        match_linked = regex_linked.match(line)
        if match_linked:
            lib_path = match_linked.group(1)
            lib_dir = os.path.dirname(lib_path)
            if lib_dir:  # Ensure it's not empty (root dir is '/')
                library_dirs.add(lib_dir)
                logger.debug(f"Found linked library dir: {lib_dir} (from line: {line})")
            continue

        match_direct = regex_direct.match(line)
        if match_direct:
            lib_path = match_direct.group(1)
            lib_dir = os.path.dirname(lib_path)
            if lib_dir:
                library_dirs.add(lib_dir)
                logger.debug(f"Found direct library dir: {lib_dir} (from line: {line})")
            continue
    logger.debug(f"Found unique library directories: {library_dirs}")
    return library_dirs


def format_docker_mounts(executable_path: str, library_dirs: set[str]) -> list[str]:
    """
    Formats the executable path and library directories into Docker bind mount strings.

    The executable is mounted to /opt/bin/ inside the container.
    Library directories are mounted to the same path as they are on the host, as read-only.

    Args:
        executable_path: The absolute path to the executable on the host.
        library_dirs: A set of absolute directory paths containing linked libraries.

    Returns:
        A list of strings in the format "host_path:container_path:ro".
    """
    mounts = []

    # Mount the executable itself to a standard, non-conflicting path in the container
    executable_basename = os.path.basename(executable_path)
    container_exec_path = f"/usr/bin/{executable_basename}"
    mounts.append(f"{executable_path}:{container_exec_path}:ro")
    logger.debug(f"Added executable mount: {mounts[-1]}")

    # Mount each library directory to the same path inside the container
    for lib_dir in sorted(list(library_dirs)):  # Sort for deterministic output
        # Ensure we don't mount the root directory "/" unless explicitly intended (ldd shouldn't return it)
        if lib_dir and lib_dir != "/":
            mounts.append(f"{lib_dir}:{lib_dir}:ro")
            logger.debug(f"Added library dir mount: {mounts[-1]}")
        elif lib_dir == "/":
            logger.warning(
                f"Skipping potential root directory mount '/' for libraries."
            )

    return mounts


def get_executable_and_library_mounts(
    command_name_or_path: str,
) -> tuple[str, list[str]]:
    """
    Orchestrates finding an executable, its library dependencies, and formatting
    them into Docker bind mount strings.

    Args:
       command_name_or_path: The name of the command (e.g., "numactl") or
                             a potential absolute path (e.g., "/usr/bin/numactl").

    Returns:
        A tuple containing:
        - The absolute path of the executable on the host.
        - A list of Docker bind mount strings for the executable and its library directories.

    Raises:
        BindingError: If any step fails (executable not found, ldd fails, etc.).
    """
    try:
        executable_path = find_executable_path(command_name_or_path)
        library_dirs = find_linked_libraries(executable_path)
        mounts = format_docker_mounts(executable_path, library_dirs)
        return executable_path, mounts
    except BindingError:
        raise  # Re-raise the specific BindingError


# --- Basic Test Execution ---
if __name__ == "__main__":
    import argparse

    logger.setLevel(logging.DEBUG)  # Set logger to debug level for testing

    parser = argparse.ArgumentParser(
        description="Utility to find executable dependencies and format Docker mounts."
    )
    parser.add_argument(
        "command",
        help="The command name (e.g., 'numactl', 'ls') or an absolute path to an executable.",
    )
    args = parser.parse_args()

    print(f"\n--- Testing binding for command: {args.command} ---")

    try:
        exec_path, mounts = get_executable_and_library_mounts(args.command)

        print(f"\nExecutable Found At: {exec_path}")
        print("\nGenerated Docker Mounts (host_path:container_path:mode):")
        if mounts:
            for mount in mounts:
                print(f"  {mount}")
        else:
            print("  No dynamic libraries found or needed (likely statically linked).")

        # Example of how to potentially use this in a docker run command:
        print("\nExample Docker Command Snippet:")
        docker_prefix = ["docker", "run", "--rm"]
        if mounts:
            mount_args = [item for mount in mounts for item in ["-v", mount]]
        else:
            mount_args = []

        # Assuming the executable is mounted at /opt/bin/command_name inside the container
        container_exec_path = f"/usr/bin/{os.path.basename(exec_path)}"
        container_command = [container_exec_path]  # You might add args here

        print(
            shlex.join(
                docker_prefix + mount_args + ["your_image_name"] + container_command
            )
        )

    except BindingError as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logger.exception("An unexpected error occurred during testing:")
        sys.exit(1)
