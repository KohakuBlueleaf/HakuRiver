import subprocess
import os
import time
import json
import re
import datetime
import shlex

from .logger import logger


def _run_command(cmd, capture_output=True, text=True, check=False, **kwargs):
    """Helper to run subprocess commands and log output."""
    logger.debug(f"Running command: {' '.join(shlex.quote(c) for c in cmd)}")
    try:
        result = subprocess.run(
            cmd, capture_output=capture_output, text=text, check=check, **kwargs
        )
        if "sudo" != cmd[0] and result.returncode != 0:
            return _run_command(
                ["sudo"] + cmd, capture_output, text, check, **kwargs
            )
        # Avoid logging potentially huge output from docker save/load by default
        if result.stdout and cmd[0:2] not in (["docker", "save"], ["docker", "load"]):
            logger.debug(f"Command stdout:\n{result.stdout}")
        if result.stderr and cmd[0:2] not in (["docker", "save"], ["docker", "load"]):
            logger.debug(f"Command stderr:\n{result.stderr}")
        # Special logging for load/save errors
        if result.returncode != 0 and cmd[0:2] in (
            ["docker", "save"],
            ["docker", "load"],
        ):
            logger.error(f"Command stderr:\n{result.stderr}")

        return result
    except FileNotFoundError:
        logger.error(f"Command not found: {cmd[0]}")
        raise
    except subprocess.CalledProcessError as e:
        if "sudo" != cmd[0]:  # Avoid logging sudo command errors
            return _run_command(["sudo"] + cmd, capture_output, text, check, **kwargs)
        logger.error(
            f"Command failed with exit code {e.returncode}: {' '.join(shlex.quote(c) for c in cmd)}"
        )
        # Log output even for save/load on error
        logger.error(f"Stderr:\n{e.stderr}")
        if e.stdout:  # Check if stdout exists
            logger.error(f"Stdout:\n{e.stdout}")
        raise
    except Exception as e:
        logger.exception(
            f"An unexpected error occurred while running command: {' '.join(shlex.quote(c) for c in cmd)}"
        )
        raise


def create_container(image_name: str, container_name: str) -> bool:
    """
    Creates a persistent, long-running container from an image.
    Intended for users to manually interact with and modify later.

    Args:
        image_name: The name of the public Docker image (e.g., 'ubuntu:latest').
        container_name: The desired name for the persistent container.

    Returns:
        True if creation was successful, False otherwise.
    """
    image_name = image_name.lower()
    logger.info(
        f"Attempting to create persistent container '{container_name}' from image '{image_name}'..."
    )

    # Check if container already exists
    try:
        inspect_result = _run_command(
            ["docker", "inspect", container_name],
            capture_output=True,
            text=True,
            check=False,
        )
        if inspect_result.returncode == 0:
            logger.warning(
                f"Container '{container_name}' already exists. Skipping creation."
            )
            # Consider returning True as it exists, or False because we didn't create it now?
            # Let's return True, indicating the desired state exists.
            return True
    except FileNotFoundError:  # docker command not found
        return False
    except Exception as e:
        logger.error(f"Error checking for existing container '{container_name}': {e}")
        return False  # Uncertain state

    try:
        # 1. Pull the image if it doesn't exist locally (docker run will do this, but explicit pull is clearer)
        logger.info(f"Pulling Docker image: {image_name}")
        _run_command(["docker", "pull", image_name], check=True)
        logger.info(f"Successfully pulled or verified image: {image_name}")

        # 2. Create and run the container in detached mode with a long-running command
        # Using 'sleep infinity' is a common practice.
        logger.info(
            f"Creating and starting container '{container_name}' in detached mode."
        )
        _run_command(
            [
                "docker",
                "run",
                "-d",  # Detached mode
                "--name",
                container_name,
                # Optional: Add restart policy? --restart unless-stopped
                image_name,
                "sleep",
                "infinity",  # Command to keep the container running
            ],
            check=True,
        )
        logger.info(f"Successfully created and started container '{container_name}'.")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create persistent container '{container_name}': {e}")
        return False
    except Exception as e:
        logger.exception(
            f"An unexpected error occurred during persistent container creation for '{container_name}': {e}"
        )
        return False


