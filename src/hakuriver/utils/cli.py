import re
from .logger import logger


def parse_memory_string(mem_str: str) -> int | None:
    """Parses memory string like '4G', '512M', '2K' into bytes."""
    if not mem_str:
        return None
    mem_str = mem_str.upper().strip()
    match = re.match(r"^(\d+)([KMG]?)$", mem_str)
    if not match:
        raise ValueError(
            f"Invalid memory format: '{mem_str}'. Use suffix K, M, or G (e.g., 512M, 4G)."
        )

    val = int(match.group(1))
    unit = match.group(2)

    if unit == "G":
        return val * 1000_000_000
    elif unit == "M":
        return val * 1000_000
    elif unit == "K":
        return val * 1000
    else:  # No unit means bytes
        return val


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
            logger.warning(f"Ignoring invalid environment variable format: {item}")
    return result
