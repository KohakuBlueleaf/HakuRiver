import argparse
import os
import sys

import toml
import uvicorn
import hakuriver.core.runner as runner_core


def update_config(config_instance, custom_config_data):
    """Updates attributes of the config instance based on custom data."""
    logger = None
    try:
        # Runner's logger might include hostname, potentially set up during import
        from hakuriver.utils.logger import logger
    except ImportError:
        pass  # Logger might not be set up yet

    if not config_instance or not isinstance(custom_config_data, dict):
        return

    log_prefix = f"{type(config_instance).__name__}"  # e.g., "RUNNER_CONFIG"

    for key, value in custom_config_data.items():
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                if hasattr(config_instance, sub_key):
                    current_sub_value = getattr(config_instance, sub_key)
                    msg = f"Overriding {log_prefix}.{sub_key} from section '{key}': {current_sub_value} -> {sub_value}"
                    if logger:
                        logger.info(msg)
                    else:
                        print(msg)
                    try:
                        setattr(config_instance, sub_key, sub_value)
                    except AttributeError:
                        warn_msg = f"Could not set {log_prefix}.{sub_key} (read-only?)"
                        if logger:
                            logger.warning(warn_msg)
                        else:
                            print(f"Warning: {warn_msg}")
        elif hasattr(config_instance, key):
            current_value = getattr(config_instance, key)
            msg = f"Overriding {log_prefix}.{key}: {current_value} -> {value}"
            if logger:
                logger.info(msg)
            else:
                print(msg)
            try:
                setattr(config_instance, key, value)
            except AttributeError:
                warn_msg = f"Could not set {log_prefix}.{key} (read-only?)"
                if logger:
                    logger.warning(warn_msg)
                else:
                    print(f"Warning: {warn_msg}")


def main():
    """CLI entry point for running the Runner agent."""
    parser = argparse.ArgumentParser(description="Run the HakuRiver Runner agent.")
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        help="Path to a custom TOML configuration file to override defaults.",
        default=None,
    )
    args = parser.parse_args()

    custom_config_data = None
    if args.config:
        config_path = os.path.abspath(args.config)
        if not os.path.exists(config_path):
            print(
                f"Error: Custom config file not found: {config_path}", file=sys.stderr
            )
            sys.exit(1)
        try:
            with open(config_path, "r") as f:
                custom_config_data = toml.load(f)
            print(f"Loaded custom configuration from: {config_path}")
        except (toml.TomlDecodeError, IOError) as e:
            print(
                f"Error loading or reading config file '{config_path}': {e}",
                file=sys.stderr,
            )
            sys.exit(1)

    # --- Apply Custom Config Overrides ---
    if custom_config_data:
        print("Applying custom configuration overrides...")
        update_config(runner_core.RUNNER_CONFIG, custom_config_data)
        print("Custom configuration applied.")

    # --- Execute: Run Uvicorn ---
    # Runner typically binds to 0.0.0.0
    runner_bind_ip = "0.0.0.0"
    runner_port = runner_core.RUNNER_CONFIG.RUNNER_PORT
    print(f"Starting HakuRiver Runner agent on {runner_bind_ip}:{runner_port}...")
    try:
        uvicorn.run(
            runner_core.app,  # Pass the app instance
            host=runner_bind_ip,
            port=runner_port,
            log_config=None,  # Use logger configured by setup_logging
        )
    except Exception as e:
        logger = getattr(runner_core, "logger", None)
        log_msg = f"FATAL: Runner agent failed to start: {e}"
        if logger:
            logger.critical(log_msg, exc_info=True)
        else:
            print(log_msg, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