def delete_container(container_name: str) -> bool:
    """
    Deletes a Docker container (forcefully).

    Args:
        container_name: The name of the container to delete.

    Returns:
        True if deletion was successful, False otherwise.
    """
    logger.info(f"Attempting to delete container '{container_name}'...")
    try:
        # Use -f (force) to stop and remove the container
        _run_command(["docker", "rm", "--force", container_name], check=True)
        logger.info(f"Container '{container_name}' deleted successfully.")
        return True
    except subprocess.CalledProcessError as e:
        # Specific error logging is handled by _run_command check=True
        logger.error(f"Failed to delete container '{container_name}': {e}")
        return False
    except FileNotFoundError:
        return False
    except Exception as e:
        logger.exception(
            f"An unexpected error occurred during deletion of '{container_name}'."
        )
        return False


def stop_container(container_name: str) -> bool:
    """
    Stops a running Docker container.

    Args:
        container_name: The name of the container to stop.

    Returns:
        True if stopping was successful, False otherwise.
    """
    logger.info(f"Attempting to stop container '{container_name}'...")
    try:
        # Use check=False because docker stop returns 1 if container is already stopped
        result = _run_command(["docker", "stop", container_name], check=False)
        if result.returncode == 0:
            logger.info(f"Container '{container_name}' stopped successfully.")
            return True
        elif "is already stopped" in result.stderr or "is not running" in result.stderr:
            logger.warning(f"Container '{container_name}' was already stopped.")
            return True  # Consider it successful if it's already in the desired state
        else:
            logger.error(
                f"Failed to stop container '{container_name}'. Stderr: {result.stderr.strip()}"
            )
            return False
    except FileNotFoundError:
        return False
    except Exception as e:
        logger.exception(
            f"An unexpected error occurred during stopping of '{container_name}': {e}."
        )
        return False


def start_container(container_name: str) -> bool:
    """
    Starts a stopped Docker container.

    Args:
        container_name: The name of the container to start.

    Returns:
        True if starting was successful, False otherwise.
    """
    logger.info(f"Attempting to start container '{container_name}'...")
    try:
        _run_command(["docker", "start", container_name], check=True)
        logger.info(f"Container '{container_name}' started successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to start container '{container_name}': {e}.")
        return False
    except FileNotFoundError:
        return False
    except Exception as e:
        logger.exception(
            f"An unexpected error occurred during starting of '{container_name}'."
        )
        return False


def create_container_tar(
    source_container_name: str, hakuriver_container_name: str, container_tar_dir: str
) -> str | None:
    """
    Creates a HakuRiver base container tarball from an *existing* Docker container.

    Assumes the user has already created and configured the 'source_container_name'.
    Commits the container, saves the resulting image to a tarball, and cleans up
    the temporary image tagged for HakuRiver.

    Args:
        source_container_name: The name of the existing Docker container to commit from.
        hakuriver_container_name: The desired HakuRiver container name (e.g., 'myenv').
        container_tar_dir: Absolute path to the directory where container tars should be stored.

    Returns:
        The absolute path to the created tarball, or None if failed.
    """
    hakuriver_image_tag = f"hakuriver/{hakuriver_container_name}:base".lower()
    timestamp = int(time.time())
    tarball_filename = f"{hakuriver_container_name}-{timestamp}.tar"
    tarball_path = os.path.join(container_tar_dir, tarball_filename)

    logger.info(
        f"Attempting to create HakuRiver base container tarball for '{hakuriver_container_name}' "
        f"by committing from existing container '{source_container_name}'"
    )

    try:
        # Check if the source container exists
        logger.info(f"Checking if source container '{source_container_name}' exists...")
        check_cmd = ["docker", "inspect", source_container_name]
        _run_command(check_cmd, check=True, capture_output=True)  # Just check exit code
        logger.info(f"Source container '{source_container_name}' found.")

        # 1. Commit the container to create a new image (tagging it for HakuRiver)
        # It's often better to stop the container before committing for filesystem consistency
        logger.info(f"Stopping container '{source_container_name}' before commit...")
        _run_command(
            ["docker", "stop", source_container_name], check=False
        )  # Don't fail if already stopped
        logger.info(
            f"Committing container {source_container_name} to image {hakuriver_image_tag}"
        )
        _run_command(
            ["docker", "commit", source_container_name, hakuriver_image_tag], check=True
        )
        logger.info(f"Successfully committed container to image: {hakuriver_image_tag}")

        # 2. Save the *newly committed image* to a tarball
        logger.info(f"Saving image {hakuriver_image_tag} to tarball {tarball_path}")
        os.makedirs(container_tar_dir, exist_ok=True)
        _run_command(
            ["docker", "save", "-o", tarball_path, hakuriver_image_tag], check=True
        )
        logger.info(f"Successfully saved image to tarball: {tarball_path}")

        for old_timestamp, old_path in list_shared_container_tars(
            container_tar_dir, hakuriver_container_name
        ):
            if old_timestamp < timestamp:
                logger.info(f"Removing older tarball: {old_path}")
                try:
                    os.remove(old_path)
                except OSError as e:
                    logger.warning(f"Failed to remove old tarball {old_path}: {e}")

        # remove all the dangling images (not just the one we created)
        logger.info("Cleaning up dangling images...")
        _run_command(["docker", "image", "prune", "-f"], check=False)

        logger.info(
            f"HakuRiver base container tarball created successfully at {tarball_path}"
        )
        return tarball_path

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create container tarball: {e}")
        # Attempt cleanup of the HakuRiver tagged image if it was created but failed later
        try:
            _run_command(["docker", "rmi", "--force", hakuriver_image_tag], check=False)
        except Exception as e:
            pass  # Ignore cleanup errors here
        return None
    except Exception as e:
        logger.exception(
            f"An unexpected error occurred during tarball creation from '{source_container_name}': {e}"
        )
        return None


