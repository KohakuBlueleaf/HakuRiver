"""
Default host configuration.

This file demonstrates the KohakuEngine config pattern.
Copy this file and modify values to create custom configurations.
"""

from kohakuengine import Config


def config_gen() -> Config:
    """
    KohakuEngine entry point.

    Returns Config with default values (no overrides).
    """
    return Config.from_globals()
