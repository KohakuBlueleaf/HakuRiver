"""
CLI entry point for the HakuRiver Runner agent.

Usage:
    hakuriver.runner --config ~/.hakuriver/runner_config.py
"""

import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def main():
    """CLI entry point for running the Runner agent."""
    parser = argparse.ArgumentParser(description="Run the HakuRiver Runner agent.")
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        help="Path to a Python configuration file (KohakuEngine format).",
        default=None,
    )
    args = parser.parse_args()

    # Load and apply config
    if args.config:
        print(f"Loading configuration from: {args.config}")
        try:
            from kohakuengine import Config as KohakuConfig

            kohaku_config = KohakuConfig.from_file(args.config)

            # Apply globals to our config instance
            from hakuriver.runner.config import config

            for key, value in kohaku_config.globals_dict.items():
                if hasattr(config, key):
                    setattr(config, key, value)

        except ImportError:
            print("WARNING: KohakuEngine not found, config file ignored.")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            sys.exit(1)

    # Run the server
    try:
        print("Starting HakuRiver Runner agent...")
        from hakuriver.runner.app import run

        run()

    except Exception as e:
        logger.critical(f"FATAL: Runner agent failed to start: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