def list_shared_container_tars(
    container_tar_dir: str, container_name: str
) -> list[tuple[int, str]]:
    """
    Lists available container tarballs in the specified directory for a given container name.

    Args:
        container_tar_dir: Absolute path to the directory containing container tarballs.
        container_name: The HakuRiver container name.

    Returns:
        A list of (timestamp, absolute_filepath) tuples, sorted by timestamp (newest first).
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
                    continue
    except Exception as e:
        logger.exception(f"Error listing container tars in {container_tar_dir}: {e}")
        return []

    tar_files.sort(key=lambda item: item[0], reverse=True)
    return tar_files


def get_local_image_timestamp(container_name: str) -> int | None:
    """
    Gets the creation timestamp of the local HakuRiver base image.

    Args:
        container_name: The HakuRiver container name.

    Returns:
        The creation timestamp as an integer (Unix time), or None if the image is not found.
    """
    hakuriver_image_tag = f"hakuriver/{container_name}:base".lower()
    try:
        # Use docker image inspect to get the creation timestamp
        result = _run_command(
            ["docker", "image", "inspect", hakuriver_image_tag],
            check=True,
            capture_output=True,
            text=True,
        )
        # Parse the JSON output
        image_info = json.loads(result.stdout)[0]
        # The 'Created' field is in RFC 3339 format, convert to Unix timestamp
        created_time_str = image_info.get("Created")
        if created_time_str:
            # Python 3.7+ supports parsing this format directly with fromisoformat
            dt_obj = datetime.datetime.fromisoformat(
                created_time_str.replace("Z", "+00:00")
            )
            return int(dt_obj.timestamp())
        return None
    except subprocess.CalledProcessError as e:
        # Check stderr for the specific "No such image" error
        if "No such image" in e.stderr:
            logger.debug(f"Local image {hakuriver_image_tag} not found.")
            return None
        logger.error(
            f"Error inspecting local Docker image {hakuriver_image_tag}: {e.stderr}"
        )
        return None
    except (json.JSONDecodeError, KeyError, IndexError, ValueError) as e:
        logger.error(
            f"Error parsing docker image inspect output for {hakuriver_image_tag}: {e}"
        )
        return None
    except Exception as e:
        logger.exception(
            f"An unexpected error occurred while inspecting local image {hakuriver_image_tag}: {e}"
        )
        return None


def needs_sync(container_name: str, container_tar_dir: str) -> tuple[bool, str | None]:
    """
    Checks if the local image needs to be synced from the container tar directory.

    Args:
        container_name: The HakuRiver container name.
        container_tar_dir: Absolute path to the directory containing container tarballs.

    Returns:
        A tuple: (needs_sync, path_to_latest_tar).
        needs_sync is True if a newer tarball exists than the local image.
        path_to_latest_tar is the path to the newest tarball if sync is needed, otherwise None.
    """
    local_timestamp = get_local_image_timestamp(container_name)
    shared_tars = list_shared_container_tars(container_tar_dir, container_name)

    if not shared_tars:
        logger.debug(f"No shared tarballs found for container '{container_name}'.")
        return False, None

    latest_shared_timestamp, latest_shared_path = shared_tars[0]

    if local_timestamp is None:
        logger.info(
            f"Local image '{container_name}' not found. Sync is needed from {latest_shared_path}."
        )
        return True, latest_shared_path
    elif latest_shared_timestamp > local_timestamp:
        logger.info(
            f"Newer shared tarball found for '{container_name}' "
            f"(shared: {latest_shared_timestamp}, local: {local_timestamp}). "
            f"Sync is needed from {latest_shared_path}."
        )
        return True, latest_shared_path
    else:
        logger.debug(
            f"Local image '{container_name}' is up-to-date "
            f"(local: {local_timestamp}, latest shared: {latest_shared_timestamp}). "
            "No sync needed."
        )
        return False, None


def sync_from_shared(container_name: str, tarball_path: str) -> bool:
    """
    Loads a container image from a tarball into the local Docker registry.

    Args:
        container_name: The HakuRiver container name. (Used for logging)
        tarball_path: Absolute path to the .tar file.

    Returns:
        True if sync was successful, False otherwise.
    """
    logger.info(
        f"Syncing image for container '{container_name}' from tarball: {tarball_path}"
    )
    if not os.path.exists(tarball_path):
        logger.error(f"Tarball not found: {tarball_path}")
        return False

    try:
        # docker load reads from stdin by default, or from -i FILE
        _run_command(["docker", "load", "-i", tarball_path], check=True)
        logger.info(f"Successfully loaded image from {tarball_path}.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to load image from tarball {tarball_path}: {e}")
        return False
    except Exception as e:
        logger.exception(
            f"An unexpected error occurred while syncing from {tarball_path}: {e}"
        )
        return False



package_manager_lists = [
    "apk",
    "apt-get",
    "apt",
    "yum",
    "dnf",
    "zypper",
    "pacman",
    "emerge",
    "xbps-install",
    "pkg_add",
    "pkg",
]
def find_package_manager(container_image_name: str) -> str | None:
    container_image_name = container_image_name.lower()
    for manager in package_manager_lists:
        logger.debug(
            f"Checking for package manager '{manager}' in container image '{container_image_name}'..."
        )
        if _run_command(
            ["docker", "run", "--rm", container_image_name, "which", manager]
        ).returncode == 0:
            return manager
    return None


def modify_command_for_docker(
    original_command_list: list[str],
    container_image_name: str,  # This should be hakuriver/<container_name>:base
    task_id: int,
    # These are handled by the runner now based on its config
    privileged: bool = False,
    mount_dirs: (
        list[str] | None
    ) = None,  # Keep this for additional mounts specified by host
    working_dir: str = "/shared",  # Default working directory inside the container
    cpu_cores: int = 0,  # Default CPU cores to allocate (optional)
    memory_limit: str = "",  # Default memory limit (optional)
    gpu_ids: list[int] = [],
) -> list[str]:
    """
    Wraps an original command list with a 'docker run --rm' command.
    Mounts for shared/temp dirs should be added by the caller (runner) based on its config.

    Args:
        original_command_list: The command and arguments to run inside the container.
        container_image_name: The name/tag of the Docker image to use (e.g., 'hakuriver/myenv:base').
        task_id: The HakuRiver task ID (used for temporary container name).
        privileged: If True, run the container with --privileged flag.
        mount_dirs: Optional list of *additional* host directories to mount
                    into the container. Each entry should be 'host_path:container_path'.
                    (e.g., ["/data:/app/data"])

    Returns:
        A list representing the full command to execute via subprocess,
        starting with 'docker', 'run', etc.
    """
    container_image_name = container_image_name.lower()
    docker_cmd = ["docker", "run", "--rm"]

    # Add name for easier identification (optional but helpful)
    docker_cmd.extend(["--name", f"hakuriver-task-{task_id}"])
    docker_cmd.extend(["--network", "host"])  # Use host network for simplicity

    # Add privileged flag if requested
    if privileged:
        docker_cmd.append("--privileged")
        logger.warning(
            f"Task {task_id}: Running Docker container with --privileged flag!"
        )
    else:
        docker_cmd.extend(["--cap-add", "SYS_NICE"])

    # Add *additional* mount directories specified by the host/task request
    if mount_dirs:
        for mount in mount_dirs:
            parts = mount.split(":")
            if len(parts) < 2:
                logger.warning(
                    f"Invalid mount format: '{mount}'. Expected 'host_path:container_path'. Skipping."
                )
                continue
            host_path, container_path, *options = parts
            option_str = ("," + ",".join(options)) if options else ""
            docker_cmd.extend(
                [
                    "--mount",
                    f"type=bind,source={host_path},target={container_path}{option_str}",
                ]
            )
    if working_dir:
        docker_cmd.extend(["--workdir", working_dir])
    if cpu_cores > 0:
        docker_cmd.extend(["--cpus", str(cpu_cores)])
    if memory_limit:
        docker_cmd.extend(["--memory", memory_limit])
    if gpu_ids:
        id_string = ",".join(map(str, gpu_ids))
        docker_cmd.extend(["--gpus", f'\'"device={id_string}"\''])

    # Add the container image name
    docker_cmd.append(container_image_name)

    # Add the original command and arguments to be run *inside* the container
    docker_cmd.extend(original_command_list)

    logger.debug(f"Base docker command for task {task_id}: {docker_cmd}")

    return docker_cmd


def vps_command_for_docker(
    container_image_name: str,  # This should be hakuriver/<container_name>:base
    task_id: int,
    # These are handled by the runner now based on its config
    ssh_port: int = 0,  # Port for SSH access (0 for random port)
    privileged: bool = False,
    mount_dirs: list[str] | None = None,
    working_dir: str = "/shared",  # Default working directory inside the container
    cpu_cores: int = 0,  # Default CPU cores to allocate (optional)
    memory_limit: str = "",  # Default memory limit (optional)
    gpu_ids: list[int] = [],
    public_key: str = "",  # Public key for SSH access (optional)
    detached: bool = True,  # Run in detached mode
    distro: str = "",  # Linux distribution ("alpine", "debian", "ubuntu", "centos", "redhat")
) -> list[str]:
    """
    Make a command to create persistent VPS container for SSH access.
    Mounts for shared/temp dirs should be added by the caller (runner) based on its config.

    Args:
        container_image_name: The name/tag of the Docker image to use (e.g., 'hakuriver/myenv:base').
        task_id: The HakuRiver task ID (used for temporary container name).
        ssh_port: Port for SSH access (0 for random port, Docker will assign one)
        privileged: If True, run the container with --privileged flag.
        mount_dirs: Optional list of *additional* host directories to mount
                    into the container. Each entry should be 'host_path:container_path'.
                    (e.g., ["/data:/app/data"])
        working_dir: Default working directory inside the container
        cpu_cores: Number of CPU cores to allocate
        memory_limit: Memory limit (e.g., "2g" for 2 gigabytes)
        gpu_ids: List of GPU IDs to make available to the container
        public_key: Public key for SSH access (required for SSH functionality)
        restart_policy: Docker restart policy (default: unless-stopped)
        detached: Run in detached mode (-d flag)
        distro: Linux distribution to use for setup ("alpine", "debian", "ubuntu",
                "centos", "redhat"). If empty, will auto-detect from image name.

    Returns:
        A list representing the full command to execute via subprocess,
        starting with 'docker', 'run', etc.
    """
    container_image_name = container_image_name.lower()
    docker_cmd = ["docker", "run", "--restart", "unless-stopped"]

    # Add detached mode if requested
    if detached:
        docker_cmd.append("-d")

    # Add name for easier identification (optional but helpful)
    docker_cmd.extend(["--name", f"hakuriver-vps-{task_id}"])

    # Note: --network host and -p are conflicting.
    # If using host network, individual port mappings aren't needed
    # But for SSH access, we need a specific port mapping, so we won't use host networking
    docker_cmd.extend(["-p", f"{ssh_port}:22"])  # Map SSH port to host

    # Add privileged flag if requested
    if privileged:
        docker_cmd.append("--privileged")
        logger.warning(
            f"Task {task_id}: Running Docker container with --privileged flag!"
        )
    else:
        docker_cmd.extend(["--cap-add", "SYS_NICE"])

    # Add *additional* mount directories specified by the host/task request
    if mount_dirs:
        for mount in mount_dirs:
            parts = mount.split(":")
            if len(parts) < 2:
                logger.warning(
                    f"Invalid mount format: '{mount}'. Expected 'host_path:container_path'. Skipping."
                )
                continue
            host_path, container_path, *options = parts
            option_str = ("," + ",".join(options)) if options else ""
            docker_cmd.extend(
                [
                    "--mount",
                    f"type=bind,source={host_path},target={container_path}{option_str}",
                ]
            )
    if working_dir:
        docker_cmd.extend(["--workdir", working_dir])
    if cpu_cores > 0:
        docker_cmd.extend(["--cpus", str(cpu_cores)])
    if memory_limit:
        docker_cmd.extend(["--memory", memory_limit])
    if gpu_ids:
        id_string = ",".join(map(str, gpu_ids))
        docker_cmd.extend(["--gpus", f'"device={id_string}"'])

    # Determine which Linux distribution to use for setup
    detected_package_manager = find_package_manager(container_image_name)

    # Set up SSH based on the determined distribution
    match detected_package_manager:
        case "apk":
            setup_cmd = "apk update && apk add --no-cache openssh"
        case "apt":
            setup_cmd = "apt update && apt install -y openssh-server"
        case "apt-get":
            setup_cmd = "apt-get update && apt-get install -y openssh-server"
        case "dnf":
            setup_cmd = "dnf update && dnf install -y openssh-server"
        case "yum":
            setup_cmd = "yum update && yum install -y openssh-server"
        case "zypper":
            setup_cmd = "zypper refresh && zypper install -y openssh"
        case "pacman":
            setup_cmd = "pacman -Syu --noconfirm openssh"
        case "emerge":
            setup_cmd = "emerge --sync openssh"
        case "xbps-install":
            setup_cmd = "xbps-install -Syu openssh"
        case "pkg_add":
            setup_cmd = "pkg_add openssh"
        case "pkg":
            setup_cmd = "pkg update && pkg install -y openssh"
        case _:
            logger.error(
                f"Unsupported package manager '{detected_package_manager}' for image '{container_image_name}'."
            )
            raise ValueError(f"Unsupported package manager: {detected_package_manager}")
    setup_cmd += (
        " && "
        "ssh-keygen -A && "  # Generate host keys if they don't exist
        "echo 'PasswordAuthentication no' >> /etc/ssh/sshd_config && "
        "echo 'PermitRootLogin yes' >> /etc/ssh/sshd_config && "
        "mkdir -p /run/sshd && "
        "chmod 0755 /run/sshd && "
        "mkdir -p /root/.ssh && "
        f"echo '{public_key}' > /root/.ssh/authorized_keys && "
        "chmod 700 /root/.ssh && "
        "chmod 600 /root/.ssh/authorized_keys && "
        "/usr/sbin/sshd -D -e"  # Use -e flag for easier debugging
    )

    # Add the container image name
    docker_cmd.append(container_image_name)
    docker_cmd.extend(["/bin/sh", "-c", setup_cmd])

    logger.debug(f"Docker command for VPS {task_id}: {docker_cmd}")

    return docker_cmd


def find_ssh_port(container_name: str) -> int | None:
    try:
        result = _run_command(
            ["docker", "port", container_name, "22"],
            check=True,
            capture_output=True,
            text=True,
        )
        """
        it may have multiple line:
        > docker port hakuriver-vps-7323718749301768192 22
        0.0.0.0:32792
        [::]:32792
        """
        # Extract the first port mapping (IPv4)
        port_mapping = result.stdout.splitlines()[0].strip()
        return int(port_mapping.split(":")[1])
    except subprocess.CalledProcessError:
        logger.error(f"Failed to find SSH port for container '{container_name}'")
        return None
    except FileNotFoundError:
        return None


# Example Usage (for standalone testing - requires Docker daemon)
if __name__ == "__main__":
    logger.setLevel("DEBUG")
    logger.info("Starting Docker command example...")
    vps_docker_cmd = vps_command_for_docker(
        "hakuriver/py313:base",
        "test",
        distro="alpine",
        public_key="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJaT9GDwMEOCDa+2PThDgipYrWlbg0umOptqAkp28Pb9 apoll@RiceShower",
    )
    _run_command(["sudo"] + vps_docker_cmd)
