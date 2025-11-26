import os
import subprocess
import tempfile

from .logger import logger


def read_public_key_file(file_path: str) -> str:
    """Reads an SSH public key from a file."""
    try:
        path = os.path.expanduser(file_path)  # Expand ~
        with open(path, "r") as f:
            key = f.read().strip()
        if not key:
            raise ValueError(f"Public key file '{file_path}' is empty.")
        # Basic validation: check if it starts with "ssh-"
        if not key.startswith("ssh-"):
            logger.warning(
                f"Public key in file '{file_path}' does not start with 'ssh-'. Is this a valid public key?"
            )
        return key
    except FileNotFoundError:
        # Re-raise with a more specific error type
        raise FileNotFoundError(f"Public key file not found: '{file_path}'")
    except IOError as e:
        # Re-raise with a specific error type
        raise IOError(f"Error reading public key file '{file_path}': {e}")
    except Exception as e:
        # Catch any other unexpected errors
        raise Exception(
            f"Unexpected error processing public key file '{file_path}': {e}"
        )


def generate_ssh_keypair(
    private_key_path: str,
    key_type: str = "ed25519",
    comment: str = "",
) -> tuple[str, str]:
    """
    Generate an SSH keypair.

    Args:
        private_key_path: Path to save the private key.
        key_type: Key type (ed25519, rsa).
        comment: Comment for the key.

    Returns:
        Tuple of (private_key_path, public_key_string).

    Raises:
        RuntimeError: If key generation fails.
    """
    private_key_path = os.path.expanduser(private_key_path)
    public_key_path = f"{private_key_path}.pub"

    # Ensure parent directory exists
    parent_dir = os.path.dirname(private_key_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    # Remove existing keys if they exist
    for path in [private_key_path, public_key_path]:
        if os.path.exists(path):
            os.remove(path)

    # Build ssh-keygen command
    cmd = [
        "ssh-keygen",
        "-t",
        key_type,
        "-f",
        private_key_path,
        "-N",
        "",  # Empty passphrase
        "-q",  # Quiet mode
    ]

    if comment:
        cmd.extend(["-C", comment])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to generate SSH key: {e.stderr}")
    except FileNotFoundError:
        raise RuntimeError("ssh-keygen not found. Please install OpenSSH.")

    # Read the generated public key
    try:
        public_key = read_public_key_file(public_key_path)
    except Exception as e:
        raise RuntimeError(f"Failed to read generated public key: {e}")

    # Set proper permissions
    os.chmod(private_key_path, 0o600)
    os.chmod(public_key_path, 0o644)

    logger.info(f"Generated SSH keypair: {private_key_path}")

    return private_key_path, public_key


def get_default_key_output_path(task_id: int | str) -> str:
    """
    Get the default path for generated SSH key.

    Args:
        task_id: Task ID for the VPS.

    Returns:
        Path like ~/.ssh/id-hakuriver-<task_id>
    """
    ssh_dir = os.path.expanduser("~/.ssh")
    return os.path.join(ssh_dir, f"id-hakuriver-{task_id}")
