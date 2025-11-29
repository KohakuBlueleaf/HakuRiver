"""
TUI IDE module for KohakuRiver.

Provides a terminal-based IDE interface with:
- File tree browser
- Code editor with syntax highlighting
- Terminal emulator via WebSocket
"""

from kohakuriver.cli.tui.ide import IdeApp

__all__ = ["IdeApp"]
