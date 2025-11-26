"""
Resource monitoring service.

Monitors system resources (CPU, memory, temperature, GPU).
"""
import logging

import psutil

from hakuriver.utils.gpu import get_gpu_info

logger = logging.getLogger(__name__)


def get_system_stats() -> dict:
    """
    Get current system resource statistics.

    Returns:
        Dictionary with:
        - cpu_percent: CPU usage percentage
        - memory_percent: Memory usage percentage
        - memory_used_bytes: Memory used in bytes
        - memory_total_bytes: Total memory in bytes
        - current_avg_temp: Average CPU temperature
        - current_max_temp: Maximum CPU temperature
    """
    # CPU usage
    cpu_percent = psutil.cpu_percent(interval=None)

    # Memory usage
    mem_info = psutil.virtual_memory()

    # Temperature
    avg_temp = None
    max_temp = None
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            # Get temperatures from last sensor group
            temp_list = list(temps.values())
            if temp_list:
                temperatures = [sensor.current for sensor in temp_list[-1]]
                if temperatures:
                    avg_temp = sum(temperatures) / len(temperatures)
                    max_temp = max(temperatures)
    except Exception:
        pass  # Temperature monitoring not available

    return {
        "cpu_percent": cpu_percent,
        "memory_percent": mem_info.percent,
        "memory_used_bytes": mem_info.used,
        "memory_total_bytes": mem_info.total,
        "current_avg_temp": avg_temp,
        "current_max_temp": max_temp,
    }


def get_gpu_stats() -> list[dict]:
    """
    Get GPU information and statistics.

    Returns:
        List of GPU info dictionaries.
    """
    try:
        gpu_info = get_gpu_info()
        return [gpu.model_dump() if hasattr(gpu, "model_dump") else gpu for gpu in gpu_info]
    except Exception as e:
        logger.warning(f"Failed to get GPU info: {e}")
        return []


def get_total_cores() -> int:
    """
    Get total CPU core count.

    Returns:
        Number of CPU cores.
    """
    cores = psutil.cpu_count()
    if not cores:
        logger.warning("Could not determine CPU count, defaulting to 4.")
        return 4
    return cores


def get_total_memory() -> int:
    """
    Get total system memory in bytes.

    Returns:
        Total memory in bytes.
    """
    return psutil.virtual_memory().total
