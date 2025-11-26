"""
CLI entry point for the HakuRiver Host server.

Usage:
    hakuriver.host [--config PATH]
"""

import logging
import sys
from typing import Annotated

import typer

app = typer.Typer(help="HakuRiver Host server")
logger = logging.getLogger(__name__)


@app.command()
def run(
    config: Annotated[
        str | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to a Python configuration file (KohakuEngine format).",
        ),
    ] = None,
):
    """Run the HakuRiver Host server."""
    # Load and apply config
    if config:
        print(f"Loading configuration from: {config}")
        try:
            from kohakuengine import Config as KohakuConfig

            kohaku_config = KohakuConfig.from_file(config)

            # Apply globals to our config instance
            from hakuriver.host.config import config as host_config

            for key, value in kohaku_config.globals_dict.items():
                if hasattr(host_config, key):
                    setattr(host_config, key, value)

        except ImportError:
            print("WARNING: KohakuEngine not found, config file ignored.")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise typer.Exit(1)

    # Run the server
    try:
        print("Starting HakuRiver Host server...")
        from hakuriver.host.app import run as run_server

        run_server()

    except Exception as e:
        logger.critical(f"FATAL: Host server failed to start: {e}", exc_info=True)
        raise typer.Exit(1)


def main():
    """Entry point for hakuriver.host."""
    app()


if __name__ == "__main__":
    main()
