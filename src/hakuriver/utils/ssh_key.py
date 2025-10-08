import os
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
