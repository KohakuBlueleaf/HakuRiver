"""
CLI entry point for the HakuRiver Runner agent.

Usage:
    kohakuriver.runner [--config PATH]
"""

import logging
import sys
from typing import Annotated

import typer

app = typer.Typer(help="HakuRiver Runner agent")
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
    """Run the HakuRiver Runner agent."""
    # Load and apply config
    if config:
        print(f"Loading configuration from: {config}")
        try:
            from kohakuengine import Config as KohakuConfig

            kohaku_config = KohakuConfig.from_file(config)

            # Apply globals to our config instance
            from kohakuriver.runner.config import config as runner_config

            for key, value in kohaku_config.globals_dict.items():
                if hasattr(runner_config, key):
                    setattr(runner_config, key, value)

        except ImportError:
            print("WARNING: KohakuEngine not found, config file ignored.")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise typer.Exit(1)

    # Run the server
    try:
        print("Starting HakuRiver Runner agent...")
        from kohakuriver.runner.app import run as run_server

        run_server()

    except Exception as e:
        logger.critical(f"FATAL: Runner agent failed to start: {e}", exc_info=True)
        raise typer.Exit(1)


def main():
    """Entry point for kohakuriver.runner."""
    app()


if __name__ == "__main__":
    main()
