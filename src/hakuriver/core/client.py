import json
import sys
import httpx
from hakuriver.utils.config_loader import settings


class ClientConfig:
    """Holds client-specific configuration, potentially modifiable."""

    def __init__(self):
        """Initializes configuration from loaded settings."""
        self._load_settings()

    def _load_settings(self):
        """Loads relevant settings from the global 'settings' object."""
        try:
            self.host_address: str = settings["network"]["host_reachable_address"]
            self.host_port: int = settings["network"]["host_port"]
            # Default timeouts (can be overridden in requests if needed)
            self.default_timeout: float = 30.0
            self.status_timeout: float = 10.0
            self.kill_timeout: float = 15.0
            self.nodes_timeout: float = 10.0
            self.health_timeout: float = 15.0
        except KeyError as e:
            print(
                f"Error: Missing configuration key in config.toml: {e}",
                file=sys.stderr,
            )
            print("Exiting.", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error processing configuration: {e}", file=sys.stderr)
            print("Exiting.", file=sys.stderr)
            sys.exit(1)

    @property
    def host_url(self) -> str:
        """Constructs the full base URL for the host API."""
        return f"http://{self.host_address}:{self.host_port}"

    def update_setting(self, key: str, value: any):
        """Allows updating a configuration value 'on the fly' (use with caution)."""
        if hasattr(self, key):
            print(f"Updating config '{key}' from '{getattr(self, key)}' to '{value}'")
            setattr(self, key, value)
        else:
            print(f"Warning: Config key '{key}' not found.", file=sys.stderr)


# --- Instantiate Configuration ---
# This happens after settings are loaded and the class is defined.
client_config = ClientConfig()


# --- Helper Functions ---


def print_response(response: httpx.Response):
    """Helper to print formatted JSON response or error text."""
    print(f"HTTP Status Code: {response.status_code}")
    try:
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            data = response.json()
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print("Response Text:")
            print(response.text)
    except json.JSONDecodeError:
        print("Response Text (non-JSON or parse error):")
        print(response.text)
    except Exception as e:
        print(f"Error processing response content: {e}")
        print("Raw Response Text:")
        print(response.text)


def parse_key_value(items: list[str]) -> dict[str, str]:
    """Parses ['KEY1=VAL1', 'KEY2=VAL2'] into {'KEY1': 'VAL1', 'KEY2': 'VAL2'}"""
    result = {}
    if not items:
        return result
    for item in items:
        parts = item.split("=", 1)
        if len(parts) == 2:
            result[parts[0].strip()] = parts[1].strip()
        else:
            print(
                f"Warning: Ignoring invalid environment variable format: {item}",
                file=sys.stderr,
            )
    return result


# --- Client API Functions ---
def submit_task(
    command: str,
    args: list[str],
    env: dict[str, str],
    cores: int,
    memory_bytes: int | None,
    private_network: bool,
    private_pid: bool,
) -> str | None:
    """Submits a task to the host."""
    url = f"{client_config.host_url}/submit"
    payload = {
        "command": command,
        "arguments": args,
        "env_vars": env,
        "required_cores": cores,
        "required_memory_bytes": memory_bytes,
        "use_private_network": private_network,
        "use_private_pid": private_pid,
    }
    print(f"Submitting task to {url}")
    print("Payload:", json.dumps(payload, indent=2))
    try:
        with httpx.Client(timeout=client_config.default_timeout) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            print("--- Response ---")
            result = response.json()
            print_response(response)
            return result.get("task_id")
    except httpx.HTTPStatusError as e:
        print("--- Error ---")
        print_response(e.response)
    except httpx.RequestError as e:
        print("--- Connection Error ---")
        print(f"Error connecting to host at {url}: {e}")
    except Exception as e:
        print("--- Unexpected Error ---")
        print(f"An unexpected error occurred: {e}")
    return None


def check_status(task_id: str) -> str | None:
    """Checks the status of a specific task."""
    url = f"{client_config.host_url}/status/{task_id}"
    print(f"Checking status for task {task_id} at {url}")
    try:
        with httpx.Client(timeout=client_config.status_timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            print("--- Task Status ---")
            print_response(response)
            try:
                # Return status for wait logic
                return response.json().get("status")
            except (json.JSONDecodeError, AttributeError):
                print("Warning: Could not parse status from response.", file=sys.stderr)
                return None
    except httpx.HTTPStatusError as e:
        print("--- Error ---")
        print_response(e.response)
    except httpx.RequestError as e:
        print("--- Connection Error ---")
        print(f"Error connecting to host at {url}: {e}")
    except Exception as e:
        print("--- Unexpected Error ---")
        print(f"An unexpected error occurred: {e}")
    return None


def kill_task(task_id: str):
    """Requests the host to kill a task."""
    url = f"{client_config.host_url}/kill/{task_id}"
    print(f"Requesting kill for task {task_id} at {url}")
    try:
        with httpx.Client(timeout=client_config.kill_timeout) as client:
            response = client.post(url)  # Defined as POST in host
            response.raise_for_status()
            print("--- Kill Request Response ---")
            print_response(response)
    except httpx.HTTPStatusError as e:
        print("--- Error ---")
        print_response(e.response)
    except httpx.RequestError as e:
        print("--- Connection Error ---")
        print(f"Error connecting to host at {url}: {e}")
    except Exception as e:
        print("--- Unexpected Error ---")
        print(f"An unexpected error occurred: {e}")


def list_nodes():
    """Fetches the status of compute nodes from the host."""
    url = f"{client_config.host_url}/nodes"
    print(f"Fetching node status from {url}")
    try:
        with httpx.Client(timeout=client_config.nodes_timeout) as client:
            response = client.get(url)
            response.raise_for_status()
            print("--- Nodes Status ---")
            print_response(response)
    except httpx.HTTPStatusError as e:
        print("--- Error ---")
        print_response(e.response)
    except httpx.RequestError as e:
        print("--- Connection Error ---")
        print(f"Error connecting to host at {url}: {e}")
    except Exception as e:
        print("--- Unexpected Error ---")
        print(f"An unexpected error occurred: {e}")


def get_health(hostname: str | None = None):
    """Fetches the health status from the host's /health endpoint."""
    url = f"{client_config.host_url}/health"
    params = {}
    if hostname:
        params["hostname"] = hostname
        print(f"Fetching health status for node {hostname} from {url}")
    else:
        print(f"Fetching cluster health status from {url}")

    try:
        with httpx.Client(timeout=client_config.health_timeout) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            print("--- Health Status ---")
            print_response(response)
    except httpx.HTTPStatusError as e:
        print("--- Error ---")
        print_response(e.response)
    except httpx.RequestError as e:
        print("--- Connection Error ---")
        print(f"Error connecting to host at {url}: {e}")
    except Exception as e:
        print("--- Unexpected Error ---")
        print(f"An unexpected error occurred: {e}")
