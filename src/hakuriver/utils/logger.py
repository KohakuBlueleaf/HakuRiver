"""Logging utilities for HakuRiver with beautiful traceback formatting."""

import copy
import logging
import sys
import traceback

from hakuriver.models.enums import LogLevel

# ANSI color codes
COLORS = {
    "DEBUG": "\033[0;36m",  # CYAN
    "INFO": "\033[0;32m",  # GREEN
    "WARNING": "\033[0;33m",  # YELLOW
    "ERROR": "\033[0;31m",  # RED
    "CRITICAL": "\033[0;37;41m",  # WHITE ON RED
    "RESET": "\033[0m",
    "GRAY": "\033[0;90m",
    "BOLD": "\033[1m",
    "DIM": "\033[2m",
}


class ColoredFormatter(logging.Formatter):
    """
    Formatter that adds colors to log output.

    Format: [TIME][TYPE][MODULE] message
    Example: [14:32:05][INFO][hakuriver.host.app] Server starting...
    """

    def format(self, record: logging.LogRecord) -> str:
        colored_record = copy.copy(record)

        # Get level color
        level_color = COLORS.get(colored_record.levelname, COLORS["RESET"])
        reset = COLORS["RESET"]
        dim = COLORS["DIM"]

        # Format time with dim color
        time_str = self.formatTime(colored_record, self.datefmt)
        colored_time = f"{dim}[{time_str}]{reset}"

        # Format level with color
        colored_level = f"{level_color}[{colored_record.levelname}]{reset}"

        # Format module name with dim color
        colored_module = f"{dim}[{colored_record.name}]{reset}"

        # Build final message
        colored_record.msg = (
            f"{colored_time}{colored_level}{colored_module} {colored_record.msg}"
        )

        # Use a minimal format string since we built everything manually
        self._style._fmt = "%(message)s"

        return super().format(colored_record)


def format_traceback(exc: BaseException | None = None) -> str:
    """
    Format a traceback in a beautiful, readable format.

    Format:
    ====
    file: /path/to/file.py
    line: 42
    method: my_function
    code: some_code_here()
    ---
    file: /path/to/other.py
    line: 123
    method: other_function
    code: other_code()
    ---
    error: ValueError: Something went wrong
    ====

    Args:
        exc: Exception to format. If None, uses current exception from sys.exc_info()

    Returns:
        Formatted traceback string
    """
    if exc is None:
        exc_type, exc_value, exc_tb = sys.exc_info()
        if exc_value is None:
            return ""
        exc = exc_value
    else:
        exc_tb = exc.__traceback__

    lines = ["=" * 60]
    tb_list = traceback.extract_tb(exc_tb)

    for frame in tb_list:
        lines.append(f"file: {frame.filename}")
        lines.append(f"line: {frame.lineno}")
        lines.append(f"method: {frame.name}")
        if frame.line:
            lines.append(f"code: {frame.line.strip()}")
        lines.append("-" * 40)

    lines.append(f"error: {type(exc).__name__}: {exc}")
    lines.append("=" * 60)

    return "\n".join(lines)


def format_traceback_compact(exc: BaseException | None = None) -> str:
    """
    Format a traceback in a compact single-line format for less verbose logging.

    Args:
        exc: Exception to format. If None, uses current exception from sys.exc_info()

    Returns:
        Compact traceback string
    """
    if exc is None:
        exc_type, exc_value, exc_tb = sys.exc_info()
        if exc_value is None:
            return ""
        exc = exc_value
    else:
        exc_tb = exc.__traceback__

    tb_list = traceback.extract_tb(exc_tb)
    if not tb_list:
        return f"{type(exc).__name__}: {exc}"

    # Get the last frame (where error occurred)
    last_frame = tb_list[-1]
    return (
        f"{type(exc).__name__}: {exc} "
        f"(at {last_frame.filename}:{last_frame.lineno} in {last_frame.name})"
    )


class HakuRiverLogger:
    """
    Logger wrapper with configurable verbosity levels and beautiful formatting.

    Log levels (higher = less logging):
    - full: Everything including trace details
    - debug: Debug and above
    - info: Info and above
    - warning: Warning and above only
    """

    def __init__(self, name: str = "HakuRiver", level: LogLevel = LogLevel.INFO):
        self._logger = logging.getLogger(name)
        self._logger.propagate = False
        self._level = level

        # Add handler if we don't have one
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(ColoredFormatter(datefmt="%H:%M:%S"))
            self._logger.addHandler(handler)

        self._update_level()

    def _update_level(self) -> None:
        """Update the underlying logger level based on our LogLevel."""
        level_map = {
            LogLevel.FULL: logging.DEBUG,
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARNING: logging.WARNING,
        }
        self._logger.setLevel(level_map.get(self._level, logging.INFO))

    def set_level(self, level: LogLevel) -> None:
        """Set the logging verbosity level."""
        self._level = level
        self._update_level()

    def debug(self, msg: str, *args, **kwargs) -> None:
        """Log a debug message."""
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs) -> None:
        """Log an info message."""
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        """Log a warning message."""
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        """Log an error message."""
        self._logger.error(msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs) -> None:
        """Log a critical message."""
        self._logger.critical(msg, *args, **kwargs)

    def exception(
        self,
        msg: str,
        exc: BaseException | None = None,
        *args,
        **kwargs,
    ) -> None:
        """
        Log an exception with beautiful traceback formatting.

        Uses full traceback format for FULL level, compact for others.
        """
        match self._level:
            case LogLevel.FULL:
                tb = format_traceback(exc)
                self._logger.error(f"{msg}\n{tb}", *args, **kwargs)
            case LogLevel.DEBUG:
                tb = format_traceback(exc)
                self._logger.error(f"{msg}\n{tb}", *args, **kwargs)
            case LogLevel.INFO:
                tb = format_traceback_compact(exc)
                self._logger.error(f"{msg} - {tb}", *args, **kwargs)
            case LogLevel.WARNING:
                # Only log the message, no traceback
                self._logger.error(msg, *args, **kwargs)


# Global logger instance
logger = HakuRiverLogger()


def configure_logging(level: LogLevel = LogLevel.INFO) -> None:
    """
    Configure all HakuRiver loggers with the colored formatter.

    This sets up the root 'hakuriver' logger and configures the format
    for all child loggers (hakuriver.host, hakuriver.runner, etc.)

    Args:
        level: Log level to use
    """
    # Map LogLevel to logging level
    level_map = {
        LogLevel.FULL: logging.DEBUG,
        LogLevel.DEBUG: logging.DEBUG,
        LogLevel.INFO: logging.INFO,
        LogLevel.WARNING: logging.WARNING,
    }
    log_level = level_map.get(level, logging.INFO)

    # Configure the root hakuriver logger
    root_logger = logging.getLogger("hakuriver")
    root_logger.setLevel(log_level)
    root_logger.propagate = False

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add new handler with colored formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColoredFormatter(datefmt="%H:%M:%S"))
    handler.setLevel(log_level)
    root_logger.addHandler(handler)

    # Update global logger instance
    logger.set_level(level)
