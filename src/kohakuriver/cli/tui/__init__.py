"""
TUI module for KohakuRiver.

Provides terminal-based interfaces:
- IDE: File tree browser, code editor, terminal emulator
- Dashboard: Cluster management with modal dialogs
"""

from kohakuriver.cli.tui.ide import IdeApp
from kohakuriver.cli.tui.dashboard import DashboardApp

__all__ = ["IdeApp", "DashboardApp"]
