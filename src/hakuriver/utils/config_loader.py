import toml
import os
import sys

from .logger import logger


DEFAULT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILENAME = "default_config.toml"
if os.path.exists(os.path.join(os.path.expanduser("~"), ".hakuriver", "config.toml")):
    CONFIG_FILENAME = os.path.join(os.path.expanduser("~"), ".hakuriver", "config.toml")
if "HAKURIVER_CONFIG" in os.environ:
    CONFIG_FILENAME = os.environ["HAKURIVER_CONFIG"]


def find_config_path():
    """Tries to find config.toml in common locations."""
    # 1. Next to the script that imports this module
    script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    path1 = os.path.join(script_dir, CONFIG_FILENAME)
    if os.path.exists(path1):
        return path1

    # 2. In the current working directory
    path2 = os.path.join(os.getcwd(), CONFIG_FILENAME)
    if os.path.exists(path2):
        return path2

    # 3. In the directory containing this config_loader.py file
    loader_dir = os.path.dirname(os.path.abspath(__file__))
    path3 = os.path.join(loader_dir, CONFIG_FILENAME)
    if os.path.exists(path3):
        return path3

    return None  # Not found


def load_config(config_path: str = None):
    """Loads the TOML configuration file."""
    config_path = config_path or find_config_path()
    if not config_path:
        logger.error(
            f"Error: Configuration file '{CONFIG_FILENAME}' not found.", file=sys.stderr
        )
        sys.exit(1)

    try:
        with open(config_path, "r") as f:
            config_data = toml.load(f)
        logger.info(f"Configuration loaded from: {config_path}")
        return config_data
    except toml.TomlDecodeError as e:
        logger.error(f"Error decoding TOML file '{config_path}': {e}", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        logger.error(
            f"Error reading configuration file '{config_path}': {e}", file=sys.stderr
        )
        sys.exit(1)


# Load configuration immediately when this module is imported
settings = load_config()
