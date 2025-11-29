"""
CLI parsing utilities for HakuRiver.

This module provides helper functions for parsing command-line arguments
and configuration strings into structured data types.
"""

import re

from kohakuriver.utils.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# Memory Parsing
# =============================================================================


def parse_memory_string(mem_str: str) -> int | None:
    """
    Parse a human-readable memory string into bytes.

    Supports suffixes K (kilobytes), M (megabytes), G (gigabytes).
    Uses SI units (1K = 1000 bytes, not 1024).

    Args:
        mem_str: Memory string like '4G', '512M', '2K', or '1000000'.

    Returns:
        Memory size in bytes, or None if input is empty.

    Raises:
        ValueError: If the format is invalid.

    Examples:
        >>> parse_memory_string('4G')
        4000000000
        >>> parse_memory_string('512M')
        512000000
        >>> parse_memory_string('1000')
        1000
    """
    if not mem_str:
        return None

    mem_str = mem_str.upper().strip()
    match = re.match(r"^(\d+)([KMG]?)$", mem_str)

    if not match:
        raise ValueError(
            f"Invalid memory format: '{mem_str}'. "
            "Use suffix K, M, or G (e.g., 512M, 4G)."
        )

    value = int(match.group(1))
    unit = match.group(2)

    multipliers = {
        "G": 1_000_000_000,
        "M": 1_000_000,
        "K": 1_000,
        "": 1,
    }

    return value * multipliers[unit]


# =============================================================================
# Key-Value Parsing
# =============================================================================


def parse_key_value(items: list[str]) -> dict[str, str]:
    """
    Parse a list of KEY=VALUE strings into a dictionary.

    Args:
        items: List of strings in 'KEY=VALUE' format.

    Returns:
        Dictionary mapping keys to values.

    Examples:
        >>> parse_key_value(['FOO=bar', 'BAZ=qux'])
        {'FOO': 'bar', 'BAZ': 'qux'}
        >>> parse_key_value(['PATH=/usr/bin:/bin'])
        {'PATH': '/usr/bin:/bin'}
    """
    if not items:
        return {}

    result: dict[str, str] = {}

    for item in items:
        parts = item.split("=", 1)
        if len(parts) == 2:
            key = parts[0].strip()
            value = parts[1].strip()
            result[key] = value
        else:
            logger.warning(f"Ignoring invalid KEY=VALUE format: {item}")

    return result
