import argparse
import os
import sys

import toml
import uvicorn
import hakuriver.core.host as host_core


def update_config(config_instance, custom_config_data):
    """Updates attributes of the config instance based on custom data."""
    # This function needs access to the logger *after* core potentially sets it up
    logger = None
    try:
        from hakuriver.utils.logger import logger
    except ImportError:
        pass  # Logger might not be set up yet

    if not config_instance or not isinstance(custom_config_data, dict):
        return

    log_prefix = f"{type(config_instance).__name__}"  # e.g., "HOST_CONFIG"

    for key, value in custom_config_data.items():
        # Handle nested TOML sections mapping to potentially flat config attributes
        if isinstance(value, dict):
            # Look for attributes matching keys within the nested dict
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
        # Handle direct attribute overrides (for top-level TOML keys or if structure matches)
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
    """CLI entry point for running the Host server."""
    parser = argparse.ArgumentParser(description="Run the HakuRiver Host server.")
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
        update_config(host_core.HOST_CONFIG, custom_config_data)
        print("Custom configuration applied.")
        # NOTE: If logging setup depends heavily on config values that were
        # just overridden, the logging might not reflect the overrides
        # unless re-initialized here. Assumes basic setup is okay.

    # --- Execute: Run Uvicorn ---
    host_ip = host_core.HOST_CONFIG.HOST_BIND_IP
    host_port = host_core.HOST_CONFIG.HOST_PORT
    print(f"Starting HakuRiver Host server on {host_ip}:{host_port}...")
    try:
        uvicorn.run(
            host_core.app,  # Pass the app instance directly
            host=host_ip,
            port=host_port,
            log_config=None,  # Use logger configured by setup_logging
            # Add other uvicorn options if needed, e.g., workers=N
        )
    except Exception as e:
        # Attempt to use logger if available, otherwise print
        logger = getattr(host_core, "logger", None)
        log_msg = f"FATAL: Host server failed to start: {e}"
        if logger:
            logger.critical(log_msg, exc_info=True)
        else:
            print(log_msg, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
