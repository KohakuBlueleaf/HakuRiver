import os

from hakuriver.utils.logger import logger


def main():
    default_config_path = os.path.join(os.path.expanduser("~"), ".hakuriver")
    if not os.path.exists(default_config_path):
        os.makedirs(default_config_path)

    base_dir = os.path.dirname(__file__).split("/src")[0]
    config_path = os.path.join(base_dir, "src", "utils", "default_config.toml")
    default_config_file = os.path.join(default_config_path, "config.toml")
    if not os.path.exists(default_config_file):
        with open(default_config_file, "w") as f:
            with open(config_path, "r") as g:
                f.write(g.read())
    logger.info(f"Default config file created at {default_config_file}")